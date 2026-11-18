"""Contact sheets with burned-in labels (ADR-0030: ≤ 2,576 px long edge, tagged)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from reel import tools

COLS, ROWS = 4, 3
TILE_W = 240  # 4 tiles → 1,000 px wide incl. padding; 3 rows of 9:16 → ~1,300 px tall
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font() -> str | None:
    return next((f for f in FONT_CANDIDATES if Path(f).exists()), None)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def make_sheets(mezz: Path, stamps: list[tuple[float, str]], out_prefix: Path) -> list[Path]:
    """One labelled tile per (time_s, label); 12 tiles per sheet. Returns sheet paths."""
    font = _font()
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    sheets = []
    per = COLS * ROWS
    for n in range(0, len(stamps), per):
        chunk = stamps[n:n + per]
        with tempfile.TemporaryDirectory() as td:
            for k, (t, label) in enumerate(chunk):
                draw = (f",drawtext=text='{_escape(label)}':x=6:y=6:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=4"
                        + (f":fontfile='{font}'" if font else ""))
                tools.ffmpeg(["-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(mezz), "-frames:v", "1",
                              "-vf", f"scale={TILE_W}:-2:flags=area{draw}", str(Path(td) / f"t{k:02d}.png")])
            # A partial last sheet is flushed by the tile filter at EOF with white padding.
            sheet = out_prefix.with_name(f"{out_prefix.name}_{n // per + 1:02d}.png")
            tools.ffmpeg(["-y", "-framerate", "1", "-i", str(Path(td) / "t%02d.png"),
                          "-vf", f"tile={COLS}x{ROWS}:padding=6:color=white", "-frames:v", "1", str(sheet)])
            sheets.append(sheet)
    return sheets
