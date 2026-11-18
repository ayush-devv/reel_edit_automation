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
from reel import mix, tools
from reel.config import AUDIO_RATE, ffmpeg_path
from reel.schemas.plan import Ease
from reel.schemas.timeline import Keyframe, Timeline, VideoClip
from reel.workspace import tmp_path_for

EDGE_FADE_S = 0.005
CRF = 16
MUSIC_FADE_IN_S = 0.5
MUSIC_FADE_OUT_S = 1.5


class RenderError(RuntimeError):
    pass


def unsupported(tl: Timeline) -> list[str]:
    """Timeline features this renderer cannot draw yet (each names the step that adds it)."""
    out = []
    for c in tl.video:
        if not c.id.startswith(("v_", "br_")):
            out.append(f"video clip {c.id}: unknown clip kind")
        elif not (0.25 <= c.speed <= 4.0):
            out.append(f"video clip {c.id}: speed {c.speed} outside 0.25–4×")
        elif c.x or c.y:
            out.append(f"video clip {c.id}: pans render in build step 7")
    out += [f"audio clip {a.id}: unknown role {a.role}" for a in tl.audio if a.role not in ("voice", "sfx", "music")]
    out += [f"transition {t.id}: unknown type {t.type.value}" for t in tl.transitions if t.type.value not in TRANSITIONS]
    out += [f"effect {e.id}: unknown type {e.type}" for e in tl.effects if e.type not in EFFECTS]
    return out


# ------------------------------------------------------------------ transitions (frame-local)
# Each transition only changes the frames of the two shots around the cut: the out-going shot's
# last ⌊N/2⌋ frames and the in-coming shot's first ⌈N/2⌉ frames. Shots keep their exact frame
# ranges, need no handles, and audio is untouched — sync and layout stay exact.

EFFECTS = {"shake", "rgb_split", "light_leak", "exposure_pulse"}
TRANSITIONS = {"cut", "zoom", "whip", "blur", "dip_to_black", "dip_to_white", "glitch"}
ZOOM_PEAK = 1.25


def _windows(c: VideoClip, tl: Timeline) -> tuple[tuple[str, int] | None, tuple[str, int] | None]:
    """(head, tail): the transition type and frame count touching this clip's start / end."""
    head = tail = None
    for t in tl.transitions:
        if t.type.value == "cut":
            continue
        if t.at_f == c.at_f:
            head = (t.type.value, max(1, t.frames - t.frames // 2))
        if t.at_f == c.at_f + c.dur_f:
            tail = (t.type.value, max(1, t.frames // 2))
    return head, tail


def _ramp(head: tuple[str, int] | None, tail: tuple[str, int] | None, dur: int, kinds: set[str], var: str = "N") -> str | None:
    """Effect weight 0..1 over clip-relative frames: 1 on the cut frame, 0 outside the window."""
    terms = []
    if tail and tail[0] in kinds:
        h = tail[1]
        terms.append(f"clip(({var}-{dur - h}+1)/{h},0,1)")
    if head and head[0] in kinds:
        h = head[1]
        terms.append(f"clip(1-{var}/{h},0,1)")
    if not terms:
        return None
    return terms[0] if len(terms) == 1 else f"max({terms[0]},{terms[1]})"


def _value_at(kfs: list[Keyframe], f: int) -> float:
    v = 1.0
    for k in sorted(kfs, key=lambda k: k.f):
        if k.f <= f:
            v = k.v
    return v


def with_transition_zoom(c: VideoClip, head, tail) -> VideoClip:
    """Zoom transitions become scale keyframes (rendered by the same zoom path as punch-ins)."""
    kfs = list(c.scale)
    if tail and tail[0] == "zoom":
        start = max(0, c.dur_f - tail[1] - 1)
        v0 = _value_at(kfs, start)
        kfs = [k for k in kfs if k.f < start] + [Keyframe(f=start, v=v0, ease=Ease.hold), Keyframe(f=c.dur_f - 1, v=v0 * ZOOM_PEAK, ease=Ease.ease_in)]
    if head and head[0] == "zoom":
        end = min(head[1], c.dur_f - 1)
        v1 = _value_at(kfs, end)
        kfs = [Keyframe(f=0, v=v1 * ZOOM_PEAK, ease=Ease.hold), Keyframe(f=end, v=v1, ease=Ease.ease_out)] + [k for k in kfs if k.f > end]
    return c.model_copy(update={"scale": kfs}) if kfs != list(c.scale) else c


WHIP_ZOOM = 1.4


def transition_graph(k: int, inp: str, out: str, c: VideoClip, head, tail, w: int, h: int, fps: Fraction) -> list[str]:
    """Filter statements turning [inp] into [out] with blur / whip / dip windows applied."""
    stmts, cur = [], inp
    blur_k = _ramp(head, tail, c.dur_f, {"blur", "zoom"})
    if blur_k:
        stmts += [f"[{cur}]split[ta{k}][tb{k}]", f"[tb{k}]gblur=sigma=28[tbb{k}]",
                  f"[ta{k}][tbb{k}]blend=all_expr='A*(1-({blur_k}))+B*({blur_k})'[tbl{k}]"]
        cur = f"tbl{k}"
    if any(x and x[0] == "whip" for x in (head, tail)):
        # a whip pan never shows black: enlarge, pan inside the enlarged frame, smear horizontally;
        # the out-going shot pans to its right edge, the in-coming one continues from its left edge
        kt = _ramp(None, tail, c.dur_f, {"whip"}, var="n") or "0"
        kh = _ramp(head, None, c.dur_f, {"whip"}, var="n") or "0"
        m = _ramp(head, tail, c.dur_f, {"whip"})
        sw, sh = round(w * WHIP_ZOOM / 2) * 2, round(h * WHIP_ZOOM / 2) * 2
        stmts += [f"[{cur}]split[wa{k}][wb{k}]",
                  f"[wb{k}]scale={sw}:{sh},crop={w}:{h}:x='({sw - w}/2)*(1+({kt})-({kh}))':y={(sh - h) // 2},dblur=angle=0:radius=120[wbb{k}]",
                  f"[wa{k}][wbb{k}]blend=all_expr='if(gt({m},0),B,A)'[tw{k}]"]
        cur = f"tw{k}"
    g = _ramp(head, tail, c.dur_f, {"glitch"})
    if g:  # RGB split + noise + a horizontal tear on the frames next to the cut
        stmts += [f"[{cur}]split[ga{k}][gb{k}]",
                  f"[gb{k}]rgbashift=rh=-18:bh=18:edge=wrap,noise=alls=45:allf=t,crop=iw-24:ih:12:0,scale={w}:{h}[gbb{k}]",
                  f"[ga{k}][gbb{k}]blend=all_expr='if(gt({g},0.15),B,A)'[tg{k}]"]
        cur = f"tg{k}"
    fades = []
    for kind, colour in (("dip_to_black", "black"), ("dip_to_white", "white")):
        if tail and tail[0] == kind:
            fades.append(f"fade=t=out:start_frame={c.dur_f - tail[1]}:nb_frames={tail[1]}:color={colour}")
        if head and head[0] == kind:
            fades.append(f"fade=t=in:start_frame=0:nb_frames={head[1]}:color={colour}")
    stmts.append(f"[{cur}]{','.join(fades) or 'null'}[{out}]")
    return stmts


# ------------------------------------------------------------------ footage effects (after the cut, whole frame)

LEAK_COLOURS = ("0xff7a1a", "0xffc23d", "0xff3d6e", "0x000000")


def effects_graph(tl: Timeline, inp: str, out: str, fps: Fraction) -> list[str]:
    """Grain + vignette over the whole reel, then each timed effect on its own frame window.
    Windowed effects are computed on a branch and shown only inside their window (overlay enable)."""
    w, h = tl.width, tl.height
    stmts, cur, k = [], inp, 0

    def nxt() -> str:
        nonlocal k
        k += 1
        return f"fx{k}"

    look = []
    if tl.grade.vignette > 0:
        look.append(f"vignette=angle={0.2 + 0.6 * tl.grade.vignette:.3f}")
    if tl.grade.grain > 0:
        look.append(f"noise=c0s={round(4 + 30 * tl.grade.grain)}:c0f=t")
    if look:
        o = nxt()
        stmts.append(f"[{cur}]{','.join(look)}[{o}]")
        cur = o
    for e in sorted(tl.effects, key=lambda e: e.start_f):
        s0, s1, i = e.start_f, max(e.start_f + 1, e.end_f), e.intensity
        n_on = f"between(n,{s0},{s1 - 1})"
        o = nxt()
        if e.type == "shake":  # decaying, non-repeating jitter inside a slightly enlarged frame
            a = max(2, round(0.025 * h * i / 2) * 2)
            decay = f"max(0,1-(n-{s0})/{s1 - s0})"
            jx = f"{a}+{a}*(sin(n*2.3)+0.5*sin(n*5.1+1))/1.5*{decay}"
            jy = f"{a}+{a}*(sin(n*1.7+2)+0.5*sin(n*4.3))/1.5*{decay}"
            stmts += [f"[{cur}]split[{o}a][{o}b]",
                      f"[{o}b]crop={w - 2 * a}:{h - 2 * a}:x='clip({jx},0,{2 * a})':y='clip({jy},0,{2 * a})',scale={w}:{h}[{o}c]",
                      f"[{o}a][{o}c]overlay=0:0:enable='{n_on}'[{o}]"]
        elif e.type == "rgb_split":
            d = max(2, round(4 + 18 * i))
            stmts.append(f"[{cur}]rgbashift=rh=-{d}:bh={d}:edge=smear:enable='{n_on}'[{o}]")
        elif e.type == "exposure_pulse":  # peaks on the first word, gone in ~0.25 s
            t0 = float(Fraction(s0) / fps)
            stmts.append(f"[{cur}]eq=brightness='{0.35 * i:.3f}*exp(-pow((t-{t0:.4f})/0.09,2))':eval=frame[{o}]")
        elif e.type == "light_leak":  # a soft moving gradient, screen-blended, fading in and out over the window
            t0, t1 = float(Fraction(s0) / fps), float(Fraction(s1) / fps)
            dur = float(Fraction(tl.duration_f) / fps) + 1
            qw, qh = w // 4 // 2 * 2, h // 4 // 2 * 2
            cols = ":".join(f"c{j}={c}" for j, c in enumerate(LEAK_COLOURS))
            op = f"{0.75 * i:.3f}*sin(PI*clip((T-{t0:.4f})/{t1 - t0:.4f},0,1))"
            stmts += [f"gradients=s={qw}x{qh}:{cols}:n=4:x0=0:y0=0:x1={qw}:y1={qh}:speed=0.03:seed=7:r={fps.numerator}/{fps.denominator}:d={dur:.3f},"
                      f"scale={w}:{h},gblur=sigma=30,format=gbrp[{o}l]",
                      f"[{cur}]split[{o}a][{o}b]", f"[{o}b]format=gbrp[{o}g]",
                      f"[{o}g][{o}l]blend=all_expr='A*(1-({op}))+(255-(255-A)*(255-B)/255)*({op})':shortest=1,format=yuv420p[{o}c]",
                      f"[{o}a][{o}c]overlay=0:0:enable='{n_on}'[{o}]"]
        else:
            raise RenderError(f"effect {e.id}: unknown type {e.type}")
        cur = o
    stmts.append(f"[{cur}]null[{out}]")
    return stmts


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


def lut_chain(lut: Path | None) -> str:
    """Per-clip colour LUT in RGB, with explicit bt709 matrices both ways (ADR-0023)."""
    if lut is None:
        return ""
    f = str(lut).replace("\\", "/").replace("'", "\\'")
    return (f"scale=in_color_matrix=bt709:in_range=tv:out_range=pc,format=gbrp,lut3d=file='{f}':interp=tetrahedral,"
            f"scale=in_range=pc:out_color_matrix=bt709:out_range=tv,")


def crop_share(src_w: int, src_h: int, out_w: int, out_h: int) -> float:
    """Width of the cover crop window as a share of the source width (1.0 = nothing cut at the sides)."""
    s = max(out_w / src_w, out_h / src_h)
    return min(1.0, out_w / (src_w * s))


def clip_shots(c: VideoClip, fps: Fraction, faces: dict | None, scenes: dict | None, src_size: tuple[int, int] | None = None,
               out_size: tuple[int, int] = (1080, 1920), speakers: dict | None = None) -> list:
    """Per-shot framing for a base clip (camera cuts inside it get their own framing; wide two-shots
    follow the active speaker when perception/speakers.json has them; see reel.framing)."""
    from reel import framing

    fallback = _face_centre(faces, c.asset)
    samples = ((faces or {}).get(c.asset) or {}).get("samples", [])
    cuts = ((scenes or {}).get(c.asset) or {}).get("cuts_us", [])
    if not samples:
        return [framing.Shot(0, fallback, None)]
    crop_w = crop_share(*src_size, *out_size) if src_size else 1.0
    return framing.shots(c, fps, cuts, samples, fallback, crop_w=crop_w, speakers=(speakers or {}).get(c.asset))


def crop_x_expr(shots: list, crops: list[tuple[int, int, int, int]], sw: int, out_w: int) -> str:
    """Crop x over clip-relative frames `n`: a jump at every shot start, linear moves along tracked paths."""
    kfs = []
    for s, cr in zip(shots, crops):
        if s.path:
            pts = [(f, min(max(round(cx * sw - out_w / 2), 0), sw - out_w)) for f, cx in s.path]
            kfs.append(Keyframe(f=s.start_f, v=pts[0][1], ease=Ease.hold))
            kfs += [Keyframe(f=f, v=x, ease=Ease.linear) for f, x in pts if f > s.start_f]
        else:
            kfs.append(Keyframe(f=s.start_f, v=cr[2], ease=Ease.hold))
    if len({k.v for k in kfs}) == 1:
        return str(kfs[0].v)
    return scale_expr(kfs, var="n")


def fill_chain(src_w: int, src_h: int, out_w: int, out_h: int) -> str:
    """The whole frame fitted to the width over a blurred, darkened cover copy (blurred at ¼ size: cheap)."""
    fg_h = min(out_h, round(src_h * out_w / src_w / 2) * 2)
    qw, qh = out_w // 4 // 2 * 2, out_h // 4 // 2 * 2
    return (f"split[fb][ff];[fb]scale={qw}:{qh}:force_original_aspect_ratio=increase,crop={qw}:{qh},gblur=sigma=6,"
            f"scale={out_w}:{out_h},eq=brightness=-0.08:saturation=0.85[fbg];[ff]scale={out_w}:{fg_h}:flags=lanczos[ffg];"
            f"[fbg][ffg]overlay=0:{(out_h - fg_h) // 2}")


def _geometry(c: VideoClip, src_w: int, src_h: int, out_w: int, out_h: int, fps: Fraction, centre,
              lut: Path | None = None, tag: str = "") -> str:
    """`centre` is one (cx, cy) or a list of framing.Shot (per-shot crop: static, tracked or fill)."""
    from reel import framing

    shots = centre if isinstance(centre, list) else [framing.Shot(0, centre, None)]
    crops = [cover_crop(src_w, src_h, out_w, out_h, s.centre) for s in shots]
    sw, sh = crops[0][0], crops[0][1]
    starts = [s.start_f for s in shots]
    ys = [cr[3] for cr in crops]
    x = crop_x_expr(shots, crops, sw, out_w)
    y = framing.piecewise(ys, starts) if len(set(ys)) > 1 else str(ys[0])
    chain = f"scale={sw}:{sh}:flags=lanczos,crop={out_w}:{out_h}:x='{x}':y='{y}',{lut_chain(lut)}format=yuv420p"
    if c.scale and any(k.v != 1.0 for k in c.scale):
        # zoom on the face of the shot on screen (face position inside the cropped frame)
        fxs = [(s.centre[0] * sw - cr[2]) / out_w for s, cr in zip(shots, crops)]
        fys = [(s.centre[1] * sh - cr[3]) / out_h for s, cr in zip(shots, crops)]
        fx = framing.piecewise(fxs, starts, var="on", fmt="{:.4f}")
        fy = framing.piecewise(fys, starts, var="on", fmt="{:.4f}")
        z = scale_expr(c.scale)
        chain += (f",zoompan=z='{z}':d=1:s={out_w}x{out_h}:fps={fps.numerator}/{fps.denominator}"
                  f":x='clip(({fx})*iw-iw/zoom/2,0,iw-iw/zoom)':y='clip(({fy})*ih-ih/zoom/2,0,ih-ih/zoom)'")
    fills = [(s.start_f, shots[k + 1].start_f if k + 1 < len(shots) else c.dur_f) for k, s in enumerate(shots) if s.layout == "fill"]
    if not fills:
        return chain
    # fill shots: a second branch shows the whole frame; it replaces the crop only during those shots
    t = tag or "x"
    fill = fill_chain(src_w, src_h, out_w, out_h).replace("[fb]", f"[fb{t}]").replace("[ff]", f"[ff{t}]").replace(
        "[fbg]", f"[fbg{t}]").replace("[ffg]", f"[ffg{t}]")
    on = "+".join(f"between(n,{a},{b - 1})" for a, b in fills)
    return (f"split[gc{t}][gf{t}];[gc{t}]{chain}[gcc{t}];[gf{t}]{fill},{lut_chain(lut)}format=yuv420p[gff{t}];"
            f"[gcc{t}][gff{t}]overlay=0:0:enable='{on}'")


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


def atempo_chain(rate: float) -> list[float]:
    """atempo factors (each 0.5–2.0) whose product is `rate`."""
    out = []
    while rate > 2.0:
        out.append(2.0)
        rate /= 2.0
    while rate < 0.5:
        out.append(0.5)
        rate /= 0.5
    return out + [rate]


def duck_expr(regions_f: list[list[int]], fps: Fraction, depth_db: float, attack_ms: int, release_ms: int) -> str:
    """Music gain (linear) over time: −depth_db while speech plays, ramping down over `attack`
    before each region and back up over `release` after it."""
    if not regions_f:
        return "1"
    a, r = attack_ms / 1000, release_ms / 1000
    terms = []
    for s_f, e_f in regions_f:
        s, e = float(Fraction(s_f) / fps), float(Fraction(e_f) / fps)
        terms.append(f"clip(min((t-{s - a:.4f})/{a:.4f},({e + r:.4f}-t)/{r:.4f}),0,1)")
    d = terms[0]
    for t in terms[1:]:
        d = f"max({d},{t})"
    return f"pow(10,-{depth_db:.2f}*({d})/20)"


def build_command(tl: Timeline, root: Path, out: Path, *, faces: dict | None = None, crf: int = CRF,
                  room_tone: dict[str, tuple[int, int, float]] | None = None, finish_audio: bool = True,
                  luts: dict[str, Path] | None = None, stems_dir: Path | None = None, scenes: dict | None = None,
                  speakers: dict | None = None) -> list[str]:
    """`room_tone`: per mezzanine asset, the (start_us, end_us, dBFS) stretch to loop under its segments.
    `finish_audio=False` renders the raw cut voice only (used by sync tests)."""
    problems = unsupported(tl)
    if problems:
        raise RenderError("timeline uses features the base renderer does not support yet: " + "; ".join(problems))
    fps = tb.parse_rate(tl.fps)
    base = sorted((c for c in tl.video if c.id.startswith("v_")), key=lambda c: c.at_f)
    voice = {a.id[2:]: a for a in tl.audio if a.role == "voice"}  # a_<shot> pairs with v_<shot>
    extras = [a for a in tl.audio if a.role in ("sfx", "music")]
    room_tone = (room_tone or {}) if finish_audio else {}
    if not base:
        raise RenderError("timeline has no video clips")
    cursor = 0
    for c in base:
        if c.at_f != cursor:
            raise RenderError(f"base clips must be back to back: {c.id} starts at {c.at_f}, expected {cursor}")
        cursor += c.dur_f
    if cursor != tl.duration_f:
        raise RenderError(f"base clips cover {cursor} frames, timeline says {tl.duration_f}")
    total_samples = tb.frame_to_sample(tl.duration_f, fps)

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
    # audio inputs: one unseeked input per asset (sample-exact trims) — mezzanines, SFX, music
    audio_input: dict[str, int] = {}
    for asset in [c.asset for c in base] + [a.asset for a in extras]:
        if asset not in audio_input:
            audio_input[asset] = len(base) + len(audio_input)
            uri = Path(tl.assets[asset].uri)
            args += ["-i", str(uri if uri.is_absolute() else root / uri)]

    brolls = sorted((c for c in tl.video if c.id.startswith("br_")), key=lambda c: c.at_f)
    broll_input: dict[str, int] = {}
    for c in brolls:
        uri = Path(tl.assets[c.asset].uri)
        uri = uri if uri.is_absolute() else root / uri
        if c.asset not in sizes:
            sizes[c.asset] = source_size(uri)
        in_f = tb.us_to_frame(c.src_in_us, fps)
        broll_input[c.id] = len(base) + len(audio_input) + len(broll_input)
        if in_f > 0:
            args += ["-ss", f"{float((Fraction(in_f) - Fraction(1, 2)) / fps):.6f}"]
        args += ["-i", str(uri)]

    uses: dict[str, int] = {}
    for c in base:
        uses[c.asset] = uses.get(c.asset, 0) + 1 + (1 if c.asset in room_tone else 0)
    for a in extras:
        uses[a.asset] = uses.get(a.asset, 0) + 1
    graph: list[str] = []
    a_label: dict[str, list[str]] = {}
    for asset, n in uses.items():
        k = audio_input[asset]
        labels = [f"src_{k}_{j}" for j in range(n)]
        graph.append(f"[{k}:a]aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     + (f"asplit={n}" + "".join(f"[{l}]" for l in labels) if n > 1 else f"anull[{labels[0]}]"))
        a_label[asset] = labels

    bounds = tb.audio_bounds(tb.layout_segments([c.dur_f for c in base]), fps)
    concat_in, rt_in = [], []
    for k, (c, (s0, s1)) in enumerate(zip(base, bounds)):
        w, h = sizes[c.asset]
        head, tail = _windows(c, tl)
        cz = with_transition_zoom(c, head, tail)
        if c.speed == 1.0:
            timing = f"trim=end_frame={c.dur_f},setpts=PTS-STARTPTS"
        else:  # retime, then resample to the project grid and cut to the exact output length
            src_frames = int(c.dur_f * c.speed) + 2
            timing = (f"trim=end_frame={src_frames},setpts=(PTS-STARTPTS)/{c.speed},"
                      f"fps={fps.numerator}/{fps.denominator},trim=end_frame={c.dur_f},setpts=PTS-STARTPTS")
        graph.append(f"[{k}:v]{timing},"
                     f"{_geometry(cz, w, h, tl.width, tl.height, fps, clip_shots(c, fps, faces, scenes, (w, h), (tl.width, tl.height), speakers), (luts or {}).get(c.asset), tag=str(k))},setsar=1[g{k}]")
        graph += transition_graph(k, f"g{k}", f"v{k}", c, head, tail, tl.width, tl.height, fps)
        a = voice.get(c.id[2:])
        if a is None:
            raise RenderError(f"no voice audio for {c.id}")
        start = tb.frame_to_sample(tb.us_to_frame(a.src_in_us, fps), fps)
        n = s1 - s0
        fade_out = max(0.0, n / AUDIO_RATE - EDGE_FADE_S)
        gain = f",volume={a.gain_db}dB" if a.gain_db else ""
        src_n = round(n * a.speed)
        tempo = "".join(f",atempo={f:.6f}" for f in atempo_chain(a.speed)) + f",atrim=end_sample={n}" if a.speed != 1.0 else ""
        graph.append(f"[{a_label[c.asset].pop(0)}]atrim=start_sample={start}:end_sample={start + src_n},asetpts=PTS-STARTPTS{tempo},"
                     f"afade=t=in:d={EDGE_FADE_S},afade=t=out:st={fade_out:.6f}:d={EDGE_FADE_S}{gain},apad=whole_len={n}[a{k}]")
        concat_in.append(f"[v{k}][a{k}]")
        if room_tone:
            if c.asset in room_tone:
                r0, r1, _db = room_tone[c.asset]
                rs, re_ = tb.us_to_sample(r0), tb.us_to_sample(r1)
                # loop the raw stretch (fading it would dip the room every loop); noise has no pitch to click
                graph.append(f"[{a_label[c.asset].pop(0)}]atrim=start_sample={rs}:end_sample={re_},asetpts=PTS-STARTPTS,"
                             f"aloop=loop=-1:size={re_ - rs},atrim=end_sample={n},asetpts=PTS-STARTPTS[rt{k}]")
            else:
                graph.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=end_sample={n},aformat=sample_fmts=fltp[rt{k}]")
            rt_in.append(f"[rt{k}]")
    graph.append("".join(concat_in) + f"concat=n={len(base)}:v=1:a=1[vcat][vraw]")
    # full-frame b-roll: time-shifted to its slot and laid over the cut (the voice underneath is untouched)
    cur = "vcat"
    for j, c in enumerate(brolls):
        w, h = sizes[c.asset]
        nxt = f"vb{j}"
        graph.append(f"[{broll_input[c.id]}:v]trim=end_frame={c.dur_f},setpts=PTS-STARTPTS+{c.at_f}*{fps.denominator}/{fps.numerator}/TB,"
                     f"{_geometry(c, w, h, tl.width, tl.height, fps, (0.5, 0.5), (luts or {}).get(c.asset))},setsar=1[brv{j}]")
        graph.append(f"[{cur}][brv{j}]overlay=0:0:eof_action=pass:repeatlast=0[{nxt}]")
        cur = nxt
    graph += effects_graph(tl, cur, "vout", fps)

    if not finish_audio:
        graph.append("[vraw]anull[aout]")
    else:
        floors = [db for (_s, _e, db) in room_tone.values()]
        floor = min(floors) if floors else None
        graph.append(f"[vraw]{mix.voice_chain(floor)}[voice]")
        # buses: dialogue (voice + room tone), music, sfx — mixed for the deliverable, optionally
        # also written as stems for the NLE package
        buses: dict[str, list[str]] = {"dialogue": ["[voice]"], "music": [], "sfx": []}
        if rt_in:
            graph.append("".join(rt_in) + f"concat=n={len(rt_in)}:v=0:a=1,{mix.room_tone_chain(floor)}[rt]")
            buses["dialogue"].append("[rt]")
        duck = tl.ducking[0] if tl.ducking else None
        for j, a in enumerate(extras):
            at = tb.frame_to_sample(a.at_f, fps)
            length = tb.frame_to_sample(a.at_f + a.dur_f, fps) - at
            src0 = tb.us_to_sample(a.src_in_us)
            chain = f"atrim=start_sample={src0}:end_sample={src0 + length},asetpts=PTS-STARTPTS,volume={a.gain_db}dB"
            if a.role == "music":
                fade_out = max(0.0, length / AUDIO_RATE - MUSIC_FADE_OUT_S)
                chain += f",afade=t=in:d={MUSIC_FADE_IN_S},afade=t=out:st={fade_out:.3f}:d={MUSIC_FADE_OUT_S}"
                if duck and duck.target_role == "music":
                    expr = duck_expr(duck.regions_f, fps, duck.depth_db, duck.attack_ms, duck.release_ms)
                    chain += f",asetpts=PTS+{at}/SR/TB,volume='{expr}':eval=frame,asetpts=PTS-STARTPTS"
            chain += f",adelay=delays={at}S:all=1,apad=whole_len={total_samples},atrim=end_sample={total_samples}"
            graph.append(f"[{a_label[a.asset].pop(0)}]{chain}[x{j}]")
            buses[a.role].append(f"[x{j}]")
        mix_in = []
        for bus, ins in buses.items():
            if not ins:
                if not stems_dir:
                    continue
                graph.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=end_sample={total_samples},aformat=sample_fmts=fltp[{bus}_sum]")
            elif len(ins) == 1:
                graph.append(f"{ins[0]}anull[{bus}_sum]")
            else:
                graph.append("".join(ins) + f"amix=inputs={len(ins)}:normalize=0:duration=first:dropout_transition=0[{bus}_sum]")
            if stems_dir:
                graph.append(f"[{bus}_sum]asplit[{bus}_mix][{bus}_stem]")
                mix_in.append(f"[{bus}_mix]")
            else:
                mix_in.append(f"[{bus}_sum]")
        if len(mix_in) > 1:
            graph.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:normalize=0:duration=first:dropout_transition=0[aout]")
        else:
            graph.append(f"{mix_in[0]}anull[aout]")

    args += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
             "-r", f"{fps.numerator}/{fps.denominator}", "-fps_mode", "cfr", *encode_args(out, crf=crf)]
    if stems_dir and finish_audio:
        stems_dir.mkdir(parents=True, exist_ok=True)
        for bus in ("dialogue", "music", "sfx"):
            args += ["-map", f"[{bus}_stem]", "-c:a", "pcm_s24le", "-ar", str(AUDIO_RATE), str(stems_dir / f"{bus}.wav")]
    return args


def render_base(tl: Timeline, root: Path, out: Path, *, faces: dict | None = None,
                room_tone: dict[str, tuple[int, int, float]] | None = None, finish_audio: bool = True,
                luts: dict[str, Path] | None = None, stems_dir: Path | None = None, scenes: dict | None = None,
                speakers: dict | None = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path_for(out)
    cmd = build_command(tl, root, tmp, faces=faces, room_tone=room_tone, finish_audio=finish_audio, luts=luts, stems_dir=stems_dir,
                        scenes=scenes, speakers=speakers)
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
