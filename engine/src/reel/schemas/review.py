"""What the Reviewer returns (ADR-0021, ADR-0030): a fresh-context check of the finished reel."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Severity(str, Enum):
    blocker = "blocker"  # a client would reject the reel
    major = "major"  # clearly below a pro edit; should be fixed before sending
    minor = "minor"  # polish


class Category(str, Enum):
    hook = "hook"
    story = "story"
    pacing = "pacing"
    captions = "captions"
    visual = "visual"
    audio = "audio"
    brand = "brand"


class FixTarget(str, Enum):
    story = "story"  # which lines are kept / their order
    finish = "finish"  # captions, punch-ins, title, look, transitions, SFX, music
    owner = "owner"  # cannot be fixed by re-editing (footage, missing info)


class ReviewIssue(_Strict):
    id: str
    severity: Severity
    category: Category
    at: str  # timecode "m:ss.ss" from the contact sheets / read-back, or "" for the whole reel
    problem: str
    fix_target: FixTarget
    fix: str  # concrete instruction for the Editor (or the owner)


class RubricCheck(_Strict):
    id: str  # a criterion id from plan/rubric.json, exactly as given
    met: bool
    evidence: str  # what in the reel shows it (timecode + what is seen/heard), or why not


class Review(_Strict):
    sendable: bool  # would a demanding client accept this reel as is?
    summary: str
    issues: list[ReviewIssue]
    strengths: list[str]
    rubric: list[RubricCheck] = []  # 3b.1: one answer per fixed criterion (older reviews have none)
