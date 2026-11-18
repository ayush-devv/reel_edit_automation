"""S0 mezzanine: one clean clip per source on a single clock (ADR-0015, ADR-0023).

Output per clip: ProRes 422 10-bit .mov, CFR at the project fps, rotation baked in and
cleared, square pixels, even dimensions, bt709 SDR (HDR PQ/HLG tonemapped), PCM 48 kHz
stereo (silence added when the source has no audio).
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from reel import config, tools
from reel.probe import SourceProbe

TONEMAP_CHAIN = (
    "zscale=t=linear:npl=100,format=gbrpf32le,"
    "zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv"
)
TO_BT709 = "zscale=m=bt709:p=bt709:t=bt709:r=tv"
SDR_709 = {"bt709", None, "unknown", ""}


SYNC_TOLERANCE_S = 0.002


def stream_offset_s(p: SourceProbe) -> float:
    """Video start minus audio start in the source (> 0: the picture starts later than the sound)."""
    if p.video is None or p.audio is None:
        return 0.0
    return p.video.start_s - p.audio.start_s


def video_filter(p: SourceProbe, fps: Fraction) -> str:
    assert p.video is not None
    v = p.video
    chain: list[str] = []
    off = stream_offset_s(p)
    chain.append("setpts=PTS-STARTPTS")  # picture's own zero first …
    if off > SYNC_TOLERANCE_S:  # … then, if it starts late, hold its first frame so both streams share time zero
        chain.append(f"tpad=start_duration={off:.6f}:start_mode=clone")
    # Colour: HDR → tonemap to bt709 SDR; other non-709 SDR → convert; unknown → assume 709 (tag only).
    if v.hdr:
        chain.append(TONEMAP_CHAIN)
    elif v.color_space not in SDR_709 or v.color_primaries not in SDR_709:
        chain.append(TO_BT709)
    # Square pixels.
    if v.sar and v.sar not in ("1:1", "0:1", "N/A"):
        chain.append("scale=trunc(iw*sar/2)*2:ih:flags=lanczos,setsar=1")
    # Even dimensions (after autorotate, which ffmpeg applies before this chain).
    chain.append("scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos")
    chain.append("setsar=1")
    # Constant frame rate on the project clock.
    chain.append(f"fps=fps={fps.numerator}/{fps.denominator}:round=near")
    chain.append("format=yuv422p10le")
    # Make the frames carry bt709 properties so every encoder/muxer tags them (not only the HDR path).
    chain.append("setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")
    return ",".join(chain)


def build_command(p: SourceProbe, out: Path, fps: Fraction, *, encoder: str = "prores_ks") -> list[str]:
    if p.video is None:
        raise ValueError(f"{p.path}: no video stream")
    args: list[str] = ["-y", "-i", p.path]
    has_audio = p.audio is not None
    if not has_audio:
        args += ["-f", "lavfi", "-i", f"anullsrc=r={config.AUDIO_RATE}:cl=stereo"]
    args += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0"]
    args += ["-vf", video_filter(p, fps), "-fps_mode", "cfr"]
    off = stream_offset_s(p)
    # sound starts late: delay it so both streams share time zero (the shift is preserved, not lost)
    adelay = f"adelay={-off * 1000:.3f}:all=1," if off < -SYNC_TOLERANCE_S else ""
    args += ["-af", f"{adelay}asetpts=PTS-STARTPTS" if has_audio else "anull"]
    if encoder == "prores_videotoolbox":
        args += ["-c:v", "prores_videotoolbox", "-profile:v", "2"]
    else:
        args += ["-c:v", "prores_ks", "-profile:v", "2", "-vendor", "apl0"]
    args += [
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
        "-c:a", "pcm_s16le", "-ar", str(config.AUDIO_RATE), "-ac", str(config.AUDIO_CHANNELS),
        "-map_metadata", "-1", "-map_chapters", "-1",
    ]
    if not has_audio:
        args += ["-shortest"]
    args += [str(out)]
    return args


def make_mezzanine(p: SourceProbe, out: Path, fps: Fraction, *, encoder: str = "prores_ks", timeout: float = 3600) -> None:
    from reel.workspace import tmp_path_for

    tmp = tmp_path_for(out)
    tmp.unlink(missing_ok=True)
    cmd = build_command(p, tmp, fps, encoder=encoder)
    try:
        tools.ffmpeg(cmd, timeout=timeout)
    except tools.ToolError:
        tmp.unlink(missing_ok=True)
        if encoder == "prores_videotoolbox":
            # Hardware encoder unavailable/unsupported input: fall back to the CPU encoder.
            make_mezzanine(p, out, fps, encoder="prores_ks", timeout=timeout)
            return
        raise
    tmp.replace(out)
