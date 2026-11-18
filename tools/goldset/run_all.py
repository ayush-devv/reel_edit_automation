"""Run build.py over the gold-source channels (English + Hinglish), logging the summary lines."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHANNELS = [  # Hinglish first (the set needs ≥ 2 Hinglish holdout reels)
    ("@BeerBiceps", "hi", ["--shorts", "12", "--episodes", "15", "--max-pairs", "4"]),
    ("@RajShamani", "hi", ["--shorts", "12", "--episodes", "15", "--max-pairs", "4"]),
    ("@aliabdaal", "en", ["--shorts", "10", "--episodes", "15", "--max-pairs", "3", "--genre", "genre.talking_head"]),
    ("@TheDiaryOfACEO", "en", ["--shorts", "20", "--episodes", "25", "--max-pairs", "4"]),
    ("@hubermanlab", "en", ["--shorts", "15", "--episodes", "20", "--max-pairs", "3"]),
]
env = {**os.environ, "SSL_CERT_FILE": os.path.expanduser("~/.mac-ca-bundle.pem"),
       "REQUESTS_CA_BUNDLE": os.path.expanduser("~/.mac-ca-bundle.pem"), "UV_SYSTEM_CERTS": "1"}
import time

args = sys.argv[1:]
if args and args[0].startswith("--delay="):  # wait out YouTube's rate limit before starting
    time.sleep(int(args.pop(0).split("=", 1)[1]))
only = set(args)
with open(ROOT / "samples" / "_goldsrc_batch.log", "a") as log:
    for handle, lang, extra in CHANNELS:
        if only and handle not in only:
            continue
        p = subprocess.run(["uv", "run", "--script", str(ROOT / "tools/goldset/build.py"), handle, lang, *extra],
                           cwd=ROOT, env=env, capture_output=True, text=True)
        lines = [l for l in (p.stdout + p.stderr).splitlines() if re.search(r"episodes >|best match|gold pair|pair\(s\)|ERROR|Error", l)]
        log.write("\n".join(lines) + "\n")
        log.flush()
        print("\n".join(lines), flush=True)
