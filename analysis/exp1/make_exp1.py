"""Experiment 1: build clean and deliberately broken clips + contact sheets.

Source: samples/bathroom.mp4 (finished DearMa testimonial, 720x1280, 25 fps).
Judge-visible output: analysis/exp1/sheets/<id>.png (random ids).
Answer key: analysis/exp1/private/key.json (never shown to judges).
Run from the project root: python3 -I analysis/exp1/make_exp1.py
"""
import json
import random
import subprocess
from pathlib import Path

SRC = "samples/bathroom.mp4"
ROOT = Path("analysis/exp1")
CLIPS = ROOT / "clips"
SHEETS = ROOT / "sheets"
PRIVATE = ROOT / "private"
for d in (CLIPS, SHEETS, PRIVATE):
    d.mkdir(parents=True, exist_ok=True)

# name, start, duration, video filter (None = clean), defect label
CASES = [
    ("clean_intro", 0.0, 4.4, None, "none"),
    ("clean_founder", 11.52, 4.4, None, "none"),
    ("clean_talk", 38.3, 6.0, None, "none"),
    ("face_cut", 38.3, 6.0, "scale=1440:2560,crop=720:1280:360:1100", "punch-in crops the face/head out of frame"),
    ("graphic_over_face", 11.52, 4.4, "drawbox=x=180:y=300:w=360:h=320:color=yellow@1:t=fill", "opaque graphic covers the speaker's face"),
    ("black_gap", 0.0, 4.4, "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,1.8,2.4)'", "0.6 s of black frames mid-clip (1.8-2.4 s)"),
    ("freeze", 38.3, 6.0, "loop=loop=75:size=1:start=40,trim=duration=6,setpts=PTS-STARTPTS", "picture frozen ~1.6-4.6 s"),
    ("squashed", 11.52, 4.4, "scale=720:820,setsar=1,pad=720:1280:0:230:black", "picture squashed vertically and letterboxed"),
    ("pixelated", 4.4, 3.28, "scale=72:128,scale=720:1280:flags=neighbor", "heavily pixelated / low-resolution footage"),
]

rng = random.Random(20261118)
ids = [f"clip_{c}" for c in "ABCDEFGHI"]
rng.shuffle(ids)

key = {}
for (name, start, dur, vf, defect), cid in zip(CASES, ids):
    clip = CLIPS / f"{cid}.mp4"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(dur), "-i", SRC, "-an"]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(clip)]
    subprocess.run(cmd, check=True)

    sheet = SHEETS / f"{cid}.png"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(clip),
         "-vf", "fps=2,scale=240:426,tile=4x3:padding=6:color=white", "-frames:v", "1", str(sheet)],
        check=True,
    )
    key[cid] = {"case": name, "defect": defect, "source_start_s": start, "duration_s": dur}

(PRIVATE / "key.json").write_text(json.dumps(key, indent=2))
print("built", len(key), "clips; sheets in", SHEETS)
