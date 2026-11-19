"""Per-shot reframing (found on real multi-camera podcast footage): one median face per clip
puts the speaker at the edge or shows the back of a head after every camera switch.

Each base clip is split at the source's scene cuts. Per shot (after Google AutoFlip and openshorts):
- `crop`, static: the face barely moves → centred on the median face (most talking-head shots);
- `crop`, tracked: the face moves more than a dead zone → a smoothed, speed-capped path that follows
  one face (the one nearest the previous position, so a second face never steals the frame);
- `fill`: two prominent faces too far apart for one vertical crop → the whole frame, fitted to the
  width over a blurred, darkened copy of itself (nobody is cut in half);
- speaker crops: in a would-be `fill` shot with active-speaker data (perception/speakers.json),
  static crops on whoever is talking, switching at word gaps (≥ 1 s apart); stretches where the
  speaker is uncertain (both talking, laughter) keep `fill`.
A shot inherits the previous shot's centre when no face is visible.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from fractions import Fraction

from reel import timebase as tb
from reel.schemas.timeline import VideoClip

DEFAULT_CENTRE = (0.5, 0.45)


DEAD_ZONE = 0.25  # face travel (5th–95th percentile) under this share of the crop width → static shot
MAX_SPEED = 0.6  # tracked crop moves at most this many crop widths per second
SMOOTH_S = 0.5  # gaussian smoothing (sigma) of the tracked path, seconds
TRACK_STEP_S = 0.5  # one path keyframe per this many seconds (keeps the ffmpeg expression short)
FILL_MIN_RATIO = 0.5  # second face at least this share of the largest face's area counts as "prominent"
FILL_MIN_SHARE = 0.5  # share of samples with two prominent faces that don't fit one crop → fill
MIN_SUBSHOT_US = 1_000_000  # speaker-switch cuts inside a wide shot are at least this far apart
SPEAKER_MIN_COVER = 0.5  # speakers.json must cover at least this share of the shot …
SPEAKER_MIN_SPEECH = 0.6  # … and name the speaker for at least this share of it (else: whole-frame fill)


@dataclass
class Shot:
    start_f: int  # clip-relative output frame where this shot starts
    centre: tuple[float, float]  # normalised source coords
    box: dict | None  # median largest-face box (normalised source coords)
    layout: str = "crop"  # crop | fill
    path: list[tuple[int, float]] | None = None  # tracked crop: (clip-relative frame, centre x) keyframes


def _largest(faces: list[dict]) -> dict | None:
    return max(faces, key=lambda b: b["w"] * b["h"]) if faces else None


def _cx(b: dict) -> float:
    return b["x"] + b["w"] / 2


def needs_fill(window: list[dict], crop_w: float) -> bool:
    """Two prominent faces whose span is wider than one vertical crop, in most samples."""
    if not window or crop_w >= 1.0:
        return False
    wide = 0
    for s in window:
        fs = sorted(s.get("faces") or [], key=lambda b: b["w"] * b["h"], reverse=True)
        if len(fs) >= 2 and fs[1]["w"] * fs[1]["h"] >= FILL_MIN_RATIO * fs[0]["w"] * fs[0]["h"]:
            span = max(fs[0]["x"] + fs[0]["w"], fs[1]["x"] + fs[1]["w"]) - min(fs[0]["x"], fs[1]["x"])
            wide += span > crop_w * 0.95
    return wide >= FILL_MIN_SHARE * len(window)


def follow(window: list[dict], start: float) -> list[tuple[int, float]]:
    """(t_us, centre x) of one face through the shot: the face nearest the previous position."""
    out, cur = [], start
    for s in window:
        fs = s.get("faces") or []
        if not fs:
            continue
        b = min(fs, key=lambda b: abs(_cx(b) - cur))
        cur = _cx(b)
        out.append((s["t_us"], cur))
    return out


def smooth_path(pts: list[tuple[int, float]], crop_w: float) -> list[tuple[int, float]]:
    """Zero-phase gaussian smoothing (the whole shot is known, so no lag) + a speed cap."""
    import numpy as np

    if len(pts) < 3:
        return pts
    t = np.array([p[0] for p in pts], dtype=float) / 1e6
    x = np.array([p[1] for p in pts], dtype=float)
    x = np.array([statistics.median(x[max(0, k - 1):k + 2]) for k in range(len(x))])  # drop single-sample jumps
    dt = max(float(np.median(np.diff(t))), 1e-3)
    sigma = SMOOTH_S / dt
    r = max(1, int(3 * sigma))
    kern = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    xs = np.convolve(np.pad(x, r, mode="edge"), kern / kern.sum(), mode="valid")
    cap = MAX_SPEED * crop_w
    for k in range(1, len(xs)):
        step = cap * (t[k] - t[k - 1])
        xs[k] = min(max(xs[k], xs[k - 1] - step), xs[k - 1] + step)
    return [(int(tt * 1e6), float(v)) for tt, v in zip(t, xs)]


def _median_box(boxes: list[dict]) -> dict:
    return {k: statistics.median(bx[k] for bx in boxes) for k in ("x", "y", "w", "h")}


def speaker_box(window: list[dict], track_box: dict) -> dict:
    """The speaker's face box in this stretch: per sample, the face nearest the track's centre
    (faces.json boxes, so overlay face spans match what the crop shows); else the track's own box."""
    tx = _cx(track_box)
    near = [b for s in window if (fs := s.get("faces")) and abs(_cx(b := min(fs, key=lambda f: abs(_cx(f) - tx))) - tx) < 0.1]
    return _median_box(near) if near else dict(track_box)


def speaker_cuts(a: int, b: int, speakers: dict | None, min_us: int = MIN_SUBSHOT_US) -> list[tuple[int, int | None]] | None:
    """A wide two-shot [a, b) split on the active speaker: [(start_us, track | None = whole frame)].

    None when speakers.json can't drive it (no data, or tracked speech is not most of the shot's
    speech). Segment edges are already at word gaps (perception/speakers.py); stretches shorter
    than `min_us` join the previous one, so no cut is shorter than that and none falls mid-word."""
    segs = [(max(a, g["start_us"]), min(b, g["end_us"]), g["track"]) for g in (speakers or {}).get("segments") or []
            if g["start_us"] < b and g["end_us"] > a]
    if not segs:
        return None
    total = sum(e - s for s, e, _ in segs)
    tracked = sum(e - s for s, e, t in segs if t is not None)
    if total < SPEAKER_MIN_COVER * (b - a) or tracked < SPEAKER_MIN_SPEECH * total:
        return None
    parts = [(a if k == 0 else s, t) for k, (s, _, t) in enumerate(segs)]  # uncovered head/tail joins its neighbour
    merged: list[list] = []
    for k, (s, t) in enumerate(parts):
        end = parts[k + 1][0] if k + 1 < len(parts) else b
        if merged and (merged[-1][1] == t or end - s < min_us):
            continue  # same label, or too short: the previous stretch carries on
        merged.append([s, t])
    while len(merged) > 1 and merged[1][0] - merged[0][0] < min_us:  # a short opener joins the next stretch
        merged[1][0] = merged[0][0]
        merged.pop(0)
    return [(s, t) for s, t in merged]


def only_visible_face(a: int, b: int, speakers: dict | None, tracks: dict) -> dict | None:
    """The single visible-face track of an analysed multi-face stretch covering most of [a, b) — the signature of an
    over-the-shoulder angle (speakers.json keeps only faces the landmarker could read). None otherwise."""
    if not speakers or b <= a:
        return None
    covered = sum(max(0, min(b, pe) - max(a, ps)) for ps, pe in speakers.get("pieces") or [])
    if covered < 0.5 * (b - a):
        return None
    vis = [t for t in tracks.values() if t.get("start_us", 0) < b and t.get("end_us", 0) > a]
    return vis[0] if len(vis) == 1 else None


def shots(c: VideoClip, fps: Fraction, cuts_us: list[int], samples: list[dict], fallback: tuple[float, float] = DEFAULT_CENTRE,
          crop_w: float = 1.0, speakers: dict | None = None) -> list[Shot]:
    """`crop_w`: width of the vertical crop window as a share of the source width (1.0 = no horizontal crop).
    `speakers`: this clip's speakers.json entry — a wide two-shot then crops to whoever is talking."""
    src0, src1 = c.src_in_us, c.src_out_us
    bounds = [src0] + [u for u in sorted(cuts_us) if src0 < u < src1] + [src1]
    out: list[Shot] = []
    prev = fallback
    tracks = {t["id"]: t for t in (speakers or {}).get("tracks") or []}

    def add(t_us: int, shot: Shot) -> None:
        shot.start_f = tb.src_to_out_frame(t_us - src0, fps, c.speed, c.speed_to, src1 - src0)
        if out and shot.start_f <= out[-1].start_f:
            return
        if shot.path:
            shot.path = [(max(f, shot.start_f), x) for f, x in shot.path]
        out.append(shot)

    for a, b in zip(bounds, bounds[1:]):
        window = [s for s in samples if a <= s["t_us"] < b]
        boxes = [bx for s in window if (bx := _largest(s.get("faces") or []))]
        layout, path = "crop", None
        one = only_visible_face(a, b, speakers, tracks)
        if boxes and one is not None and crop_w < 1.0:
            # over-the-shoulder angle: the second "face" is the back of a head (the landmarker found no face there):
            # frame the one person whose face we can see, never the back of a head or a two-shot fill
            box = dict(one["box"])
            add(a, Shot(start_f=0, centre=(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2), box=box, layout="crop"))
            prev = (box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
            continue
        if boxes:
            box = _median_box(boxes)
            centre = (box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
            if needs_fill(window, crop_w):
                layout = "fill"
                cuts = speaker_cuts(a, b, speakers) if crop_w < 1.0 else None
                if cuts and any(t in tracks for _, t in cuts):
                    ends = [s for s, _ in cuts[1:]] + [b]
                    for (s, t), e in zip(cuts, ends):
                        if t in tracks:
                            sb = speaker_box([x for x in window if s <= x["t_us"] < e], tracks[t]["box"])
                            add(s, Shot(0, (sb["x"] + sb["w"] / 2, sb["y"] + sb["h"] / 2), sb, "crop"))
                        else:
                            add(s, Shot(0, centre, box, "fill"))
                    prev = centre
                    continue
            elif crop_w < 1.0:
                pts = follow(window, centre[0])
                xs = sorted(p[1] for p in pts)
                if len(xs) >= 4 and xs[int(0.95 * (len(xs) - 1))] - xs[int(0.05 * (len(xs) - 1))] > DEAD_ZONE * crop_w:
                    sm = smooth_path(pts, crop_w)
                    step = max(1, round(TRACK_STEP_S / max((sm[1][0] - sm[0][0]) / 1e6, 1e-3))) if len(sm) > 1 else 1
                    keep = sm[::step] + ([sm[-1]] if (len(sm) - 1) % step else [])
                    path = [(max(0, tb.src_to_out_frame(tu - src0, fps, c.speed, c.speed_to, src1 - src0)), x) for tu, x in keep]
        else:
            box, centre = None, prev
        add(a, Shot(start_f=0, centre=centre, box=box, layout=layout, path=path))
        prev = centre
    return out or [Shot(0, fallback, None)]


def piecewise(values: list[float], starts: list[int], var: str = "n", fmt: str = "{:.0f}") -> str:
    """Step expression over clip-relative frames: value k from starts[k] until starts[k+1]."""
    expr = fmt.format(values[-1])
    for v, nxt in zip(reversed(values[:-1]), reversed(starts[1:])):
        expr = f"if(lt({var},{nxt}),{fmt.format(v)},{expr})"
    return expr
