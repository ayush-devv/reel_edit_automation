"""ffmpeg base-layer renderer (ADR-0004): timeline → picture + voice, frame- and sample-exact.

One ffmpeg graph per timeline:
- video: each base clip is input-seeked half a frame before its first frame (the mezzanine is
  all-intra ProRes at the project fps, so the seek is exact), trimmed by frame count,
  cover-scaled to the output size and centred on the median face; punch-in scale keyframes
  become a per-frame zoom expression.
- audio: trimmed by sample from the cumulative time-map (`timebase.audio_bounds`), so cut
  boundaries never drift, with 5 ms fades at each edge against clicks.

Captions/overlays are the Remotion layer (build step 6). Music, SFX, ducking, b-roll,
transitions and speed changes arrive in build step 7 — a timeline that uses them is rejected
here rather than silently rendered without them.
"""

from __future__ import annotations

import time
from fractions import Fraction
from pathlib import Path

from reel import timebase as tb
from reel import tools
from reel.config import AUDIO_RATE, ffmpeg_path
from reel.schemas.plan import Ease
from reel.schemas.timeline import Keyframe, Timeline, VideoClip
from reel.workspace import tmp_path_for

EDGE_FADE_S = 0.005
CRF = 16


class RenderError(RuntimeError):
    pass


def unsupported(tl: Timeline) -> list[str]:
    """Timeline features this renderer cannot draw yet (each names the step that adds it)."""
    out = []
    for c in tl.video:
        if not c.id.startswith("v_"):
            out.append(f"video clip {c.id}: b-roll renders in build step 7")
        elif c.speed != 1.0:
            out.append(f"video clip {c.id}: speed changes render in build step 7")
        elif c.x or c.y:
            out.append(f"video clip {c.id}: pans render in build step 7")
    out += [f"audio clip {a.id}: {a.role} renders in build step 7" for a in tl.audio if a.role != "voice"]
    out += [f"transition {t.id}: {t.type.value} renders in build step 7" for t in tl.transitions if t.type.value != "cut"]
    if tl.ducking:
        out.append("ducking renders in build step 7")
    return out


def _ease(e: Ease, t: str) -> str:
    return {Ease.linear: t, Ease.ease_in: f"({t})*({t})", Ease.ease_out: f"(1-(1-({t}))*(1-({t})))",
            Ease.ease_in_out: f"({t})*({t})*(3-2*({t}))"}.get(e, t)


def scale_expr(kfs: list[Keyframe], var: str = "on") -> str:
    """Piecewise zoom expression over the clip-relative frame number `var`.

    Between keyframes i and i+1 the value moves from v_i to v_{i+1} with the ease of i+1;
    `hold` means it jumps at f_{i+1}. Before the first keyframe: v_0; after the last: v_last.
    """
    kfs = sorted(kfs, key=lambda k: k.f)
    expr = f"{kfs[-1].v:.6g}"
    for a, b in reversed(list(zip(kfs, kfs[1:]))):
        if b.ease == Ease.hold or b.f <= a.f:
            seg = f"{a.v:.6g}"
        else:
            t = f"({var}-{a.f})/{b.f - a.f}"
            seg = f"{a.v:.6g}+({b.v - a.v:.6g})*{_ease(b.ease, t)}"
        expr = f"if(lt({var},{b.f}),{seg},{expr})"
    return f"if(lt({var},{kfs[0].f}),{kfs[0].v:.6g},{expr})"


def _face_centre(faces: dict | None, clip_asset: str) -> tuple[float, float]:
    box = ((faces or {}).get(clip_asset) or {}).get("median_box")
    if not box:
        return 0.5, 0.5
    return box["x"] + box["w"] / 2, box["y"] + box["h"] / 2


def cover_crop(src_w: int, src_h: int, out_w: int, out_h: int, centre: tuple[float, float]) -> tuple[int, int, int, int]:
    """Scale to cover the output, crop around `centre` (normalised source coords): (sw, sh, x, y)."""
    s = max(out_w / src_w, out_h / src_h)
    sw, sh = max(out_w, round(src_w * s / 2) * 2), max(out_h, round(src_h * s / 2) * 2)
    cx, cy = centre
    x = min(max(round(cx * sw - out_w / 2), 0), sw - out_w)
    y = min(max(round(cy * sh - out_h / 2), 0), sh - out_h)
    return sw, sh, x, y


def face_box_out(faces: dict | None, asset: str, src_w: int, src_h: int, out_w: int, out_h: int) -> dict | None:
    """Median face box in normalised OUTPUT coordinates (after the cover crop), for overlay layout."""
    box = ((faces or {}).get(asset) or {}).get("median_box")
    if not box:
        return None
    sw, sh, x, y = cover_crop(src_w, src_h, out_w, out_h, _face_centre(faces, asset))
    return {"x": round((box["x"] * sw - x) / out_w, 4), "y": round((box["y"] * sh - y) / out_h, 4),
            "w": round(box["w"] * sw / out_w, 4), "h": round(box["h"] * sh / out_h, 4)}


def _geometry(c: VideoClip, src_w: int, src_h: int, out_w: int, out_h: int, fps: Fraction, centre: tuple[float, float]) -> str:
    sw, sh, x, y = cover_crop(src_w, src_h, out_w, out_h, centre)
    cx, cy = centre
    chain = f"scale={sw}:{sh}:flags=lanczos,crop={out_w}:{out_h}:{x}:{y},format=yuv420p"
    if c.scale and any(k.v != 1.0 for k in c.scale):
        # face position inside the cropped frame, so the punch-in keeps the face centred
        fx, fy = (cx * sw - x) / out_w, (cy * sh - y) / out_h
        z = scale_expr(c.scale)
        chain += (f",zoompan=z='{z}':d=1:s={out_w}x{out_h}:fps={fps.numerator}/{fps.denominator}"
                  f":x='clip({fx:.4f}*iw-iw/zoom/2,0,iw-iw/zoom)':y='clip({fy:.4f}*ih-ih/zoom/2,0,ih-ih/zoom)'")
    return chain


def source_size(path: Path) -> tuple[int, int]:
    st = tools.ffprobe_json(path, ["-select_streams", "v:0"])["streams"][0]
    return int(st["width"]), int(st["height"])


def encode_args(out: Path, *, crf: int = CRF) -> list[str]:
    """`.mov` → ProRes 422 + PCM intermediate (no generation loss before the composite);
    anything else → the delivery encode (H.264 High, yuv420p, bt709, AAC 48 kHz, faststart)."""
    if out.suffix.lower() == ".mov":
        return ["-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le", "-vendor", "apl0",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
                "-c:a", "pcm_s16le", "-ar", str(AUDIO_RATE), "-ac", "2", str(out)]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", "256k", "-ar", str(AUDIO_RATE), "-ac", "2", "-movflags", "+faststart", str(out)]


def build_command(tl: Timeline, root: Path, out: Path, *, faces: dict | None = None, crf: int = CRF) -> list[str]:
    problems = unsupported(tl)
    if problems:
        raise RenderError("timeline uses features the base renderer does not support yet: " + "; ".join(problems))
    fps = tb.parse_rate(tl.fps)
    base = sorted(tl.video, key=lambda c: c.at_f)
    voice = {a.src.item: a for a in tl.audio if a.role == "voice" and a.src}
    if not base:
        raise RenderError("timeline has no video clips")
    cursor = 0
    for c in base:
        if c.at_f != cursor:
            raise RenderError(f"base clips must be back to back: {c.id} starts at {c.at_f}, expected {cursor}")
        cursor += c.dur_f
    if cursor != tl.duration_f:
        raise RenderError(f"base clips cover {cursor} frames, timeline says {tl.duration_f}")

    args: list[str] = [str(ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    sizes: dict[str, tuple[int, int]] = {}
    # video inputs: one seeked input per clip
    for c in base:
        uri = root / tl.assets[c.asset].uri
        if c.asset not in sizes:
            sizes[c.asset] = source_size(uri)
        in_f = tb.us_to_frame(c.src_in_us, fps)
        if in_f > 0:
            args += ["-ss", f"{float((Fraction(in_f) - Fraction(1, 2)) / fps):.6f}"]
        args += ["-i", str(uri)]
    # audio inputs: one unseeked input per asset (sample-exact trims)
    audio_input: dict[str, int] = {}
    for c in base:
        if c.asset not in audio_input:
            audio_input[c.asset] = len(base) + len(audio_input)
            args += ["-i", str(root / tl.assets[c.asset].uri)]

    uses: dict[str, int] = {}
    for c in base:
        uses[c.asset] = uses.get(c.asset, 0) + 1
    graph: list[str] = []
    a_label: dict[str, list[str]] = {}
    for asset, n in uses.items():
        k = audio_input[asset]
        labels = [f"src_{k}_{j}" for j in range(n)]
        graph.append(f"[{k}:a]aresample={AUDIO_RATE}," + (f"asplit={n}" + "".join(f"[{l}]" for l in labels) if n > 1 else f"anull[{labels[0]}]"))
        a_label[asset] = labels

    bounds = tb.audio_bounds(tb.layout_segments([c.dur_f for c in base]), fps)
    concat_in = []
    for k, (c, (s0, s1)) in enumerate(zip(base, bounds)):
        w, h = sizes[c.asset]
        graph.append(f"[{k}:v]trim=end_frame={c.dur_f},setpts=PTS-STARTPTS,"
                     f"{_geometry(c, w, h, tl.width, tl.height, fps, _face_centre(faces, c.asset))},setsar=1[v{k}]")
        a = voice.get(c.src.item)
        if a is None:
            raise RenderError(f"no voice audio for {c.id}")
        start = tb.frame_to_sample(tb.us_to_frame(a.src_in_us, fps), fps)
        n = s1 - s0
        fade_out = max(0.0, n / AUDIO_RATE - EDGE_FADE_S)
        gain = f",volume={a.gain_db}dB" if a.gain_db else ""
        graph.append(f"[{a_label[c.asset].pop(0)}]atrim=start_sample={start}:end_sample={start + n},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={EDGE_FADE_S},afade=t=out:st={fade_out:.6f}:d={EDGE_FADE_S}{gain},apad=whole_len={n}[a{k}]")
        concat_in.append(f"[v{k}][a{k}]")
    graph.append("".join(concat_in) + f"concat=n={len(base)}:v=1:a=1[vout][aout]")

    args += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
             "-r", f"{fps.numerator}/{fps.denominator}", "-fps_mode", "cfr", *encode_args(out, crf=crf)]
    return args


def render_base(tl: Timeline, root: Path, out: Path, *, faces: dict | None = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path_for(out)
    cmd = build_command(tl, root, tmp, faces=faces)
    t0 = time.time()
    tools.run(cmd)
    tmp.replace(out)
    return verify(tl, out) | {"render_s": round(time.time() - t0, 1)}


def verify(tl: Timeline, path: Path) -> dict:
    """Frame count must equal the timeline; audio must last as long as the picture (±1 frame)."""
    fps = tb.parse_rate(tl.fps)
    info = tools.ffprobe_json(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    frames = len(tools.ffprobe_frame_times(path))
    a_dur = float(a["duration"]) if a and a.get("duration") else 0.0
    v_dur = float(Fraction(tl.duration_f) / fps)
    res = {"frames": frames, "frames_expected": tl.duration_f, "size": f"{v['width']}x{v['height']}",
           "audio_s": round(a_dur, 4), "video_s": round(v_dur, 4)}
    problems = []
    if frames != tl.duration_f:
        problems.append(f"frame count {frames} != timeline {tl.duration_f}")
    if (int(v["width"]), int(v["height"])) != (tl.width, tl.height):
        problems.append(f"size {res['size']} != {tl.width}x{tl.height}")
    if abs(a_dur - v_dur) > float(1 / fps) + 0.03:  # AAC priming/padding tolerance
        problems.append(f"audio {a_dur:.3f}s vs video {v_dur:.3f}s")
    if problems:
        raise RenderError("render verification failed: " + "; ".join(problems))
    return res
