"""Pipeline stages. Each module exposes a `STAGE` (reel.runner.Stage); `edit` exposes `STAGES`.

PIPELINE = analysis only (no Claude calls) — used by tests and the eval harness's perception
checks. EDIT_PIPELINE = analysis + Editor decisions + compile + render — what `reel run` uses.
"""

from reel.stages import edit, ingest, mezzanine, mine, perception, speakers, tables, voice

PIPELINE = [ingest.STAGE, mezzanine.STAGE, perception.STAGE, voice.STAGE, speakers.STAGE, tables.STAGE]
EDIT_PIPELINE = [*PIPELINE, *edit.STAGES]
# Clip Factory (roadmap G2.2): a long recording is analysed once and mined; each picked candidate becomes a reel
# project that runs only the edit stages on files shared from the source (reel.clipfactory).
MINE_PIPELINE = [*PIPELINE, mine.STAGE]
CLIP_PIPELINE = list(edit.STAGES)
