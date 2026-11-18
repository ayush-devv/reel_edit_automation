"""Gold pairs via local transcription (caption endpoint throttled): Hinglish first, then English top-up."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOBS = [
    ("@BeerBiceps", "hi", ["--shorts", "10", "--episodes", "12", "--max-pairs", "3"]),
    ("@RajShamani", "hi", ["--shorts", "10", "--episodes", "12", "--max-pairs", "3"]),
    ("@aliabdaal", "en", ["--shorts", "8", "--episodes", "12", "--max-pairs", "2", "--genre", "genre.talking_head"]),
    ("@hubermanlab", "en", ["--shorts", "10", "--episodes", "10", "--max-pairs", "2"]),
]
env = {**os.environ, "SSL_CERT_FILE": os.path.expanduser("~/.mac-ca-bundle.pem"), "REQUESTS_CA_BUNDLE": os.path.expanduser("~/.mac-ca-bundle.pem")}
for handle, lang, extra in JOBS:
    if sys.argv[1:] and handle not in sys.argv[1:]:
        continue
    p = subprocess.run([str(ROOT / "engine/.venv/bin/python"), str(ROOT / "tools/goldset/build_asr.py"), handle, lang, *extra],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    keep = [l for l in (p.stdout + p.stderr).splitlines() if any(k in l for k in ("episodes >", "short ", "gold pair", "pair(s)", "Error", "ERROR"))]
    print("\n".join(keep[-30:]), flush=True)
