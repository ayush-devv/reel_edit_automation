"""Paths, constants and pinned-tool resolution."""

from __future__ import annotations

import os
import shutil
from fractions import Fraction
from pathlib import Path

# Repository root = two levels above engine/src/reel
ENGINE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = ENGINE_DIR.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
EVAL_DIR = REPO_ROOT / "eval"

AUDIO_RATE = 48_000
AUDIO_CHANNELS = 2

# Standard project frame rates (ADR-0015). Sources are snapped to the nearest one.
STANDARD_FPS: tuple[Fraction, ...] = (
    Fraction(24000, 1001),
    Fraction(24),
    Fraction(25),
    Fraction(30000, 1001),
    Fraction(30),
    Fraction(50),
    Fraction(60000, 1001),
    Fraction(60),
)
MAX_PROJECT_FPS = Fraction(60)

# Filters the engine relies on from the pinned build (ADR-0023).
REQUIRED_FILTERS = ("zscale", "tonemap", "libplacebo", "subtitles", "drawtext", "fps", "scale")
REQUIRED_ENCODERS = ("prores_videotoolbox", "prores_ks", "pcm_s16le", "libx264", "h264_videotoolbox")

_BREW_PREFIXES = (
    Path.home() / ".brew",
    Path("/opt/homebrew"),
    Path("/usr/local"),
)


class ToolNotFound(RuntimeError):
    pass


def _pinned_candidate(name: str) -> Path | None:
    for prefix in _BREW_PREFIXES:
        candidate = prefix / "opt" / "ffmpeg-full" / "bin" / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def ffmpeg_path() -> Path:
    """Pinned ffmpeg: $REEL_FFMPEG, else Homebrew ffmpeg-full."""
    env = os.environ.get("REEL_FFMPEG")
    if env:
        return Path(env)
    found = _pinned_candidate("ffmpeg")
    if found:
        return found
    raise ToolNotFound(
        "Pinned ffmpeg not found. Install it with `brew install ffmpeg-full` "
        "or set REEL_FFMPEG to an ffmpeg built with zimg, libplacebo and libass."
    )


def ffprobe_path() -> Path:
    env = os.environ.get("REEL_FFPROBE")
    if env:
        return Path(env)
    found = _pinned_candidate("ffprobe")
    if found:
        return found
    system = shutil.which("ffprobe")
    if system:
        return Path(system)
    raise ToolNotFound("ffprobe not found.")


# ASR engine per language (ADR-0007). Hindi/Hinglish = bake-off winner; until the owner's clips
# have been scored this stays on Whisper large-v3 (`reel bakeoff`, docs/plan/step8-hinglish.md).
ASR_ENGINES = {"en": "whisper-turbo", "hi": "whisper-large-v3", "hinglish": "whisper-large-v3"}


# QA gate modes (ADR-0017): measured gates warn until `reel calibrate` shows an acceptable
# false-positive rate on owner-sendable renders; the owner then promotes them here.
QA_GATES = {
    "frame_count": "block", "loudness": "block", "proof_words": "block", "brief": "block",
    "dead_air": "warn", "frozen": "warn", "black": "warn", "caption_contrast": "warn", "caption_over_face": "warn",
    "safe_zone": "warn", "reading_speed": "warn", "face_cut": "warn",
    "cut_pop": "warn", "cut_flash": "warn", "cut_in_word": "warn", "duration_match": "warn",
    "numbers": "warn",  # on-screen numbers vs speech (reel.numbers); the plan check already sends clear mismatches back
}
# The Reviewer can always force `hold`; it drives automatic fixes only once calibrated (ADR-0021 §5).
REVIEWER_TRUSTED = False
MAX_FIX_LOOPS = 3
