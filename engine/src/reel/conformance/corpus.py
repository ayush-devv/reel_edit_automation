"""Synthetic conformance clips. Every clip carries a sync probe: a full-white flash frame
and a 1 kHz beep, both starting at exactly 2.000 s, so A/V offset can be measured after
any conversion. Real phone clips (samples/conformance/) are added to the same suite later.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reel import tools

FLASH_AT = 2.0
DUR = 4.0
BEEP = f"aevalsrc='if(between(t,{FLASH_AT},{FLASH_AT}+0.1),0.8*sin(2*PI*1000*t),0)':s=48000:d={DUR}:c=stereo"


@dataclass(frozen=True)
class Clip:
    name: str
    expect_fps: str  # project fps the mezzanine must have when this clip is ingested alone
    description: str


CLIPS = [
    Clip("cfr25_portrait", "25/1", "720x1280 25 fps H.264 — must stay 25 fps"),
    Clip("cfr60_portrait", "60/1", "1080x1920 60 fps H.264"),
    Clip("ntsc2997_portrait", "30000/1001", "720x1280 29.97 fps H.264"),
    Clip("rotated_landscape_tag", "30/1", "1280x720 stored, display rotation 90 → portrait"),
    Clip("vfr_jitter", "30/1", "~30 fps with jittered timestamps (VFR)"),
    Clip("hdr_hlg_10bit", "30/1", "HEVC 10-bit tagged bt2020/HLG → must tonemap to bt709"),
    Clip("no_audio", "30/1", "video only → silent PCM track added"),
]


def _flash_video(size: str, rate: str, base: str = "testsrc2") -> str:
    """Three white frames starting at the first frame at or after FLASH_AT.

    Three, not one: converting VFR to CFR may legitimately drop a single frame, and the
    probe measures the flash *onset*, which survives that.
    """
    num, _, den = rate.partition("/")
    frame_s = float(den or 1) / float(num)
    fl = f"gte(t,{FLASH_AT})*lt(t,{FLASH_AT}+{frame_s * 2.999:.6f})"
    return f"{base}=size={size}:rate={rate}:duration={DUR},drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{fl}'"


def build(out_dir: Path, names: list[str] | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for clip in CLIPS:
        if names and clip.name not in names:
            continue
        out = out_dir / f"{clip.name}.mp4" if clip.name != "hdr_hlg_10bit" else out_dir / f"{clip.name}.mov"
        _make(clip.name, out, out_dir)
        made.append(out)
    return made


def _h264(args: list[str]) -> list[str]:
    return args + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k"]


def _make(name: str, out: Path, tmp_dir: Path) -> None:
    if name == "cfr25_portrait":
        tools.ffmpeg(_h264(["-y", "-f", "lavfi", "-i", _flash_video("720x1280", "25"), "-f", "lavfi", "-i", BEEP]) + [str(out)])
    elif name == "cfr60_portrait":
        tools.ffmpeg(_h264(["-y", "-f", "lavfi", "-i", _flash_video("1080x1920", "60"), "-f", "lavfi", "-i", BEEP]) + [str(out)])
    elif name == "ntsc2997_portrait":
        tools.ffmpeg(_h264(["-y", "-f", "lavfi", "-i", _flash_video("720x1280", "30000/1001"), "-f", "lavfi", "-i", BEEP]) + [str(out)])
    elif name == "rotated_landscape_tag":
        base = tmp_dir / ".rot_base.mp4"
        tools.ffmpeg(_h264(["-y", "-f", "lavfi", "-i", _flash_video("1280x720", "30"), "-f", "lavfi", "-i", BEEP]) + [str(base)])
        # Display matrix: rotate 90° so players show it as portrait 720x1280.
        tools.ffmpeg(["-y", "-display_rotation:v:0", "90", "-i", str(base), "-c", "copy", str(out)])
        base.unlink(missing_ok=True)
    elif name == "vfr_jitter":
        vf = _flash_video("720x1280", "30") + ",setpts='(N/30+0.006*sin(N*1.7))/TB'"
        tools.ffmpeg(["-y", "-f", "lavfi", "-i", vf, "-f", "lavfi", "-i", BEEP, "-fps_mode", "passthrough",
                      "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                      "-c:a", "aac", "-b:a", "160k", str(out)])
    elif name == "hdr_hlg_10bit":
        tools.ffmpeg(["-y", "-f", "lavfi", "-i", _flash_video("720x1280", "30"), "-f", "lavfi", "-i", BEEP,
                      "-c:v", "libx265", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p10le",
                      "-x265-params", "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:log-level=error",
                      "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc",
                      "-tag:v", "hvc1", "-c:a", "aac", "-b:a", "160k", str(out)])
    elif name == "no_audio":
        tools.ffmpeg(["-y", "-f", "lavfi", "-i", _flash_video("720x1280", "30"), "-an",
                      "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)])
    else:
        raise ValueError(name)
