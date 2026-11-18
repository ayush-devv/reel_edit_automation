"""Real-footage sync: sources whose video and audio streams start at different times
(section downloads, some phone files) must stay in sync through the mezzanine."""

from fractions import Fraction

import pytest

from reel import config, tools
from reel.conformance import checks
from reel.mezzanine import make_mezzanine, stream_offset_s
from reel.probe import probe

try:
    config.ffmpeg_path()
    READY = True
except config.ToolNotFound:
    READY = False


def _offset_clip(tmp_path, video_late_s: float):
    """Flash at 2.0 s of the picture's own timeline; beep placed so both happen together in a player."""
    v = tmp_path / "v.mp4"
    a = tmp_path / "a.wav"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=25:duration=4,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,2,2.12)'",
                  "-c:v", "libx264", "-pix_fmt", "yuv420p", str(v)])
    beep_at = 2.0 + video_late_s
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", f"aevalsrc='if(between(t,{beep_at},{beep_at}+0.1),0.8*sin(2*PI*1000*t),0)':s=48000:d=5:c=stereo", str(a)])
    out = tmp_path / "src.mp4"
    off_v, off_a = (video_late_s, 0.0) if video_late_s > 0 else (0.0, -video_late_s)
    tools.ffmpeg(["-y", "-itsoffset", str(off_v), "-i", str(v), "-itsoffset", str(off_a), "-i", str(a), "-map", "0:v", "-map", "1:a",
                  "-c:v", "copy", "-c:a", "aac", str(out)])
    return out


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg")
@pytest.mark.parametrize("video_late_s", [0.2, -0.2])
def test_mezzanine_keeps_sync_when_streams_start_apart(tmp_path, video_late_s):
    src = _offset_clip(tmp_path, video_late_s)
    p = probe(src)
    assert stream_offset_s(p) == pytest.approx(video_late_s, abs=0.03)
    mezz = tmp_path / "m.mov"
    make_mezzanine(p, mezz, Fraction(25))
    assert abs(checks.av_offset_ms(mezz)) <= 1000 / 25, checks.av_offset_ms(mezz)
