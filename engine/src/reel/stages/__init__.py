"""Pipeline stages. Each module exposes a `STAGE` (reel.runner.Stage); `edit` exposes `STAGES`.

PIPELINE = analysis only (no Claude calls) — used by tests and the eval harness's perception
checks. EDIT_PIPELINE = analysis + Editor decisions + compile + render — what `reel run` uses.
"""

from reel.stages import edit, ingest, mezzanine, perception, speakers, tables

PIPELINE = [ingest.STAGE, mezzanine.STAGE, perception.STAGE, speakers.STAGE, tables.STAGE]
EDIT_PIPELINE = [*PIPELINE, *edit.STAGES]
