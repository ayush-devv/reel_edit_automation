"""Delivery variants + client review copy (build step 10b).

The 9:16 master (export/reel.mp4) serves Reels, Shorts and TikTok. Other aspect ratios are not
crops of the finished reel: the base is cropped around the face and the overlay is re-rendered
at the new size, so captions and titles are laid out for that frame (never cut off).
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

from reel import overlay, tools
from reel.schemas.timeline import Timeline
from reel.workspace import tmp_path_for

PROFILES = {
    "feed_4x5": {"size": (1080, 1350), "safe": {"top": 90, "bottom": 140, "left": 60, "right": 60}, "label": "Instagram/Facebook feed 4:5"},
    "square": {"size": (1080, 1080), "safe": {"top": 80, "bottom": 120, "left": 60, "right": 60}, "label": "square 1:1"},
}
PLATFORM_MAX_S = {"Instagram Reels": 180, "YouTube Shorts": 180, "TikTok": 600}
REVIEW_W = 540


def crop_y(props: dict, src_h: int, out_h: int) -> int:
    """Top of the crop window. The face comes first (kept at ~40 % from the top); text already
    burned into the footage (brand banners, logos) is kept inside the window when the face allows it."""
    faces = [s["box"] for s in props.get("faces", []) if s.get("box")]
    zones = [z for s in props.get("faces", []) for z in s.get("text", [])]
    lo, hi = 0, src_h - out_h  # allowed range for the window top
    if faces:
        f = sorted(faces, key=lambda b: b["y"])[len(faces) // 2]
        f0, f1 = f["y"] * src_h, (f["y"] + f["h"]) * src_h
        lo, hi = max(lo, int(f1 - out_h)), min(hi, int(f0))  # whole face inside
        target = (f0 + f1) / 2 - 0.40 * out_h
    else:
        target = 0.45 * src_h - out_h / 2
    if zones:
        z0 = min(z["y"] for z in zones) * src_h
        z1 = max(z["y"] + z["h"] for z in zones) * src_h
        zlo, zhi = int(z1 - out_h), int(z0)  # window tops that contain every text zone
        if max(lo, zlo) <= min(hi, zhi):
            lo, hi = max(lo, zlo), min(hi, zhi)
    return int(min(max(target, lo), hi)) if lo <= hi else int(min(max(target, 0), src_h - out_h))


def make_variant(ws, tl: Timeline, name: str) -> dict:
    prof = PROFILES[name]
    w, h = prof["size"]
    out_dir = ws.path("render", "variants", name)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    props_main = json.loads(ws.path("render", "overlay.props.json").read_text())
    y = crop_y(props_main, tl.height, h)
    base = out_dir / "base.mov"
    tmp = tmp_path_for(base)
    tools.ffmpeg(["-y", "-i", str(ws.path("render", "base.mov")), "-vf", f"crop={w}:{h}:0:{y}", "-c:v", "prores_ks", "-profile:v", "2",
                  "-pix_fmt", "yuv422p10le", "-c:a", "copy", str(tmp)])
    tmp.replace(base)
    vtl = tl.model_copy(update={"width": w, "height": h})
    props = copy.deepcopy(props_main) | {"width": w, "height": h, "safe": prof["safe"]}
    # faces/text zones move with the crop: shift and rescale their y into the variant frame
    for span in props["faces"]:
        for key in ("box",):
            b = span.get(key)
            if b:
                span[key] = {**b, "y": (b["y"] * tl.height - y) / h, "h": b["h"] * tl.height / h}
        span["text"] = [{**z, "y": (z["y"] * tl.height - y) / h, "h": z["h"] * tl.height / h} for z in span.get("text", [])]
    ov = out_dir / "overlay.mov"
    overlay.render_overlay(props, ov, public_dir=ws.root)
    final = ws.path("export", "variants", f"reel_{name}.mp4")
    meta = overlay.composite(vtl, base, ov, final)
    return meta | {"variant": name, "crop_y": y, "variant_s": round(time.time() - t0, 1)}


def review_copy(ws, tl: Timeline, verdict: str | None) -> dict:
    """Small, watermarked, timecoded copy for client notes ("0:12 make this faster")."""
    src = ws.path("render", "final.mp4")
    out = ws.path("export", "review", "review.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path_for(out)
    font = render_font()
    fontarg = f":fontfile='{font}'" if font else ""
    label = "REVIEW COPY - not for publishing"
    vf = (f"scale={REVIEW_W}:-2,drawtext=text='%{{pts\\:hms}}'{fontarg}:x=12:y=12:fontsize=26:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=6,"
          f"drawtext=text='{label}'{fontarg}:x=(w-tw)/2:y=h-th-18:fontsize=20:fontcolor=white@0.85:box=1:boxcolor=black@0.5:boxborderw=6")
    tools.ffmpeg(["-y", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp)])
    tmp.replace(out)
    return {"review": str(out.relative_to(ws.root)), "size_mb": round(out.stat().st_size / 1e6, 2)}


def render_font() -> str | None:
    from reel import sheets

    f = sheets._font()
    return str(f) if f else None


def platform_notes(duration_s: float) -> list[str]:
    return [f"{p}: {duration_s:.0f} s exceeds the {m} s limit" for p, m in PLATFORM_MAX_S.items() if duration_s > m]
