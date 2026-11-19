"""Frame-exact splicing of all-intra movies (roadmap G1.5: partial re-render).

base.mov (ProRes 422) and overlay.mov (ProRes 4444) are all-intra: every frame is a keyframe, so a stretch can be
replaced by stream copy at any frame, with no re-encode and no keyframe grid. The kept stretches of the old movie are
cut into pieces with an exact frame count (input seek a quarter frame past the first frame's timestamp, then
`-frames:v N`), and the pieces and the newly rendered chunks are joined by the concat demuxer with no in/out points
(in/out points shift the timeline at a seam). Every splice is verified — frame count and a timestamp on every frame of
the project grid — and the caller falls back to a full render on any failure.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from reel import config, tools
from reel.workspace import tmp_path_for


def _q(p: Path) -> str:
    return "'" + str(p).replace("'", "'\\''") + "'"


def kept_ranges(chunks: list[tuple[int, int, Path]], total_f: int) -> list[tuple[int, int]]:
    """Frame ranges [start, end) of the old movie that stay, around the inclusive chunk ranges."""
    out, pos = [], 0
    for a, b, _p in sorted(chunks):
        if a > pos:
            out.append((pos, a))
        pos = b + 1
    if pos < total_f:
        out.append((pos, total_f))
    return out


def frame_times(path: Path) -> list[float]:
    r = tools.run([str(config.ffprobe_path()), "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                   "-of", "csv=p=0", str(path)])
    return [float(x) for x in r.stdout.decode().split() if x.strip()]


def stream_format(path: Path) -> tuple:
    st = tools.ffprobe_json(path)["streams"][0]
    return (st.get("codec_name"), st.get("codec_tag_string"), st.get("profile"), st.get("pix_fmt"), st.get("width"), st.get("height"))


def frame_count(path: Path) -> int:
    return len(frame_times(path))


def cut(old: Path, start_f: int, end_f: int, out: Path, fps: Fraction) -> None:
    """Frames [start_f, end_f) of an all-intra movie, by stream copy. Output-side seek: with stream copy it drops every
    packet before the point (exact for all-intra video); an input-side seek would pull in the frame before it."""
    seek = ["-ss", f"{float((Fraction(start_f) - Fraction(1, 4)) / fps):.9f}"] if start_f else []
    tools.ffmpeg(["-y", "-i", str(old), *seek, "-map", "0", "-frames:v", str(end_f - start_f), "-c", "copy",
                  "-avoid_negative_ts", "make_zero", str(out)])


def splice(old: Path, chunks: list[tuple[int, int, Path]], out: Path, *, total_f: int, fps: Fraction) -> None:
    """Write `out` = `old` with each chunk (inclusive frame range → file) in place. Raises on any problem."""
    want = stream_format(old)
    for a, b, path in chunks:
        n = frame_count(path)
        if n != b - a + 1:
            raise RuntimeError(f"chunk {path.name} has {n} frames, expected {b - a + 1}")
        got = stream_format(path)
        if got != want:  # stream copy can't mix ProRes flavours, sizes or pixel formats
            raise RuntimeError(f"chunk {path.name} is {got}, the movie is {want}")
    work = out.parent / f".{out.stem}.splice"
    work.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path_for(out)
    try:
        parts: list[tuple[int, int, Path]] = []  # (start frame, frames, file)
        for k, (s, e) in enumerate(kept_ranges(chunks, total_f)):
            piece = work / f"keep{k:03d}{old.suffix}"
            cut(old, s, e, piece, fps)
            if frame_count(piece) != e - s:
                raise RuntimeError(f"kept piece {s}–{e} has {frame_count(piece)} frames, expected {e - s}")
            parts.append((s, e - s, piece))
        parts += [(a, b - a + 1, p) for a, b, p in chunks]
        lst = work / "list.txt"
        # an explicit duration per file: containers may report one frame less, which would start the next piece early
        lst.write_text("ffconcat version 1.0\n" + "".join(f"file {_q(p)}\nduration {float(Fraction(n) / fps):.9f}\n"
                                                          for _s, n, p in sorted(parts, key=lambda x: x[0])))
        tools.ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-map", "0", "-c", "copy", str(tmp)])
        times = frame_times(tmp)
        if len(times) != total_f:
            raise RuntimeError(f"spliced movie has {len(times)} frames, expected {total_f}")
        step = 1 / float(fps)
        bad = next((k for k, t in enumerate(times) if abs(t - k * step) > step / 4), None)
        if bad is not None:
            raise RuntimeError(f"spliced movie's frame {bad} is at {times[bad]:.4f} s, expected {bad * step:.4f} s")
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)
        for f in work.glob("*"):
            f.unlink()
        work.rmdir()
