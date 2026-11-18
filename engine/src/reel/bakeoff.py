"""Hinglish ASR bake-off (ADR-0007, build step 8).

Dataset: samples/hinglish/<name>/ with one media file (video or audio), `transcript.txt` (what
was said, any script, fillers written as spoken) and optionally `words.tsv`
(word<TAB>start_s<TAB>end_s) for caption-sync scoring.

Each engine transcribes every clip; scores are computed on script-agnostic keys (reel.script.key)
so a Roman-script engine and a Devanagari engine are compared fairly:
  WER (key), CER (key characters), filler retention, word-onset error vs words.tsv,
  timing sanity (zero/negative/overlong words, non-monotonic starts), real-time factor.
Composite (ADR-0007: accuracy first, then fillers, then sync) picks the engine.
"""

from __future__ import annotations

import difflib
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from reel import config
from reel import script as sc
from reel.evalh.metrics import median_timing_error_ms, word_error_rate
from reel.perception.asr import RawWord
from reel.perception.audio import extract_wav

MEDIA_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".wav", ".m4a", ".mp3", ".aac", ".flac", ".aiff", ".aif"}
DEFAULT_DIR = config.REPO_ROOT / "samples" / "hinglish"
# true disfluencies (not discourse words like "matlab"/"toh", which carry meaning and are usually kept)
FILLER_KEYS = {sc.key(w) for w in ("um", "umm", "uh", "uhh", "hmm", "hm", "er", "erm", "aa", "aah", "mm", "अ", "अं", "हम्म", "उम")}
WEIGHTS = {"accuracy": 0.6, "fillers": 0.2, "sync": 0.2}
SYNC_WORST_MS = 300.0


@dataclass
class Clip:
    name: str
    media: Path
    reference: str
    ref_times: list[tuple[str, float, float]] | None = None


def load_dataset(root: Path = DEFAULT_DIR) -> list[Clip]:
    clips = []
    for d in sorted(p for p in root.glob("*") if p.is_dir()):
        media = next((f for f in sorted(d.iterdir()) if f.suffix.lower() in MEDIA_EXT), None)
        ref = d / "transcript.txt"
        if media is None or not ref.exists():
            continue
        times = None
        tsv = d / "words.tsv"
        if tsv.exists():
            times = []
            for line in tsv.read_text().splitlines():
                parts = line.split("\t")
                if len(parts) >= 3:
                    try:
                        times.append((parts[0], float(parts[1]), float(parts[2])))
                    except ValueError:
                        continue  # header
        clips.append(Clip(d.name, media, ref.read_text().strip(), times))
    return clips


def char_error_rate(ref: str, hyp: str) -> float:
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def filler_retention(ref_keys: list[str], hyp_keys: list[str]) -> float | None:
    want = [k for k in ref_keys if k in FILLER_KEYS]
    if not want:
        return None
    have = [k for k in hyp_keys if k in FILLER_KEYS]
    kept = 0
    for k in want:
        if k in have:
            have.remove(k)
            kept += 1
    return kept / len(want)


def onset_errors(ref_times: list[tuple[str, float, float]], hyp: list[RawWord]) -> list[tuple[float, float]]:
    """Match hypothesis words to timed reference words by key (difflib alignment) → onset pairs."""
    rk = [sc.key(w) for w, _, _ in ref_times]
    hk = [sc.key(w.text) for w in hyp]
    pairs = []
    for block in difflib.SequenceMatcher(a=rk, b=hk, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            pairs.append((hyp[block.b + k].start_s, ref_times[block.a + k][1]))
    return pairs


def timing_sanity(words: list[RawWord]) -> float:
    """Share of words with impossible timing (≤ 0 or > 2 s long, or starting before the previous word)."""
    if not words:
        return 1.0
    bad = sum(1 for k, w in enumerate(words) if w.end_s - w.start_s <= 0 or w.end_s - w.start_s > 2.0
              or (k and w.start_s < words[k - 1].start_s - 1e-3))
    return bad / len(words)


@dataclass
class ClipScore:
    engine: str
    clip: str
    wer: float
    cer: float
    fillers: float | None
    onset_ms: float | None
    within_100ms: float | None
    bad_timing: float
    rtf: float
    devanagari_share: float
    hypothesis: str = field(repr=False, default="")

    def composite(self) -> float:
        acc = max(0.0, 1 - (self.wer + self.cer) / 2)
        parts = {"accuracy": acc}
        if self.fillers is not None:
            parts["fillers"] = self.fillers
        if self.onset_ms is not None:
            parts["sync"] = max(0.0, 1 - min(self.onset_ms, SYNC_WORST_MS) / SYNC_WORST_MS)
        w = sum(WEIGHTS[k] for k in parts)
        return sum(WEIGHTS[k] * v for k, v in parts.items()) / w * (1 - min(0.5, self.bad_timing))


def score(engine: str, clip: Clip, words: list[RawWord], runtime_s: float, duration_s: float) -> ClipScore:
    hyp_text = " ".join(w.text for w in words)
    rk = [sc.key(t) for t in sc.tokens(clip.reference)]
    hk = [sc.key(t) for t in sc.tokens(hyp_text)]
    pairs = onset_errors(clip.ref_times, words) if clip.ref_times else []
    within = sum(abs(p - r) <= 0.1 for p, r in pairs) / len(pairs) if pairs else None
    return ClipScore(engine=engine, clip=clip.name, wer=round(word_error_rate(rk, hk), 4),
                     cer=round(char_error_rate(" ".join(rk), " ".join(hk)), 4), fillers=filler_retention(rk, hk),
                     onset_ms=median_timing_error_ms(pairs) if pairs else None, within_100ms=within,
                     bad_timing=round(timing_sanity(words), 4), rtf=round(runtime_s / max(duration_s, 1e-6), 3),
                     devanagari_share=round(sc.mixed_ratio(hyp_text), 3), hypothesis=hyp_text)


def warm(engines: dict[str, object], out_dir: Path, language: str | None) -> None:
    import numpy as np
    import soundfile as sf

    wav = out_dir / "wav" / "_warmup.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(wav), (np.random.default_rng(0).normal(0, 0.01, 16000)).astype("float32"), 16000)
    for name, backend in engines.items():
        try:
            backend.transcribe(wav, language, None)
        except Exception as exc:  # noqa: BLE001 — the timed run records the failure
            (out_dir / "errors.log").open("a").write(f"{name} warm-up: {type(exc).__name__}: {exc}\n")


def run(engines: dict[str, object], clips: list[Clip], out_dir: Path, *, language: str | None = "hi") -> dict:
    """engines: name → backend with .transcribe(wav, language, prompt) (reel.perception.asr.Backend)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    warm(engines, out_dir, language)  # load/download models outside the timed runs (RTF = transcription only)
    rows: list[ClipScore] = []
    for clip in clips:
        wav = extract_wav(clip.media, out_dir / "wav" / f"{clip.name}.wav")
        import soundfile as sf

        duration = sf.info(str(wav)).duration
        for name, backend in engines.items():
            t0 = time.time()
            try:
                words, _lang = backend.transcribe(wav, language, None)
            except Exception as exc:  # noqa: BLE001 — a failing engine scores zero, the bake-off continues
                (out_dir / "errors.log").open("a").write(f"{name} {clip.name}: {type(exc).__name__}: {exc}\n")
                words = []
            s = score(name, clip, words, time.time() - t0, duration)
            rows.append(s)
            d = out_dir / name
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{clip.name}.txt").write_text(s.hypothesis + "\n")
            (d / f"{clip.name}.words.tsv").write_text("".join(f"{w.text}\t{w.start_s:.3f}\t{w.end_s:.3f}\t{w.prob:.2f}\n" for w in words))
    summary = summarise(rows)
    (out_dir / "results.json").write_text(json.dumps({"summary": summary, "clips": [r.__dict__ for r in rows]}, indent=2, ensure_ascii=False))
    (out_dir / "results.md").write_text(report_md(summary, rows, clips))
    return summary


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 4) if vals else None


def summarise(rows: list[ClipScore]) -> dict:
    out = {}
    for name in dict.fromkeys(r.engine for r in rows):
        rs = [r for r in rows if r.engine == name]
        out[name] = {"wer": _mean([r.wer for r in rs]), "cer": _mean([r.cer for r in rs]), "fillers": _mean([r.fillers for r in rs]),
                     "onset_ms": _mean([r.onset_ms for r in rs]), "within_100ms": _mean([r.within_100ms for r in rs]),
                     "bad_timing": _mean([r.bad_timing for r in rs]), "rtf": _mean([r.rtf for r in rs]),
                     "devanagari_share": _mean([r.devanagari_share for r in rs]), "composite": _mean([r.composite() for r in rs])}
    ranked = sorted(out, key=lambda n: -(out[n]["composite"] or 0))
    return {"engines": out, "ranking": ranked, "winner": ranked[0] if ranked else None}


def report_md(summary: dict, rows: list[ClipScore], clips: list[Clip]) -> str:
    e = summary["engines"]
    lines = ["# Hinglish ASR bake-off", "", f"{len(clips)} clip(s): {', '.join(c.name for c in clips)} · "
             f"timing reference on {sum(1 for c in clips if c.ref_times)} clip(s)", "",
             "| engine | composite | WER | CER | fillers kept | onset err ms | ≤100 ms | bad timing | RTF | Devanagari |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    fmt = lambda v: "–" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))  # noqa: E731
    for n in summary["ranking"]:
        s = e[n]
        lines.append(f"| {n} | {fmt(s['composite'])} | {fmt(s['wer'])} | {fmt(s['cer'])} | {fmt(s['fillers'])} | {fmt(s['onset_ms'])} | "
                     f"{fmt(s['within_100ms'])} | {fmt(s['bad_timing'])} | {fmt(s['rtf'])} | {fmt(s['devanagari_share'])} |")
    lines += ["", f"**Winner (composite = {WEIGHTS}, scaled down by bad timing): {summary['winner']}**", "",
              "Scores use script-agnostic keys (`reel.script.key`): Devanagari is romanised and spelling variants folded "
              "before comparison. Hypotheses per engine are in `<engine>/<clip>.txt` — read a few before trusting the numbers.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ engines

def engines(names: list[str] | None = None) -> dict[str, object]:
    """Registered candidates (ADR-0007). Heavy engines import lazily inside their adapters."""
    from reel.perception.asr import MlxWhisper

    registry = {
        "whisper-turbo": lambda: MlxWhisper("mlx-community/whisper-large-v3-turbo"),
        "whisper-large-v3": lambda: MlxWhisper("mlx-community/whisper-large-v3-mlx"),
    }
    from reel import hinglish_engines

    hinglish_engines.register()
    registry.update(EXTRA_ENGINES)
    pick = names or list(registry)
    unknown = [n for n in pick if n not in registry]
    if unknown:
        raise KeyError(f"unknown engine(s) {unknown}; available: {sorted(registry)}")
    return {n: registry[n]() for n in pick}


EXTRA_ENGINES: dict[str, object] = {}  # transformers-based adapters register here (see hinglish_engines.py)
