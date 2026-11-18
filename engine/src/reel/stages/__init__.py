"""Pipeline stages. Each module exposes a `STAGE` (reel.runner.Stage)."""

from reel.stages import ingest, mezzanine

PIPELINE = [ingest.STAGE, mezzanine.STAGE]
