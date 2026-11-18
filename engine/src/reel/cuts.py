"""Cut-point self-check on the final render (idea from browser-use/video-use, MIT).

For every cut of the reel (base clip boundaries incl. pause-tightening jump cuts, and full-frame
b-roll in/out) a "timeline view" strip: 10 frames from 1.5 s before to 1.5 s after the cut above
the waveform of that audio window, with the cut marked in red; plus strips of the first and last
2 s. Four automatic checks feed QA; all start as `warn` (config.QA_GATES) until calibrated:

  cut_pop         click/pop in the final mix within ±20 ms of a cut: the peak linear-prediction
                  residual (speech and music are predictable sample to sample, a click is not)
                  stands POP_DB above the 99.9th percentile of the surrounding ±300 ms
  cut_flash       one frame at a cut that differs strongly from both neighbours (a white/black
                  flash, or a stray frame of another shot between two stable shots)
  cut_in_word     a cut that lands inside a spoken word: checked on the source clock against
                  the heard word edges (perception/edges.json, else ASR times), base clips only
  duration_match  container / video / audio durations of the deliverable vs the timeline

Intended events are not defects: SFX at a cut skip the pop check; transitions, flash events,
footage effects and full-screen cards near a cut skip the flash check.
Writes qa/cuts/*.png and qa/cuts.json.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np

from reel import config, qa, sheets, tools
from reel import timebase as tb
from reel.schemas.perception import WordTable
from reel.schemas.timeline import Timeline, VideoClip
from reel.workspace import atomic_write_json

AUDIO_RATE = 48_000
POP_WIN_S = 0.020  # look for the click this close to the cut
POP_GUARD_S = 0.025  # context excludes this much around the cut
POP_CTX_S = 0.300  # context = the surrounding ±300 ms of the mix
LPC_ORDER = 24
POP_DB = 15.0  # residual burst this far above the context's 99.9th percentile = click (0.1 % of
#                arbitrary positions in a real podcast mix score this high; injected clicks score 17–25 dB)
POP_MIN = 0.02  # absolute floor (residual, full scale = 1): ignore bumps in near-silence
FLASH_MAD = 25.0  # mean |Δluma| (0–255) to BOTH neighbours for a stray frame
FLASH_LUMA = 30.0  # mean-luma jump (0–255) up/down on both sides for a flash frame
STABLE_SHARE = 0.5  # a stray frame's neighbours change less than half as much among themselves
WORD_TOL_US = 10_000  # + one frame: cut points are snapped to the frame grid
STRIP_SPAN_S = 1.5
EDGE_S = 2.0  # head / tail strips
TILES = 10
TILE_W = 170
GAP, MID_GAP = 4, 10
HEAD_H, WAVE_H = 34, 150
REVIEW_STRIPS = 12  # cut strips the Reviewer sees (most suspicious first), plus head and tail
CARD_GRAPHICS = {"text_card", "cta_card"}
RED = np.array([255, 64, 64], dtype=np.uint8)


# ------------------------------------------------------------------ the cut list


def cut_points(tl: Timeline) -> list[dict]:
    """Output frames where the picture cuts: base clip boundaries and full-frame b-roll in/out."""
    base = sorted((c for c in tl.video if c.id.startswith("v_")), key=lambda c: c.at_f)
    by_f: dict[int, dict] = {}

    def at(f: int) -> dict:
        return by_f.setdefault(f, {"f": f, "kinds": [], "out_clip": None, "in_clip": None, "label": []})

    for a, b in zip(base, base[1:]):
        d = at(b.at_f)
        d["kinds"].append("cut" if a.src.item != b.src.item else "jump_cut")
        d["out_clip"], d["in_clip"] = a.id, b.id
        d["label"].append(f"{a.id[2:]}→{b.id[2:]}")
    for c in tl.video:
        if c.id.startswith("br_"):
            for f, kind in ((c.at_f, "broll_in"), (c.at_f + c.dur_f, "broll_out")):
                if 0 < f < tl.duration_f:
                    at(f)["kinds"].append(kind)
                    at(f)["label"].append(f"{kind.replace('_', ' ')} {c.id[3:]}")
    return [by_f[f] for f in sorted(by_f)]


def intended(tl: Timeline, f: int, fps: Fraction) -> tuple[list[str], list[str]]:
    """Designed events at this cut: (visual, audio) reasons to skip the flash / pop check."""
    vis = [f"transition {t.type.value}" for t in tl.transitions if abs(t.at_f - f) <= t.frames + 1]
    vis += ["flash" for fl in tl.flashes if abs(fl.at_f - f) <= fl.frames + 1]
    vis += [f"effect {e.type}" for e in tl.effects if e.start_f - 3 <= f <= e.end_f + 3]
    vis += [f"graphic {g.kind}" for g in tl.graphics if g.kind in CARD_GRAPHICS and min(abs(g.start_f - f), abs(g.end_f - f)) <= 3]
    w = math.ceil(POP_WIN_S * float(fps)) + 1
    aud = [f"sfx {a.asset}" for a in tl.audio if a.role == "sfx" and a.at_f - w <= f <= a.at_f + a.dur_f + w]
    return vis, aud


# ------------------------------------------------------------------ decoding


def read_audio(path: Path) -> np.ndarray:
    """The final mix as mono float32 at 48 kHz (empty when there is no audio)."""
    try:
        raw = tools.ffmpeg(["-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(AUDIO_RATE), "-f", "f32le", "-"]).stdout
    except tools.ToolError:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(raw, dtype=np.float32)


def decode_frames(path: Path, frames: set[int], width: int) -> dict[int, np.ndarray]:
    """These frame numbers at `width` (RGB) in ONE decode pass (qa.frames_at decodes the file once
    per 40 frames; cut strips need hundreds)."""
    if not frames:
        return {}
    v = next(s for s in tools.ffprobe_json(path)["streams"] if s["codec_type"] == "video")
    height = int(round(int(v["height"]) * width / int(v["width"]) / 2) * 2)
    size, last, out, n = width * height * 3, max(frames), {}, 0
    proc = subprocess.Popen([str(config.ffmpeg_path()), "-v", "error", "-nostdin", "-i", str(path), "-map", "0:v:0",
                             "-vf", f"scale={width}:{height}:flags=area", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while n <= last:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            if n in frames:
                out[n] = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3)
            n += 1
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()
    return out


# ------------------------------------------------------------------ checks


def lpc_residual(seg: np.ndarray, order: int = LPC_ORDER) -> np.ndarray:
    """Linear-prediction error of `seg` (autocorrelation method). Speech and music are predictable
    from the last few ms; a click is not, so it stands out in the residual even under loud audio."""
    seg = seg.astype(np.float64)
    n = len(seg)
    r = np.array([seg[:n - k] @ seg[k:] for k in range(order + 1)])
    if r[0] <= 1e-12:
        return np.zeros(n)
    r[0] *= 1 + 1e-6  # white-noise correction keeps the system well conditioned
    toeplitz = r[np.abs(np.subtract.outer(np.arange(order), np.arange(order)))]
    a = np.linalg.solve(toeplitz, r[1:order + 1])
    pred = np.convolve(seg, np.concatenate([[0.0], a]))[:n]
    e = seg - pred
    e[:order] = 0.0
    return e


def pop_measure(x: np.ndarray, t: float) -> dict | None:
    """Click detector at time t (s) of the mono mix `x`: peak LPC residual within ±20 ms of the cut
    vs the 99.9th percentile of the residual over the surrounding ±300 ms."""
    c = int(round(t * AUDIO_RATE))
    w, g, k = (int(s * AUDIO_RATE) for s in (POP_WIN_S, POP_GUARD_S, POP_CTX_S))
    lo, hi = max(0, c - k), min(len(x), c + k)
    if hi - lo < 4 * g:
        return None
    e = np.abs(lpc_residual(x[lo:hi]))
    pos = np.arange(len(e)) + lo
    win, ctx = np.abs(pos - c) <= w, (np.abs(pos - c) > g) & (np.arange(len(e)) >= LPC_ORDER)
    if not win.any() or ctx.sum() < 200:
        return None
    k_peak = int(np.argmax(np.where(win, e, -1.0)))
    peak, ref = float(e[k_peak]), float(np.percentile(e[ctx], 99.9))
    db = max(-99.0, 20 * math.log10(peak / max(ref, 1e-4))) if peak > 0 else -99.0
    return {"peak": round(peak, 4), "context_p999": round(ref, 4), "db": round(db, 1), "offset_ms": round((pos[k_peak] - c) / AUDIO_RATE * 1000, 1),
            "pop": bool(db >= POP_DB and peak >= POP_MIN)}


def _gray(rgb: np.ndarray) -> np.ndarray:
    return rgb.astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def flash_measure(gray: dict[int, np.ndarray], f: int) -> dict:
    """Flash / stray frame among the frames next to the cut at f (f-2 … f+1)."""

    def mad(a: int, b: int) -> float | None:
        return float(np.abs(gray[a] - gray[b]).mean()) if a in gray and b in gray else None

    worst = {"frame": None, "mad": 0.0, "luma_jump": 0.0, "flash": False, "why": ""}
    for g in range(f - 2, f + 2):
        if any(k not in gray for k in (g - 1, g, g + 1)):
            continue
        m_prev, m_next = mad(g - 1, g), mad(g, g + 1)
        lum = {k: float(gray[k].mean()) for k in (g - 1, g, g + 1)}
        dl_prev, dl_next = lum[g] - lum[g - 1], lum[g] - lum[g + 1]
        jump = min(abs(dl_prev), abs(dl_next)) if dl_prev * dl_next > 0 else 0.0
        around = [m for m in (mad(g - 2, g - 1), mad(g + 1, g + 2)) if m is not None]
        both = min(m_prev, m_next)
        stray = both >= FLASH_MAD and bool(around) and all(m < STABLE_SHARE * both for m in around)
        luma = jump >= FLASH_LUMA
        if (luma or stray, both) > (worst["flash"], worst["mad"]):
            why = ("brighter" if dl_prev > 0 else "darker") + f" than both neighbours by {jump:.0f}/255" if luma else (
                f"differs from both neighbours (mean |Δ| {both:.0f}/255) while they are stable — a stray frame" if stray else "")
            worst = {"frame": g, "mad": round(both, 1), "luma_jump": round(jump, 1), "flash": luma or stray, "why": why}
    return worst


def words_cut(clip: VideoClip, side: str, words_by_clip: dict, edges: dict, fps: Fraction) -> list[dict]:
    """Words of the clip's source that this edge of the clip cuts through (more than a frame deep).
    A word's extent is where the ASR times and the heard edges agree (their intersection): heard
    edges of neighbouring words overlap by design, and either source alone over-reports."""
    t = clip.src_out_us if side == "out" else clip.src_in_us
    tol = int(round(1e6 / float(fps))) + WORD_TOL_US
    hits = []
    for w in words_by_clip.get(clip.asset, []):
        hs, he = edges.get(w.i, (w.start_us, w.end_us))
        s, e = max(w.start_us, hs), min(w.end_us, he)
        if s + tol < t < e - tol:
            hits.append({"i": w.i, "text": w.text, "side": side, "clip": clip.id, "into_ms": round((t - s) / 1000), "left_ms": round((e - t) / 1000)})
    return hits


def duration_check(tl: Timeline, final: Path) -> dict:
    """Container and stream durations vs the timeline (render.verify's tolerances: video ±1 frame,
    audio ±1 frame + 30 ms of AAC priming/padding)."""
    fps = tb.parse_rate(tl.fps)
    want = float(Fraction(tl.duration_f) / fps)
    info = tools.ffprobe_json(final)
    dur = lambda d: float(d) if d not in (None, "N/A") else None  # noqa: E731
    v = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), {})
    a = next((s for s in info.get("streams", []) if s["codec_type"] == "audio"), None)
    got = {"timeline": round(want, 4), "video": dur(v.get("duration")), "audio": dur(a.get("duration")) if a else None,
           "container": dur(info.get("format", {}).get("duration"))}
    frame = 1 / float(fps)
    problems = []
    for key, tol in (("video", frame + 1e-3), ("audio", frame + 0.03), ("container", frame + 0.03)):
        if got[key] is None:
            problems.append(f"{key} duration missing" if key != "audio" or a is None else "audio duration unknown")
        elif abs(got[key] - want) > tol:
            problems.append(f"{key} {got[key]:.3f} s vs timeline {want:.3f} s ({(got[key] - want) * 1000:+.0f} ms)")
    return {"durations_s": got, "problems": problems}


# ------------------------------------------------------------------ strips


def _tile_frames(f: int, fps: Fraction, total: int) -> list[int]:
    """5 frames before the cut (ending on the last frame of the outgoing shot) and 5 from the cut on."""
    span = max(5, round(STRIP_SPAN_S * float(fps)))
    step = (span - 1) / 4
    return [f - 1 - round(k * step) for k in (4, 3, 2, 1, 0)] + [f + round(k * step) for k in range(5)]


def _edge_frames(start: int, end: int) -> list[int]:
    return sorted({int(round(v)) for v in np.linspace(start, max(start, end - 1), TILES)})


def waveform(final: Path, t0: float, t1: float, width: int, height: int = WAVE_H) -> np.ndarray:
    """showwavespic of [t0, t1) of the final mix as an RGB array (black when silent / no audio)."""
    blank = np.zeros((height, max(1, width), 3), dtype=np.uint8)
    if t1 - t0 < 0.02 or width < 2:
        return blank
    try:
        raw = tools.ffmpeg(["-ss", f"{t0:.4f}", "-t", f"{t1 - t0:.4f}", "-i", str(final), "-filter_complex",
                            f"[0:a:0]aformat=channel_layouts=mono,showwavespic=s={width}x{height}:colors=0x8fd3ff:draw=full:scale=sqrt",
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]).stdout
    except tools.ToolError:
        return blank
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3) if len(raw) == width * height * 3 else blank


def _escape(text: str) -> str:
    return sheets._escape(text).replace(",", "\\,")


def compose(tiles: list[np.ndarray | None], wave: np.ndarray, *, marker: bool, wave_x: int = 0) -> np.ndarray:
    th, tw = next((t.shape[:2] for t in tiles if t is not None), (int(TILE_W * 16 / 9), TILE_W))
    mid = MID_GAP if marker else GAP
    width = TILES * tw + (TILES - 2) * GAP + mid
    img = np.full((HEAD_H + th + GAP + WAVE_H, width, 3), 22, dtype=np.uint8)
    x = 0
    for k, t in enumerate(tiles):
        if t is not None:
            img[HEAD_H:HEAD_H + th, x:x + tw] = t[:th, :tw]
        x += tw + (mid if k == TILES // 2 - 1 else GAP)
    wy = HEAD_H + th + GAP
    ww = min(wave.shape[1], width - wave_x)
    img[wy:wy + WAVE_H, wave_x:wave_x + ww] = wave[:, :ww]
    if marker:
        cx = (TILES // 2) * tw + (TILES // 2 - 1) * GAP + mid // 2
        img[HEAD_H - 4:, cx - 1:cx + 1] = RED
    return img


def write_png(img: np.ndarray, out: Path, header: str, labels: list[tuple[int, int, str]], alert: bool) -> None:
    font = sheets._font()
    ff = f":fontfile='{font}'" if font else ""
    out.parent.mkdir(parents=True, exist_ok=True)
    h, w = img.shape[:2]
    with tempfile.TemporaryDirectory() as td:
        raw, txt = Path(td) / "strip.rgb", Path(td) / "header.txt"
        raw.write_bytes(np.ascontiguousarray(img).tobytes())
        txt.write_text(header)
        draws = [f"drawtext=textfile='{_escape(str(txt))}':expansion=none:x=8:y=7:fontsize=20:fontcolor={'0xff6a6a' if alert else 'white'}{ff}"]
        draws += [f"drawtext=text='{_escape(s)}':expansion=none:x={x}:y={y}:fontsize=15:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=3{ff}"
                  for x, y, s in labels]
        tools.ffmpeg(["-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", str(raw), "-vf", ",".join(draws),
                      "-frames:v", "1", str(out)])


def _tile_labels(frames: list[int], ref: int, fps: Fraction, tw: int, th: int, marker: bool) -> list[tuple[int, int, str]]:
    out, x = [], 0
    for k, f in enumerate(frames):
        d = f - ref
        s = f"{d:+d}f" if abs(d) <= 2 else f"{float(Fraction(d) / fps):+.2f}s"
        out.append((x + 4, HEAD_H + th - 24, s if marker else qa.tc(f, fps)))
        x += tw + ((MID_GAP if marker else GAP) if k == TILES // 2 - 1 else GAP)
    return out


# ------------------------------------------------------------------ run


def _summary(c: dict) -> list[str]:
    bits = []
    if c.get("pop", {}).get("pop"):
        bits.append(f"POP +{c['pop']['db']:.0f} dB")
    if c.get("flash", {}).get("flash"):
        bits.append("FLASH FRAME")
    if c.get("in_word"):
        bits.append("IN WORD " + ", ".join(f"“{w['text']}”" for w in c["in_word"]))
    return bits


def suspicion(c: dict) -> float:
    s = 0.0
    pop, flash = c.get("pop") or {}, c.get("flash") or {}
    s += (3.0 if pop.get("pop") else 0.0) + max(0.0, pop.get("db", 0.0)) / POP_DB
    s += (3.0 if flash.get("flash") else 0.0) + min(1.0, flash.get("mad", 0.0) / FLASH_MAD) * 0.5
    s += 2.0 * len(c.get("in_word") or [])
    return round(s, 3)


def check(ws, tl: Timeline, words: WordTable | None, edges: dict | None = None, *, final: Path | None = None) -> tuple[list[qa.GateResult], dict]:
    """Run every cut check on render/final.mp4, write qa/cuts/*.png + qa/cuts.json; return (gates, report)."""
    fps = tb.parse_rate(tl.fps)
    final = final or ws.path("render", "final.mp4")
    out_dir = ws.path("qa", "cuts")
    for old in out_dir.glob("*.png") if out_dir.exists() else []:
        old.unlink()
    total = tl.duration_f
    edges = edges or {}
    words_by_clip: dict[str, list] = {}
    for w in (words.words if words else []):
        words_by_clip.setdefault(w.clip, []).append(w)
    clips = {c.id: c for c in tl.video}
    cuts = cut_points(tl)

    # one decode for every strip tile and flash window, one for the audio
    edge_n = min(total, max(1, round(EDGE_S * float(fps))))
    head, tail = _edge_frames(0, edge_n), _edge_frames(total - edge_n, total)
    wanted = set(head) | set(tail)
    for c in cuts:
        c["tiles"] = _tile_frames(c["f"], fps, total)
        wanted |= set(c["tiles"]) | set(range(c["f"] - 4, c["f"] + 4))
    rgb = decode_frames(final, {f for f in wanted if 0 <= f < total}, TILE_W)
    gray = {f: _gray(v) for f, v in rgb.items()}
    audio = read_audio(final)

    report_cuts = []
    for n, c in enumerate(cuts, 1):
        f = c["f"]
        t = float(Fraction(f) / fps)
        vis, aud = intended(tl, f, fps)
        pop = pop_measure(audio, t) if not aud else None
        flash = flash_measure(gray, f) if not vis else None
        in_word = []
        if c["out_clip"]:
            in_word += words_cut(clips[c["out_clip"]], "out", words_by_clip, edges, fps)
            in_word += words_cut(clips[c["in_clip"]], "in", words_by_clip, edges, fps)
        entry = {"n": n, "f": f, "t": round(t, 3), "tc": qa.tc(f, fps), "kinds": c["kinds"], "label": " · ".join(c["label"]),
                 "intended": vis + aud, "pop": pop or {}, "flash": flash or {}, "in_word": in_word,
                 "strip": f"qa/cuts/cut_{n:03d}.png"}
        entry["suspicion"] = suspicion(entry)
        tiles = [rgb.get(k) for k in c["tiles"]]
        tw = TILE_W
        th = next((x.shape[0] for x in tiles if x is not None), int(TILE_W * 16 / 9))
        width = TILES * tw + (TILES - 2) * GAP + MID_GAP
        t0, t1 = t - STRIP_SPAN_S, t + STRIP_SPAN_S
        a0, a1 = max(0.0, t0), min(float(Fraction(total) / fps), t1)
        px = width / (t1 - t0)
        wave = waveform(final, a0, a1, int(round((a1 - a0) * px)))
        img = compose(tiles, wave, marker=True, wave_x=int(round((a0 - t0) * px)))
        alert = _summary(entry)
        header = f"cut {n} at {entry['tc']} ({entry['label']})" + (f"  —  {'; '.join(alert)}" if alert else "") + (
            f"  [intended: {', '.join(entry['intended'])}]" if entry["intended"] else "")
        write_png(img, ws.root / entry["strip"], header, _tile_labels(c["tiles"], f, fps, tw, th, True), bool(alert))
        report_cuts.append(entry)

    # head and tail: the opening and the ending (does the reel start / end inside a word?)
    edges_report = {}
    base = sorted((c for c in tl.video if c.id.startswith("v_")), key=lambda c: c.at_f)
    for name, frames, clip, side in (("head", head, base[0] if base else None, "in"), ("tail", tail, base[-1] if base else None, "out")):
        tiles = [rgb.get(k) for k in frames] + [None] * (TILES - len(frames))
        a0, a1 = float(Fraction(frames[0]) / fps), float(Fraction(frames[-1] + 1) / fps)
        width = TILES * TILE_W + (TILES - 1) * GAP
        img = compose(tiles, waveform(final, a0, a1, width), marker=False)
        in_word = words_cut(clip, side, words_by_clip, edges, fps) if clip else []
        rel = f"qa/cuts/{name}.png"
        header = (f"{'first' if name == 'head' else 'last'} {EDGE_S:.0f} s ({qa.tc(frames[0], fps)}–{qa.tc(frames[-1] + 1, fps)})"
                  + (f"  —  {'starts' if name == 'head' else 'ends'} inside “{in_word[0]['text']}”" if in_word else ""))
        th = next((x.shape[0] for x in tiles if x is not None), int(TILE_W * 16 / 9))
        write_png(img, ws.root / rel, header, _tile_labels(frames, 0, fps, TILE_W, th, False), bool(in_word))
        edges_report[name] = {"strip": rel, "in_word": in_word}

    duration = duration_check(tl, final)
    report = {"cuts": report_cuts, **edges_report, "duration": duration, "audio": bool(len(audio)),
              "thresholds": {"pop_db": POP_DB, "pop_min": POP_MIN, "pop_window_ms": POP_WIN_S * 1000, "flash_mad": FLASH_MAD,
                             "flash_luma": FLASH_LUMA, "word_tol_ms": round(1000 / float(fps) + WORD_TOL_US / 1000, 1)}}
    report["review_strips"] = review_strips(report)
    atomic_write_json(ws.path("qa", "cuts.json"), report)
    return gates(report), report


def review_strips(report: dict, limit: int = REVIEW_STRIPS) -> list[str]:
    """Head, tail and the `limit` most suspicious cuts (workspace-relative paths, in reel order)."""
    ranked = sorted(report.get("cuts", []), key=lambda c: (-c["suspicion"], c["f"]))[:limit]
    picked = [c["strip"] for c in sorted(ranked, key=lambda c: c["f"])]
    return [report["head"]["strip"], *picked, report["tail"]["strip"]] if "head" in report else picked


def gates(report: dict) -> list[qa.GateResult]:
    cuts = report["cuts"]
    pops = [c for c in cuts if c["pop"].get("pop")]
    flashes = [c for c in cuts if c["flash"].get("flash")]
    in_word = [(c["tc"], w) for c in cuts for w in c["in_word"]]
    in_word += [("0:00.00" if k == "head" else "end", w) for k in ("head", "tail") for w in report.get(k, {}).get("in_word", [])]
    worst_db = max((c["pop"].get("db", -99.0) for c in cuts if c["pop"]), default=None)
    dur = report["duration"]
    n = len(cuts)
    return [
        qa.GateResult("cut_pop", not pops, at=[c["tc"] for c in pops],
                      detail=(f"{len(pops)} of {n} cut(s) click/pop in the final mix: "
                              + ", ".join(f"{c['tc']} (+{c['pop']['db']:.0f} dB burst {c['pop']['offset_ms']:+.0f} ms from the cut)" for c in pops))
                      if pops else f"{n} cut(s) clean (worst {worst_db if worst_db is not None else 'n/a'} dB, limit +{POP_DB:.0f} dB)",
                      fix_hint="Re-render with edge fades / a short crossfade at the cut, or move the cut to a zero crossing in a pause.",
                      measured={"worst_db": worst_db, "pops": [{"tc": c["tc"], **c["pop"]} for c in pops]}),
        qa.GateResult("cut_flash", not flashes, at=[c["tc"] for c in flashes],
                      detail=(f"{len(flashes)} flash/stray frame(s) at cuts: " + "; ".join(f"{c['tc']} frame {c['flash']['frame']} {c['flash']['why']}" for c in flashes))
                      if flashes else f"no flash frames at {n} cut(s)",
                      fix_hint="Remove the one-frame leftover at the cut (the shot boundary is off by a frame).",
                      measured={"flashes": [{"tc": c["tc"], **c["flash"]} for c in flashes]}),
        qa.GateResult("cut_in_word", not in_word, at=[tc for tc, _ in in_word], fixable=True,
                      detail=(f"{len(in_word)} cut(s) inside a word: " + "; ".join(
                          f"{tc} {'end of' if w['side'] == 'out' else 'start of'} {w['clip']} cuts “{w['text']}” {w['into_ms']} ms in, {w['left_ms']} ms left"
                          for tc, w in in_word)) if in_word else "every cut lands between words",
                      fix_hint="Move the item boundary to a word edge: end the line after the whole word, or start the next line at a word start.",
                      measured={"words": [{"tc": tc, **w} for tc, w in in_word]}),
        qa.GateResult("duration_match", not dur["problems"], detail="; ".join(dur["problems"]) or
                      f"container/video/audio match the timeline ({dur['durations_s']['timeline']:.3f} s)", measured=dur["durations_s"]),
    ]
