"""End-to-end perception on synthetic speech (macOS `say`). Skipped without the tools."""

import json
import re
import shutil
import subprocess

import pytest

from reel import config, tools
from reel.evalh.metrics import word_error_rate
from reel.runner import run_pipeline
from reel.stages import PIPELINE
from reel.workspace import Workspace

SCRIPT = ("Hi everyone. Today I will show you one simple trick to save money. "
          "Put ten percent of your salary into a separate account every month, and never touch it.")

try:
    config.ffmpeg_path()
    import mlx_whisper  # noqa: F401
    import silero_vad  # noqa: F401

    READY = shutil.which("say") is not None
except Exception:  # noqa: BLE001
    READY = False

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not READY, reason="needs pinned ffmpeg, perception extra and macOS say")]


@pytest.fixture(scope="module")
def speech_clip(tmp_path_factory):
    d = tmp_path_factory.mktemp("speech")
    aiff = d / "voice.aiff"
    subprocess.run(["say", "-o", str(aiff), SCRIPT], check=True)
    clip = d / "talk.mp4"
    tools.ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30", "-i", str(aiff),
                  "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(clip)])
    return clip


def _norm(text):
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", text.lower()).split() if t]


def test_perception_end_to_end(speech_clip, tmp_path):
    ws = Workspace.create(tmp_path / "proj")
    state = run_pipeline(ws, PIPELINE, options={"input": str(speech_clip), "language": "en", "skip_visual": False})
    meta = state["stages"]["perception"]["meta"]
    words = json.loads(ws.path("perception", "words.json").read_text())["words"]
    hyp = _norm(" ".join(w["text"] for w in words))
    wer = word_error_rate(_norm(SCRIPT), hyp)
    assert wer <= 0.10, (wer, hyp)
    starts = [w["start_us"] for w in words]
    assert starts == sorted(starts) and all(w["end_us"] > w["start_us"] for w in words)
    segs = json.loads(ws.path("perception", "segments.json").read_text())["segments"]
    assert len(segs) >= 2
    vad = json.loads(ws.path("perception", "vad.json").read_text())["c01"]
    assert vad["speech_ratio"] > 0.5
    prosody = json.loads(ws.path("perception", "prosody.json").read_text())["segments"]
    assert all(p["words_per_s"] > 0.5 for p in prosody)
    faces = json.loads(ws.path("perception", "faces.json").read_text())["c01"]
    assert "error" in faces or faces["presence"] == 0.0  # synthetic picture has no faces
    palette = json.loads(ws.path("perception", "palette.json").read_text())["c01"]
    assert "error" in palette or len(palette["colors"]) == 5
    assert meta["words"] == len(words)
    # idempotent
    again = run_pipeline(ws, PIPELINE, options={"input": str(speech_clip), "language": "en", "skip_visual": False})
    assert again["stages"]["perception"]["finished"] == state["stages"]["perception"]["finished"]
