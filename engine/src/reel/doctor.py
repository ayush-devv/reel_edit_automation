"""Environment checks for the pinned toolchain (ADR-0023, ADR-0030)."""

from __future__ import annotations

import re
import shutil
import subprocess

from reel import config


def _out(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def check() -> dict:
    report: dict = {"ok": True, "items": []}

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        report["items"].append({"name": name, "ok": ok, "detail": detail, "required": required})
        if required and not ok:
            report["ok"] = False

    try:
        ff = config.ffmpeg_path()
        version = (_out([str(ff), "-version"]).splitlines() or ["?"])[0]
        add("pinned ffmpeg", True, f"{ff} — {version}")
        filters = set(re.findall(r"^\s*[TSC.]{2,3}\s+(\w+)\s", _out([str(ff), "-hide_banner", "-filters"]), re.M))
        for name in config.REQUIRED_FILTERS:
            add(f"filter {name}", name in filters, "present" if name in filters else "missing")
        encoders = set(re.findall(r"^\s*[VAS][.\w]{5}\s+(\w+)\s", _out([str(ff), "-hide_banner", "-encoders"]), re.M))
        for name in config.REQUIRED_ENCODERS:
            add(f"encoder {name}", name in encoders, "present" if name in encoders else "missing", required=name != "prores_videotoolbox")
    except config.ToolNotFound as exc:
        add("pinned ffmpeg", False, str(exc))
    try:
        fp = config.ffprobe_path()
        add("ffprobe", True, str(fp))
    except config.ToolNotFound as exc:
        add("ffprobe", False, str(exc))
    node = shutil.which("node")
    add("node (Remotion)", bool(node), _out([node, "--version"]).strip() if node else "not found", required=False)
    claude = shutil.which("claude")
    add("claude (Claude Code)", bool(claude), _out([claude, "--version"]).strip() if claude else "not found", required=False)
    return report
