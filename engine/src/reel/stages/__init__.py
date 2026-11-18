"""Pipeline stages. Each module exposes a `STAGE` (reel.runner.Stage)."""

from reel.stages import ingest, mezzanine, perception

PIPELINE = [ingest.STAGE, mezzanine.STAGE, perception.STAGE]
