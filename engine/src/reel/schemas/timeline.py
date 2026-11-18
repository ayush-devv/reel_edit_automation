"""The canonical timeline — single source of truth for rendering (ADR-0003, ADR-0004).

Every field carries its owning renderer in `json_schema_extra={"owner": ...}`:
ffmpeg = base layer (pixels + sound), remotion = transparent overlay, engine = precomputed
by the Python engine. Placement is in integer output frames; source points are integer µs
on the mezzanine clock; keyframes are clip-relative.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from reel.schemas.plan import Ease, TransitionType


def owned(owner: str, **kw):
    return Field(json_schema_extra={"owner": owner}, **kw)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Keyframe(_Strict):
    f: int  # frame relative to the clip start
    v: float
    ease: Ease = Ease.linear


class Provenance(_Strict):
    item: str  # plan item id
    words: list[int]  # [first, last] global word indices


class AssetKind(str, Enum):
    video = "video"
    audio = "audio"
    image = "image"
    sfx = "sfx"
    music = "music"
    matte = "matte"


class Asset(_Strict):
    id: str
    kind: AssetKind
    uri: str  # path relative to the workspace or repo
    duration_us: int | None = None


class VideoClip(_Strict):
    id: str
    asset: str = owned("ffmpeg")
    at_f: int = owned("ffmpeg")
    dur_f: int = owned("ffmpeg")
    src_in_us: int = owned("ffmpeg")
    src_out_us: int = owned("ffmpeg")
    speed: float = owned("ffmpeg", default=1.0)
    scale: list[Keyframe] = owned("ffmpeg", default_factory=list)  # punch-ins / push-ins
    x: list[Keyframe] = owned("ffmpeg", default_factory=list)  # pan (normalised offset)
    y: list[Keyframe] = owned("ffmpeg", default_factory=list)
    src: Provenance


class AudioClip(_Strict):
    id: str
    asset: str = owned("ffmpeg")
    at_f: int = owned("ffmpeg")
    dur_f: int = owned("ffmpeg")
    src_in_us: int = owned("ffmpeg", default=0)
    speed: float = owned("ffmpeg", default=1.0)  # retime (non-speech only, ADR-0015)
    gain_db: float = owned("ffmpeg", default=0.0)
    role: str = owned("ffmpeg")  # voice | music | sfx
    src: Provenance | None = None


class Ducking(_Strict):
    target_role: str = owned("ffmpeg", default="music")
    under_role: str = owned("ffmpeg", default="voice")
    depth_db: float = owned("ffmpeg")
    attack_ms: int = owned("ffmpeg", default=200)
    release_ms: int = owned("ffmpeg", default=500)
    regions_f: list[list[int]] = owned("ffmpeg", default_factory=list)  # speech spans [start, end) in output frames


class TransitionEvent(_Strict):
    id: str
    at_f: int = owned("ffmpeg")  # output frame of the cut
    type: TransitionType = owned("ffmpeg")
    frames: int = owned("ffmpeg")


class CaptionWord(_Strict):
    i: int
    text: str = owned("remotion")
    start_f: int = owned("remotion")
    end_f: int = owned("remotion")
    emph: bool = owned("remotion", default=False)


class CaptionPage(_Strict):
    start_f: int = owned("remotion")
    end_f: int = owned("remotion")
    words: list[CaptionWord] = owned("remotion")


class CaptionTrack(_Strict):
    family: str = owned("remotion")
    tokens: dict[str, str] = owned("remotion", default_factory=dict)
    script: str = owned("remotion", default="latin")
    timing: str = owned("remotion", default="word")  # word = word-by-word highlight; phrase = page-level (fallback)
    pages: list[CaptionPage] = owned("remotion", default_factory=list)


class Grade(_Strict):
    look: str = owned("ffmpeg", default="none")
    strength: float = owned("ffmpeg", default=0.0)
    correct: bool = owned("ffmpeg", default=True)  # per-clip white balance + exposure toward neutral


class TitleEvent(_Strict):
    id: str
    text: str = owned("remotion")
    start_f: int = owned("remotion")
    end_f: int = owned("remotion")
    role: str = owned("remotion", default="hook")


class FlashEvent(_Strict):
    id: str
    at_f: int = owned("remotion")  # output frame of the cut; the flash peaks here
    frames: int = owned("remotion")


class Timeline(_Strict):
    schema_version: int = 1
    fps: str  # "num/den"
    width: int
    height: int
    duration_f: int
    assets: dict[str, Asset]
    video: list[VideoClip]
    audio: list[AudioClip]
    transitions: list[TransitionEvent] = Field(default_factory=list)
    ducking: list[Ducking] = Field(default_factory=list)
    grade: Grade = Field(default_factory=Grade)
    captions: CaptionTrack | None = None
    titles: list[TitleEvent] = Field(default_factory=list)
    flashes: list[FlashEvent] = Field(default_factory=list)
    plan_ref: dict[str, str] = Field(default_factory=dict)  # file hashes of the plans compiled


def field_owners(model: type[BaseModel] = Timeline, prefix: str = "") -> dict[str, str]:
    """Flatten owner tags: {'video[].at_f': 'ffmpeg', 'captions.pages': 'remotion', ...}."""
    out: dict[str, str] = {}
    for name, f in model.model_fields.items():
        extra = f.json_schema_extra if isinstance(f.json_schema_extra, dict) else {}
        if "owner" in extra:
            out[f"{prefix}{name}"] = extra["owner"]
        ann = f.annotation
        for sub in (VideoClip, AudioClip, Ducking, Grade, TransitionEvent, CaptionTrack, CaptionPage, CaptionWord, TitleEvent, FlashEvent):
            if ann is sub or (getattr(ann, "__args__", None) and sub in ann.__args__):
                out.update(field_owners(sub, f"{prefix}{name}[]."))
    return out


REMOTION_FIELDS = ("captions", "titles", "flashes")
FFMPEG_FIELDS = ("assets", "video", "audio", "transitions", "ducking", "grade")


def part(tl: Timeline, fields: tuple[str, ...]) -> dict:
    """The slice of the timeline one renderer reads (for input hashes: a caption-only change
    must not re-render the base)."""
    d = tl.model_dump(mode="json")
    return {k: d[k] for k in ("fps", "width", "height", "duration_f", *fields)}
