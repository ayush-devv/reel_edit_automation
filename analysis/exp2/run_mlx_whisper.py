"""Experiment 2: transcribe with mlx-whisper and save words with timestamps.

Usage: .venv/bin/python run_mlx_whisper.py AUDIO MODEL_REPO OUT_JSON [LANG]
"""
import json
import sys
import time

import mlx_whisper

audio, repo, out = sys.argv[1], sys.argv[2], sys.argv[3]
lang = sys.argv[4] if len(sys.argv) > 4 else None

t0 = time.time()
result = mlx_whisper.transcribe(
    audio,
    path_or_hf_repo=repo,
    word_timestamps=True,
    language=lang,
    condition_on_previous_text=False,
)
elapsed = time.time() - t0

words = [
    {"w": w["word"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3), "p": round(w.get("probability", 0), 3)}
    for seg in result["segments"]
    for w in seg.get("words", [])
]
json.dump({"model": repo, "language": result.get("language"), "elapsed_s": round(elapsed, 1), "text": result["text"], "words": words}, open(out, "w"), ensure_ascii=False, indent=1)
print(f"model={repo} lang={result.get('language')} elapsed={elapsed:.1f}s words={len(words)}")
print(result["text"].strip())
