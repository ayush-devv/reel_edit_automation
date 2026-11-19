"""Import MUCS 2021 Hindi-English test speech as the Hinglish ASR bake-off answer key (ADR-0032).

Source: OpenSLR SLR104 `Hindi-English_test.tar.gz` (CC BY-SA 4.0), Kaldi layout:
  test/<recording>.wav, test/transcripts/{segments,text,wav.scp}.
Builds samples/hinglish/mucs_<recording>/ = clip.wav (a ~30–45 s run of consecutive sentences) +
transcript.txt (their human transcripts, joined), one clip per recording for speaker variety.

Internal evaluation only: the dataset (ShareAlike) is never redistributed and never used in a reel.
ADR-0032 discounts MUCS scores by 5 WER points for the in-domain gap (read spoken tutorials vs. creators).

Usage: python tools/mucs/import_mucs.py samples/_mucs/Hindi-English_test.tar.gz [--out samples/hinglish] [--clips 24]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from reel.config import ffmpeg_path  # noqa: E402

TARGET_S = (30.0, 45.0)
SKIP_FIRST = 1  # the first sentence of a tutorial is a stock greeting: start at the second


def read_kaldi(tdir: Path) -> tuple[dict[str, list[tuple[str, float, float]]], dict[str, str]]:
    segs: dict[str, list[tuple[str, float, float]]] = {}
    for line in (tdir / "segments").read_text().splitlines():
        utt, rec, a, b = line.split()
        segs.setdefault(rec, []).append((utt, float(a), float(b)))
    text = {}
    for line in (tdir / "text").read_text().splitlines():
        utt, _, words = line.partition(" ")
        text[utt] = words.strip()
    for rec in segs:
        segs[rec].sort(key=lambda s: s[1])
    return segs, text


def pick_run(utts: list[tuple[str, float, float]], text: dict[str, str]) -> list[tuple[str, float, float]]:
    """Consecutive sentences (no gap > 1.5 s) totalling TARGET_S."""
    run: list[tuple[str, float, float]] = []
    for u in utts[SKIP_FIRST:]:
        if not text.get(u[0]):
            continue
        if run and (u[1] - run[-1][2] > 1.5 or u[2] - run[0][1] > TARGET_S[1]):
            if run[-1][2] - run[0][1] >= TARGET_S[0]:
                break
            run = []
        run.append(u)
    return run if run and run[-1][2] - run[0][1] >= 10.0 else []


def safe_members(tar: tarfile.TarFile, names: set[str]):
    for m in tar.getmembers():
        if m.name in names and m.isfile() and ".." not in Path(m.name).parts and not m.name.startswith("/"):
            yield m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tar", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "samples" / "hinglish")
    ap.add_argument("--clips", type=int, default=24)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as td, tarfile.open(a.tar) as tar:
        tdir = Path(td)
        want = {"test/transcripts/segments", "test/transcripts/text"}
        tar.extractall(tdir, members=list(safe_members(tar, want)), filter="data")
        segs, text = read_kaldi(tdir / "test" / "transcripts")
        chosen = []
        for rec in sorted(segs):
            run = pick_run(segs[rec], text)
            if run:
                chosen.append((rec, run))
            if len(chosen) >= a.clips:
                break
        tar.extractall(tdir, members=list(safe_members(tar, {f"test/{rec}.wav" for rec, _ in chosen})), filter="data")
        a.out.mkdir(parents=True, exist_ok=True)
        for rec, run in chosen:
            d = a.out / f"mucs_{rec}"
            d.mkdir(parents=True, exist_ok=True)
            start, end = run[0][1], run[-1][2]
            subprocess.run([str(ffmpeg_path()), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
                            "-i", str(tdir / "test" / f"{rec}.wav"), "-ac", "1", "-ar", "16000", str(d / "clip.wav")], check=True)
            (d / "transcript.txt").write_text(" ".join(text[u] for u, _, _ in run) + "\n")
            (d / "SOURCE.md").write_text(f"MUCS 2021 Hindi-English test (OpenSLR SLR104, CC BY-SA 4.0), recording {rec}, "
                                         f"{start:.1f}–{end:.1f} s, utterances {run[0][0]} … {run[-1][0]}. Internal evaluation only (ADR-0032).\n")
            print(f"{d.name}: {end - start:.1f} s, {len(run)} sentences")
    print(f"{len(chosen)} clip(s) in {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
