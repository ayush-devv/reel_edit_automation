"""Dub spike (roadmap 3c.4a): re-voice a finished project in another language, end to end.

lines → translate (Claude, checked) → synthesise (a declared voice generator, batch) → fit (shorter rewrite,
≤ 15 % speed-up, slide) → intelligibility QA (own ASR) → mix (dubbed dialogue + the project's music/SFX stems)
→ target-script captions → composite → dub/<lang>/reel_<lang>.mp4 + dub.json.

Everything stays in dub/<lang>/; the project is untouched. The only voice cleared so far (G2.5) is Chatterbox's
built-in voice — a stranger's voice over the client's face — so a spike render is for judging the pipeline, not
for delivery. A generator that clones a voice runs only with dub/consent.json (research note dubbing.md §7).
"""

from __future__ import annotations

import json
import subprocess
import time
import unicodedata
import wave
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from reel import config
from reel import numbers as num
from reel import script as sc
from reel.workspace import Workspace, atomic_write_bytes, atomic_write_json

PERSONA = Path(__file__).parent / "personas" / "dubber.md"
EFFORT = "medium"
LANGS = {"hi": {"name": "Hindi", "caption_script": "devanagari", "tts_lang": "hi"},
         "en": {"name": "English", "caption_script": "latin", "tts_lang": "en"}}
LINE_GAP_S = 0.35  # a pause this long between caption pages starts a new spoken line
LINE_MAX_S = 6.0
OVER = 1.15  # a line may run this much longer than its slot before it is rewritten; also the speed-up cap
SLIDE_GAP_S = 0.08  # silence kept between a slid line and the one before
MAX_LINE_ERROR = 0.35  # word error (ASR vs the text sent) above which a line holds the dub
PAGE_WORDS = 3
CONSENT_FIELDS = ("speaker", "languages", "reels", "retention", "revocation", "signed_at")
DISCLOSURE = "The voice in this version is AI-generated."
SYNTH_TIMEOUT_S = 180


class DubError(RuntimeError):
    pass


@dataclass
class Line:
    id: str
    start_f: int
    end_f: int
    text: str


@dataclass
class Placed:
    id: str
    start_s: float
    dur_s: float  # after any speed-up
    tempo: float
    drift_s: float
    over: bool = False  # still longer than its slot after the speed-up cap


class DubLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    caption: str
    tts: str


class DubPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[DubLine]


# ------------------------------------------------------------------ lines


def lines(tl) -> list[Line]:
    """Caption pages grouped into spoken lines: a new line at a pause, a sentence end, or LINE_MAX_S."""
    from reel import timebase as tb

    if not tl.captions or not tl.captions.pages:
        raise DubError("the timeline has no captions to dub")
    fps = tb.parse_rate(tl.fps)
    gap_f, max_f = round(LINE_GAP_S * fps), round(LINE_MAX_S * fps)
    out: list[Line] = []
    cur: Line | None = None
    for pg in tl.captions.pages:
        text = " ".join(w.text for w in pg.words).strip()
        if not text:
            continue
        if cur and (pg.start_f - cur.end_f >= gap_f or cur.text.rstrip()[-1:] in ".?!।" or pg.end_f - cur.start_f > max_f):
            out.append(cur)
            cur = None
        if cur is None:
            cur = Line(f"L{len(out) + 1:02d}", pg.start_f, pg.end_f, text)
        else:
            cur.end_f, cur.text = pg.end_f, f"{cur.text} {text}"
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------ translation


def deva_share(text: str) -> float:
    letters = [c for c in text if unicodedata.category(c).startswith("L") or unicodedata.category(c).startswith("M")]
    return sum("ऀ" <= c <= "ॿ" for c in letters) / len(letters) if letters else 0.0


def check_plan(plan: DubPlan, want: list[Line], lang: str):
    from reel.validate import Issue

    issues = []
    ids = [x.id for x in plan.lines]
    want_ids = [x.id for x in want]
    if sorted(ids) != sorted(want_ids) or len(set(ids)) != len(ids):
        missing, extra = [i for i in want_ids if i not in ids], [i for i in ids if i not in want_ids]
        issues.append(Issue("lines_changed", "lines", f"Answer every line once (missing {missing}, extra {extra}).",
                            f"Return exactly these ids, once each: {want_ids}."))
    hindi = LANGS[lang]["caption_script"] == "devanagari"
    for x in plan.lines:
        if not x.caption.strip() or not x.tts.strip():
            issues.append(Issue("empty", f"lines.{x.id}", "A line is empty.", "Give every line a caption and a tts text."))
            continue
        for name, text in (("tts", x.tts), ("caption", x.caption)):
            share = deva_share(text)
            if hindi and share < 0.8:
                issues.append(Issue("wrong_script", f"lines.{x.id}.{name}", f"`{name}` must be in Devanagari for Hindi.",
                                    "Write Hindi (and Hinglish) in Devanagari; English loanwords in Devanagari too."))
            if not hindi and share > 0.05:
                issues.append(Issue("wrong_script", f"lines.{x.id}.{name}", f"`{name}` must be in Latin script for English.",
                                    "Write English in Latin script."))
    return issues


def _input_md(ws: Workspace, lang: str, ls: list[Line], fps: Fraction, glossary: list[str]) -> str:
    rows = ["| id | starts at | seconds | original |", "|---|---|---|---|"]
    rows += [f"| {x.id} | {float(x.start_f / fps):.2f} | {float((x.end_f - x.start_f) / fps):.2f} | {x.text} |" for x in ls]
    parts = [f"# Dub this reel into {LANGS[lang]['name']}", "",
             "Each line must be spoken naturally in about the same seconds as the original (Hindi usually runs longer "
             "than English: prefer the shorter natural phrasing).", "", *rows, ""]
    if glossary:
        parts += ["## Keep exactly (names, products)", "", *[f"- {g}" for g in glossary], ""]
    rel = Path("dub") / lang / "input.md"
    atomic_write_bytes(ws.path(*rel.parts), "\n".join(parts).encode())
    return str(rel)


def translate(caller, ws: Workspace, lang: str, ls: list[Line], fps: Fraction, glossary: list[str]) -> tuple[DubPlan, str | None, float]:
    from reel import decide

    rel = _input_md(ws, lang, ls, fps, glossary)
    d = decide.decide(caller, ws, label=f"dub_{lang}", prompt=f"Read {rel} and return the dub plan.", model=DubPlan, persona=PERSONA,
                      effort=EFFORT, check=lambda p: check_plan(p, ls, lang))
    return d.plan, d.session_id, d.cost_usd


def shorten(caller, ws: Workspace, lang: str, plan: DubPlan, over: dict[str, float], ls: list[Line], session: str | None) -> tuple[DubPlan, float]:
    """One shorter rewrite for the lines that ran over their slot; other lines are kept as they were."""
    from reel import decide

    detail = "\n".join(f"- {i}: {r:.0%} of its slot" for i, r in over.items())
    prompt = (f"These lines came out too long when spoken:\n{detail}\nRewrite only those lines shorter (same meaning, natural "
              f"speech) and return the complete dub plan with every other line unchanged.")
    d = decide.decide(caller, ws, label=f"dub_{lang}_shorten", prompt=prompt, model=DubPlan, persona=PERSONA, effort=EFFORT,
                      check=lambda p: check_plan(p, ls, lang), resume=session)
    old = {x.id: x for x in plan.lines}
    new = {x.id: x for x in d.plan.lines}
    return DubPlan(lines=[new[i] if i in over else old[i] for i in old]), d.cost_usd


# ------------------------------------------------------------------ voice


def voice(gen_id: str | None, gens: dict | None = None, reg=None, project: Workspace | None = None) -> tuple[str, dict]:
    """The declared voice generator: licence row checked (G2.5 rule); a cloning voice needs written consent."""
    from reel import listen

    gens = listen.declared() if gens is None else gens
    voices = {g: s for g, s in gens.items() if s.get("set") == "voice"}
    if not voices:
        raise DubError("no voice generator declared in ~/.config/reel/generators.json (set \"voice\")")
    gid = gen_id or sorted(voices)[0]
    spec = voices.get(gid)
    if spec is None:
        raise DubError(f"voice generator {gid!r} is not declared; declared: {sorted(voices)}")
    try:
        listen.check_licence(gid, spec, reg)
    except listen.ListenError as exc:
        raise DubError(str(exc)) from exc
    if spec.get("clones"):
        consent = project.path("dub", "consent.json") if project else None
        data = json.loads(consent.read_text()) if consent and consent.exists() else None
        if not data or any(not data.get(k) for k in CONSENT_FIELDS):
            raise DubError(f"{gid} clones a voice: dub/consent.json must record {', '.join(CONSENT_FIELDS)} "
                           "(written consent from the speaker, research note dubbing.md §7)")
    return gid, spec


def synthesize(spec: dict, jobs: list[dict], work: Path) -> None:
    """jobs: [{text, lang, out}]. One model load with `batch_cmd`; else one process per line with `cmd`."""
    work.mkdir(parents=True, exist_ok=True)
    if spec.get("batch_cmd"):
        jf = work / "jobs.json"
        atomic_write_json(jf, jobs)
        cmd = [a.replace("{jobs}", str(jf)) for a in spec["batch_cmd"]]
        subprocess.run(cmd, check=True, capture_output=True, timeout=SYNTH_TIMEOUT_S + 90 * len(jobs))
    else:
        for j in jobs:
            cmd = [a.replace("{prompt}", j["text"]).replace("{lang}", j["lang"]).replace("{out}", j["out"]).replace("{seconds}", "0")
                   for a in spec["cmd"]]
            subprocess.run(cmd, check=True, capture_output=True, timeout=SYNTH_TIMEOUT_S)
    missing = [j["out"] for j in jobs if not Path(j["out"]).exists() or Path(j["out"]).stat().st_size == 0]
    if missing:
        raise DubError(f"the voice generator wrote nothing for {len(missing)} line(s): {[Path(m).name for m in missing]}")


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


# ------------------------------------------------------------------ fit


def slots(ls: list[Line], fps: Fraction, total_f: int) -> list[float]:
    """Seconds each line may take: up to the next line's original start (the last one: to the end)."""
    starts = [x.start_f for x in ls[1:]] + [total_f]
    return [float((s - x.start_f) / fps) for x, s in zip(ls, starts)]


def over_ratios(ls: list[Line], durs: dict[str, float], fps: Fraction, total_f: int) -> dict[str, float]:
    return {x.id: durs[x.id] / s for x, s in zip(ls, slots(ls, fps, total_f)) if s > 0 and durs[x.id] / s > OVER}


def fit(ls: list[Line], durs: dict[str, float], fps: Fraction, total_f: int) -> list[Placed]:
    """Speed a long line up (≤ OVER), never slow one down; a line still too long pushes the next one later."""
    out: list[Placed] = []
    prev_end = 0.0
    for x, slot in zip(ls, slots(ls, fps, total_f)):
        d = durs[x.id]
        tempo = min(OVER, d / slot) if slot > 0 and d > slot else 1.0
        length = d / tempo
        orig = float(x.start_f / fps)
        start = orig if prev_end <= orig + 1e-6 else prev_end + SLIDE_GAP_S  # slide only past an overlap
        out.append(Placed(x.id, round(start, 3), round(length, 3), round(tempo, 3), round(start - orig, 3), over=length > slot + 1e-6))
        prev_end = start + length
    return out


# ------------------------------------------------------------------ QA


def _number_word(tok: str) -> bool:
    t = unicodedata.normalize("NFC", tok.casefold())
    return (any(ch.isdigit() for ch in t) or t in num.WORD_UNITS or t in num.SCALES or t in num.EN_TENS or t in num.FRACTIONS
            or t in num.MODIFIERS or t in num.PERCENT)


def line_error(sent: str, heard: str) -> float:
    """Word error of what the recogniser heard against what was sent, on script-agnostic keys. Numbers are compared as
    values ("5000" heard for "पाँच हज़ार" sent is right); each sent number not heard counts as one error."""
    sent, heard = (t.replace("।", " ").replace("॥", " ") for t in (sent, heard))  # the danda sits inside the Devanagari block
    want = [sc.key(t) for t in sc.tokens(sent) if not _number_word(t)]
    got = [sc.key(t) for t in sc.tokens(heard) if not _number_word(t)]
    sent_n, heard_n = num.parse(sent), num.parse(heard)
    missed = sum(not any(num.matches(s, h) for h in heard_n) for s in sent_n)
    total = len(want) + len(sent_n)
    if total == 0:
        return 0.0
    matched = sum(b.size for b in SequenceMatcher(a=want, b=got, autojunk=False).get_matching_blocks())
    return round((len(want) - matched + missed) / total, 3)


# ------------------------------------------------------------------ captions


def caption_pages(placed: list[Placed], plan: DubPlan, heard: dict[str, list], fps: Fraction) -> list[dict]:
    """Target-script pages of ≤ PAGE_WORDS words. Word times: the recogniser's when its word count matches the caption's,
    else spread over the spoken span by characters."""
    by_id = {x.id: x for x in plan.lines}
    pages, i = [], 0
    for p in placed:
        words = by_id[p.id].caption.split()
        if not words:
            continue
        hw = heard.get(p.id) or []
        scale = 1.0 / p.tempo
        if len(hw) == len(words):
            times = [(p.start_s + w.start_s * scale, p.start_s + w.end_s * scale) for w in hw]
        else:
            span0 = (hw[0].start_s * scale) if hw else 0.0
            span1 = (hw[-1].end_s * scale) if hw else p.dur_s
            total = sum(len(w) + 1 for w in words)
            t, times = p.start_s + span0, []
            for w in words:
                d = (span1 - span0) * (len(w) + 1) / total
                times.append((t, t + d))
                t += d
        for k in range(0, len(words), PAGE_WORDS):
            chunk = list(zip(words[k:k + PAGE_WORDS], times[k:k + PAGE_WORDS]))
            cw = []
            for text, (a, b) in chunk:
                fa, fb = round(a * fps), max(round(b * fps), round(a * fps) + 1)
                cw.append({"i": i, "text": text, "start_f": fa, "end_f": fb, "emph": False})
                i += 1
            pages.append({"start_f": cw[0]["start_f"], "end_f": cw[-1]["end_f"], "words": cw})
    for a, b in zip(pages, pages[1:]):  # pages never overlap
        if a["end_f"] > b["start_f"]:
            a["end_f"] = max(a["start_f"] + 1, b["start_f"])
            a["words"][-1]["end_f"] = min(a["words"][-1]["end_f"], a["end_f"])
    return pages


# ------------------------------------------------------------------ mix + render


def _atempo(src: Path, dst: Path, tempo: float) -> None:
    from reel import tools

    rate = config.AUDIO_RATE
    chain = f"aresample={rate}" + (f",atempo={tempo:.4f}" if abs(tempo - 1.0) > 1e-3 else "")
    tools.ffmpeg(["-y", "-i", str(src), "-af", chain, "-ac", "2", "-c:a", "pcm_s24le", str(dst)])


def dialogue_track(placed: list[Placed], wavs: dict[str, Path], out: Path, total_s: float) -> None:
    """The dubbed lines on a silent track of the reel's length."""
    from reel import tools

    rate = config.AUDIO_RATE
    ins, graph = [], []
    for k, p in enumerate(placed):
        ins += ["-i", str(wavs[p.id])]
        graph.append(f"[{k}:a]adelay={int(round(p.start_s * 1000))}:all=1[d{k}]")
    n = len(placed)
    graph.append(f"anullsrc=r={rate}:cl=stereo,atrim=duration={total_s:.4f}[sil]")
    graph.append("[sil]" + "".join(f"[d{k}]" for k in range(n)) + f"amix=inputs={n + 1}:normalize=0:duration=first:dropout_transition=0[a]")
    tools.ffmpeg(["-y", *ins, "-filter_complex", ";".join(graph), "-map", "[a]", "-ar", str(rate), "-c:a", "pcm_s24le", str(out)])


def dub_base(project: Workspace, dialogue: Path, out: Path) -> None:
    """base.mov picture + (dubbed dialogue + the project's own music and SFX stems)."""
    from reel import tools

    stems = project.path("render", "stems")
    tools.ffmpeg(["-y", "-i", str(project.path("render", "base.mov")), "-i", str(dialogue), "-i", str(stems / "music.wav"),
                  "-i", str(stems / "sfx.wav"), "-filter_complex",
                  "[1:a][2:a][3:a]amix=inputs=3:normalize=0:duration=first:dropout_transition=0[a]",
                  "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "pcm_s24le", "-ar", str(config.AUDIO_RATE), str(out)])


def render(project: Workspace, tl, pages: list[dict], lang: str, base: Path, out_dir: Path) -> dict:
    from reel import overlay
    from reel.schemas.timeline import CaptionPage

    cap = tl.captions.model_copy(update={"pages": [CaptionPage.model_validate(p) for p in pages],
                                         "script": LANGS[lang]["caption_script"]})
    tl_dub = tl.model_copy(update={"captions": cap})
    rj = lambda *p: json.loads(project.path(*p).read_text()) if project.path(*p).exists() else None  # noqa: E731
    props = overlay.build_props(tl_dub, project.root, rj("perception", "faces.json"), rj("perception", "ocr.json"),
                                rj("perception", "scenes.json"), rj("perception", "speakers.json"))
    ov = out_dir / "overlay.mov"
    meta = overlay.render_overlay(props, ov, public_dir=project.root)
    behind = next((t for t in tl.titles if t.layer == "behind"), None)
    bh = ({"layer": project.path("render", "behind.mov"), "matte": project.path("render", "matte.mkv"), "start_f": behind.start_f,
           "end_f": behind.end_f} if behind else None)
    final = out_dir / f"reel_{lang}.mp4"
    meta |= overlay.composite(tl_dub, base, ov, final, behind=bh)
    return meta


# ------------------------------------------------------------------ the job


@dataclass
class Options:
    lang: str
    voice: str | None = None
    render: bool = True
    glossary: list[str] = field(default_factory=list)


def run(project_root: Path, opts: Options, *, caller=None, gens: dict | None = None, reg=None, synth=synthesize, asr=None) -> dict:
    from reel import claude_call, decide
    from reel import timebase as tb
    from reel.schemas.timeline import Timeline

    if opts.lang not in LANGS:
        raise DubError(f"language {opts.lang!r} is not supported yet: use one of {sorted(LANGS)}")
    project = Workspace(project_root.resolve())
    for need in ("timeline/timeline.json", "render/base.mov", "render/stems/dialogue.wav", "render/stems/music.wav", "render/stems/sfx.wav"):
        if not project.path(need).exists():
            raise DubError(f"{project.root.name} has no {need}: run the edit to the end first")
    gid, spec = voice(opts.voice, gens, reg, project)
    out_dir = project.path("dub", opts.lang)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "lines"
    t0 = time.time()
    tl = Timeline.model_validate_json(project.path("timeline", "timeline.json").read_text())
    fps = tb.parse_rate(tl.fps)
    ls = lines(tl)
    caller = caller or claude_call.call
    try:
        plan, session, cost = translate(caller, project, opts.lang, ls, fps, opts.glossary)
    except decide.DecisionError as exc:
        raise DubError(str(exc)) from exc
    tts_lang = LANGS[opts.lang]["tts_lang"]

    def speak(ids: list[str]) -> None:
        by = {x.id: x for x in plan.lines}
        synth(spec, [{"text": by[i].tts, "lang": tts_lang, "out": str(work / f"{i}.wav")} for i in ids], work)

    t_synth = time.time()
    speak([x.id for x in ls])
    durs = {x.id: wav_seconds(work / f"{x.id}.wav") for x in ls}
    over = over_ratios(ls, durs, fps, tl.duration_f)
    rewritten: list[str] = []
    if over:
        plan, c2 = shorten(caller, project, opts.lang, plan, over, ls, session)
        cost += c2
        rewritten = sorted(over)
        speak(rewritten)
        durs |= {i: wav_seconds(work / f"{i}.wav") for i in rewritten}
    synth_s = round(time.time() - t_synth, 1)
    placed = fit(ls, durs, fps, tl.duration_f)
    total_s = float(tl.duration_f / fps)

    from reel.perception.asr import MlxWhisper

    asr = asr or MlxWhisper()
    by = {x.id: x for x in plan.lines}
    heard, qa_lines = {}, []
    for p in placed:
        words, _ = asr.transcribe(work / f"{p.id}.wav", tts_lang, None)
        heard[p.id] = words
        err = line_error(by[p.id].tts, " ".join(w.text for w in words))
        qa_lines.append({"id": p.id, "error": err, "heard": " ".join(w.text for w in words), "tts": by[p.id].tts,
                         "caption": by[p.id].caption, "start_s": p.start_s, "seconds": p.dur_s, "tempo": p.tempo, "drift_s": p.drift_s,
                         "over_slot": p.over, "rewritten": p.id in rewritten})
    bad = [q["id"] for q in qa_lines if q["error"] > MAX_LINE_ERROR]
    end_drift = max(0.0, placed[-1].start_s + placed[-1].dur_s - total_s) if placed else 0.0
    hold = [f"line {i}: the recogniser could not follow it (word error over {MAX_LINE_ERROR:.0%})" for i in bad]
    if end_drift > 0.5:
        hold.append(f"the dub runs {end_drift:.1f} s past the end of the reel")

    fitted = {}
    for p in placed:
        dst = work / f"{p.id}.fit.wav"
        _atempo(work / f"{p.id}.wav", dst, p.tempo)
        fitted[p.id] = dst
    dialogue = out_dir / "dialogue.wav"
    dialogue_track(placed, fitted, dialogue, total_s)
    pages = caption_pages(placed, plan, heard, fps)
    meta: dict = {}
    if opts.render:
        base = out_dir / "base.mov"
        dub_base(project, dialogue, base)
        meta = render(project, tl, pages, opts.lang, base, out_dir)
    record = {
        "lang": opts.lang, "created": time.time(), "status": "hold" if hold else "ok", "hold": hold,
        "for_delivery": False,  # the spike: a built-in voice is not the speaker's; cloning + consent come first
        "why_not_for_delivery": "the voice is not the speaker's" if not spec.get("clones") else "spike: owner review first",
        "voice": {"generator": gid, "source": spec.get("source"), "licence_id": spec.get("licence_id"), "commit": spec.get("commit"),
                  "weights_sha256": spec.get("weights_sha256"), "watermark": spec.get("watermark"),
                  "voice": spec.get("voice", "built-in (not the speaker)"), "clones": bool(spec.get("clones"))},
        "disclosure": DISCLOSURE, "lines": qa_lines, "rewritten": rewritten, "end_drift_s": round(end_drift, 2),
        "claude_cost_usd": round(cost, 4), "synth_s": synth_s, "total_s": round(time.time() - t0, 1),
        "output": f"dub/{opts.lang}/reel_{opts.lang}.mp4" if opts.render else None, "render": meta,
    }
    atomic_write_json(out_dir / "dub.json", record)
    return record
