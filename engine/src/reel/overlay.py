"""Remotion overlay + ffmpeg composite (ADR-0004, build step 6).

The overlay is a transparent ProRes 4444 (straight alpha) rendered by `renderer/` from the
remotion-owned timeline fields; ffmpeg composites it onto the ProRes base and makes the one
lossy delivery encode, carrying the base audio.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from reel import config, mix, render, tools
from reel import timebase as tb
from reel.schemas.timeline import Timeline
from reel.workspace import atomic_write_json, file_fingerprint, hash_inputs, tmp_path_for

RENDERER_DIR = config.REPO_ROOT / "renderer"
REMOTION_BIN = RENDERER_DIR / "node_modules" / ".bin" / "remotion"
SAFE = {"top": 220, "bottom": 420, "right": 130, "left": 60}  # px on 1080×1920 (Reels/Shorts UI)


class OverlayError(RuntimeError):
    pass


def available() -> bool:
    return REMOTION_BIN.exists() and shutil.which("node") is not None


def renderer_fingerprint() -> str:
    """Changes to the overlay components must re-render overlays."""
    files = sorted(p for p in (RENDERER_DIR / "src").rglob("*") if p.is_file()) + [RENDERER_DIR / "package-lock.json"]
    return hash_inputs([file_fingerprint(p) for p in files if p.exists()])


def _overlaps(a: list[float], b: list[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def text_zones(ocr: dict | None, asset: str, src_w: int, src_h: int, out_w: int, out_h: int, faces: dict | None,
               min_presence: float = 0.3) -> list[dict]:
    """Burned-in text already in the footage (titles, logos, lower thirds), in normalised OUTPUT
    coordinates, so our titles and captions never sit on top of it. Only text that persists
    (≥ 30 % of OCR samples) and has ≥ 3 letters counts; timecodes and numbers are ignored."""
    items = [it for it in ((ocr or {}).get(asset) or {}).get("items", [])
             if sum(ch.isalpha() for ch in it["text"]) >= 3 and it.get("score", 1) >= 0.6]
    samples = len({it["t_us"] for it in ((ocr or {}).get(asset) or {}).get("items", [])}) or 1
    groups: list[dict] = []  # merged box + the sample times it was seen at
    for it in items:
        g = next((g for g in groups if _overlaps(g["box"], it["box"])), None)
        if g is None:
            groups.append({"box": list(it["box"]), "t": {it["t_us"]}})
        else:
            g["box"] = [min(g["box"][0], it["box"][0]), min(g["box"][1], it["box"][1]), max(g["box"][2], it["box"][2]), max(g["box"][3], it["box"][3])]
            g["t"].add(it["t_us"])
    sw, sh, x, y = render.cover_crop(src_w, src_h, out_w, out_h, render._face_centre(faces, asset))
    out = []
    for g in groups:
        if len(g["t"]) / samples < min_presence:
            continue
        x0, y0, x1, y1 = g["box"]
        bx0, by0 = max(0.0, (x0 * sw - x) / out_w), max(0.0, (y0 * sh - y) / out_h)
        bx1, by1 = min(1.0, (x1 * sw - x) / out_w), min(1.0, (y1 * sh - y) / out_h)
        if bx1 > bx0 and by1 > by0:
            out.append({"x": round(bx0, 4), "y": round(by0, 4), "w": round(bx1 - bx0, 4), "h": round(by1 - by0, 4)})
    return out


def build_props(tl: Timeline, root: Path, faces: dict | None, ocr: dict | None = None, scenes: dict | None = None) -> dict:
    """Overlay props. Face spans are per shot (camera cuts inside a clip get their own framing)."""
    fps = tb.parse_rate(tl.fps)
    spans, sizes = [], {}
    for c in sorted((c for c in tl.video if c.id.startswith("v_")), key=lambda c: c.at_f):
        if c.asset not in sizes:
            sizes[c.asset] = render.source_size(root / tl.assets[c.asset].uri)
        sw_, sh_ = sizes[c.asset]
        zones = text_zones(ocr, c.asset, sw_, sh_, tl.width, tl.height, faces)
        shots = render.clip_shots(c, fps, faces, scenes, (sw_, sh_), (tl.width, tl.height))
        for k, shot in enumerate(shots):
            start = c.at_f + shot.start_f
            end = c.at_f + (shots[k + 1].start_f if k + 1 < len(shots) else c.dur_f)
            box = None
            if shot.box and shot.layout == "fill":  # whole frame fitted to the width, centred vertically
                b, s = shot.box, tl.width / sw_
                top = (tl.height - sh_ * s) / 2
                box = {"x": round(b["x"], 4), "y": round((top + b["y"] * sh_ * s) / tl.height, 4),
                       "w": round(b["w"], 4), "h": round(b["h"] * sh_ * s / tl.height, 4)}
            elif shot.box:
                sw, sh, x, y = render.cover_crop(sw_, sh_, tl.width, tl.height, shot.centre)
                b = shot.box
                box = {"x": round((b["x"] * sw - x) / tl.width, 4), "y": round((b["y"] * sh - y) / tl.height, 4),
                       "w": round(b["w"] * sw / tl.width, 4), "h": round(b["h"] * sh / tl.height, 4)}
            if end > start:
                spans.append({"start_f": start, "end_f": end, "box": box, "text": zones})
    d = tl.model_dump(mode="json")
    from reel import emoji

    for g in d["graphics"]:
        if g["kind"] == "emoji_pop":
            g["uri"] = emoji.svg_uri(g["emoji"]) or ""
    d["graphics"] = [g for g in d["graphics"] if g["kind"] != "emoji_pop" or g["uri"]]
    return {"fps": float(fps), "width": tl.width, "height": tl.height, "duration_f": tl.duration_f,
            "captions": d["captions"], "titles": d["titles"], "flashes": d["flashes"], "pips": d["pips"], "graphics": d["graphics"], "faces": spans, "safe": SAFE}


def render_overlay(props: dict, out: Path, *, timeout_s: int = 1800, public_dir: Path | None = None,
                   frames: tuple[int, int] | None = None) -> dict:
    """`frames` = (first, last) inclusive renders only that window (behind-the-subject titles)."""
    if not available():
        raise OverlayError(f"Remotion renderer not installed: run `npm ci` in {RENDERER_DIR}")
    out.parent.mkdir(parents=True, exist_ok=True)
    props_file = out.with_suffix(".props.json")
    atomic_write_json(props_file, props)
    tmp = tmp_path_for(out)
    cmd = [str(REMOTION_BIN), "render", "src/index.ts", "Overlay", str(tmp), f"--props={props_file}",
           "--codec=prores", "--prores-profile=4444", "--pixel-format=yuva444p10le", "--image-format=png",
           "--log=error", "--overwrite"] + ([f"--public-dir={public_dir}"] if public_dir else []) \
        + ([f"--frames={frames[0]}-{frames[1]}"] if frames else [])
    env = {**os.environ, "REMOTION_DISABLE_TELEMETRY": "1"}
    t0 = time.time()
    import subprocess

    proc = subprocess.run(cmd, cwd=RENDERER_DIR, capture_output=True, text=True, timeout=timeout_s, env=env)
    if proc.returncode != 0:
        raise OverlayError(f"Remotion render failed ({proc.returncode}): {(proc.stderr or proc.stdout)[-1500:]}")
    tmp.replace(out)
    return {"overlay_s": round(time.time() - t0, 1)}


def composite(tl: Timeline, base: Path, overlay: Path, out: Path, *, behind: dict | None = None) -> dict:
    """Base (ProRes 422 + PCM) + overlay (ProRes 4444 straight alpha) → delivery MP4.

    `behind` = {"layer": mov, "matte": grey video, "start_f", "end_f"}: a title rendered for that
    window sits on the base, and the person (base pixels where the matte is white) goes back over it.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    fps = tb.parse_rate(tl.fps)
    tmp = tmp_path_for(out)
    t0 = time.time()
    before = mix.measure(base)  # loudnorm pass 1 on the finished mix
    n = tb.frame_to_sample(tl.duration_f, fps)  # loudnorm pads its output: keep the exact sample count
    inputs = ["-i", str(base), "-i", str(overlay)]
    if behind:
        s0, s1 = behind["start_f"], behind["end_f"]
        off = f"{s0}*{fps.denominator}/{fps.numerator}/TB"
        inputs += ["-i", str(behind["layer"]), "-i", str(behind["matte"])]
        video = (f"[0:v]split[b0][b1];[2:v]format=yuva444p10le,setpts=PTS-STARTPTS+{off}[bh];"
                 f"[b0][bh]overlay=0:0:format=auto:alpha=straight:eof_action=pass:repeatlast=0[t1];"
                 f"[b1]trim=start_frame={s0}:end_frame={s1},setpts=PTS-STARTPTS,format=yuva444p10le[bw];[3:v]format=gray[m];"
                 f"[bw][m]alphamerge,setpts=PTS-STARTPTS+{off}[person];"
                 f"[t1][person]overlay=0:0:format=auto:eof_action=pass:repeatlast=0[t2];"
                 f"[1:v]format=yuva444p10le[ov];[t2][ov]overlay=0:0:format=auto:alpha=straight:eof_action=pass,format=yuv420p[v];")
    else:
        video = "[1:v]format=yuva444p10le[ov];[0:v][ov]overlay=0:0:format=auto:alpha=straight:eof_action=pass,format=yuv420p[v];"
    tools.ffmpeg(["-y", *inputs,
                  "-filter_complex", video + f"[0:a]{mix.loudnorm_filter(before)},apad=whole_len={n},atrim=end_sample={n},asetpts=N/SR/TB[a]",
                  "-map", "[v]", "-map", "[a]", "-r", f"{fps.numerator}/{fps.denominator}", "-fps_mode", "cfr",
                  *render.encode_args(tmp)])
    after = mix.measure(tmp)
    problems = mix.check_delivery(after)
    if problems:
        raise OverlayError("delivery loudness out of spec: " + "; ".join(problems))
    tmp.replace(out)
    return render.verify(tl, out) | {"composite_s": round(time.time() - t0, 1), "lufs_in": before["input_i"],
                                     "lufs": after["input_i"], "true_peak_dbtp": after["input_tp"], "behind_title": bool(behind)}
