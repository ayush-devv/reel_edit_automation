"""Gold pairs without YouTube captions (that endpoint throttles us): audio-only downloads +
local Whisper transcription, then the same matching as build.py.

Run with the engine venv (needs mlx-whisper + yt-dlp):
  engine/.venv/bin/python tools/goldset/build_asr.py <@handle> <en|hi> [--shorts 10] [--episodes 12] [--max-pairs 3]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import yt_dlp

sys.path.insert(0, str(Path(__file__).parent))
import build as b  # noqa: E402  (match, download, GOLD, SRC, RAW_TARGET_S, MIN_MATCH)

from reel.perception.asr import MlxWhisper  # noqa: E402
from reel.perception.audio import extract_wav  # noqa: E402

JS = {"js_runtimes": {"node": {}}, "compat_opts": {"no-certifi"}}  # system CA bundle (TLS-inspecting network), not certifi
ASR = MlxWhisper("mlx-community/whisper-large-v3-turbo")


def meta(video_id: str) -> dict | None:
    """None for videos we cannot read (members-only, private, age-gated, removed): skip, never crash the batch."""
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, **JS}) as y:
            i = y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except yt_dlp.utils.DownloadError as e:
        print(f"  skip {video_id}: {str(e).splitlines()[0][:120]}")
        return None
    return {"id": video_id, "date": i.get("upload_date"), "duration": i.get("duration"), "title": i.get("title")}


def audio(video_id: str, cache: Path) -> Path:
    out = cache / f"{video_id}.m4a"
    if not out.exists():
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True, "format": "bestaudio[ext=m4a]/bestaudio",
                               "outtmpl": str(cache / "%(id)s.%(ext)s"), **JS}) as y:
            y.download([f"https://www.youtube.com/watch?v={video_id}"])
        out = next(cache.glob(f"{video_id}.*"))
    return out


CHUNK_S = 600  # long episodes: 10-minute chunks (whole-file word timing collapses on 2-hour Hindi audio)
LOCATE_REPO = "mlx-community/whisper-large-v3-turbo"  # the small model loops on Hindi and was slower
MAX_EPISODE_S = 4500  # skip 2–3 h podcasts: too slow to transcribe while YouTube's caption endpoint throttles us


def _norm(t: str) -> str:
    return re.sub(r"[^\w\u0900-\u097F']", "", t.lower())


def words(video_id: str, lang: str, cache: Path, *, long: bool = False, stop_when=None) -> list[tuple[str, float]]:
    """Short clips: word-timed transcript. Long episodes: chunked, segment-timed (words spread evenly
    over each segment) — only used to LOCATE the Short; pairs are verified afterwards."""
    import subprocess

    import mlx_whisper

    from reel import config

    j = cache / f"{video_id}.{'segS' if long else 'locS'}.json"
    if j.exists():
        return [tuple(x) for x in json.loads(j.read_text())]
    a = audio(video_id, cache)
    wav = extract_wav(a, cache / f"{video_id}.wav")
    out: list[tuple[str, float]] = []
    if not long:  # the Short, transcribed with the SAME small model as the episodes so their words line up
        res = mlx_whisper.transcribe(str(wav), path_or_hf_repo=LOCATE_REPO, language=lang, word_timestamps=False,
                                     condition_on_previous_text=False)
        for seg in res.get("segments", []):
            toks = [t for t in (_norm(x) for x in seg["text"].split()) if t]
            span = max(1e-3, seg["end"] - seg["start"])
            out += [(t, seg["start"] + span * n / max(1, len(toks))) for n, t in enumerate(toks)]
    else:
        import soundfile as sf

        dur = sf.info(str(wav)).duration
        for k in range(0, int(dur), CHUNK_S):
            part = cache / f"{video_id}.part.wav"
            subprocess.run([str(config.ffmpeg_path()), "-v", "error", "-y", "-ss", str(k), "-t", str(CHUNK_S), "-i", str(wav), str(part)], check=True)
            res = mlx_whisper.transcribe(str(part), path_or_hf_repo=LOCATE_REPO, language=lang, word_timestamps=False,
                                         condition_on_previous_text=False)
            for seg in res.get("segments", []):
                toks = [t for t in (_norm(x) for x in seg["text"].split()) if t]
                span = max(1e-3, seg["end"] - seg["start"])
                out += [(t, k + seg["start"] + span * n / max(1, len(toks))) for n, t in enumerate(toks)]
            part.unlink(missing_ok=True)
            if stop_when and stop_when(out):  # the Short is found: no need to transcribe the rest (not cached: partial)
                wav.unlink(missing_ok=True)
                return out
    j.write_text(json.dumps(out, ensure_ascii=False))
    wav.unlink(missing_ok=True)
    return out


def verify(d: Path, lang: str, cache: Path) -> float:
    """Share of the final's words found in the downloaded raw clip (both transcribed with word timing)."""
    fw = [(t, w.start_s) for w in ASR.transcribe(extract_wav(d / "final.mp4", cache / "v_f.wav"), lang, None)[0] if (t := _norm(w.text))]
    rw = [(t, w.start_s) for w in ASR.transcribe(extract_wav(d / "raw" / "raw.mp4", cache / "v_r.wav"), lang, None)[0] if (t := _norm(w.text))]
    for f in ("v_f.wav", "v_r.wav"):
        (cache / f).unlink(missing_ok=True)
    return b.match(fw, rw)[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("lang", choices=["en", "hi"])
    ap.add_argument("--shorts", type=int, default=10)
    ap.add_argument("--episodes", type=int, default=12)
    ap.add_argument("--max-pairs", type=int, default=3)
    ap.add_argument("--genre", default="genre.podcast_clip")
    a = ap.parse_args()
    chan = a.handle.lstrip("@")
    cache = b.SRC / chan / "asr"
    cache.mkdir(parents=True, exist_ok=True)
    shorts = [m for s in b.list_tab(a.handle, "shorts", a.shorts) if (m := meta(s["id"]))]
    eps = [m for e in b.list_tab(a.handle, "videos", a.episodes) if (m := meta(e["id"]))]
    eps = [e for e in eps if 600 < (e["duration"] or 0) <= MAX_EPISODE_S and e["date"]]
    print(f"{chan}: {len(shorts)} shorts, {len(eps)} episodes > 10 min", flush=True)
    made = 0
    for sh in shorts:
        if made >= a.max_pairs or not sh["date"]:
            continue
        sd = dt.date.fromisoformat(f"{sh['date'][:4]}-{sh['date'][4:6]}-{sh['date'][6:]}")
        cands = sorted((e for e in eps if 0 <= (sd - dt.date.fromisoformat(f"{e['date'][:4]}-{e['date'][4:6]}-{e['date'][6:]}")).days <= 45),
                       key=lambda e: e["date"], reverse=True)[:2]
        if not cands:
            continue
        sw = words(sh["id"], a.lang, cache)
        if len(sw) < 20:
            continue
        best = (0.0, None, 0.0, 0.0)
        for ep in cands:
            done = lambda ew: b.match(sw, ew)[0] >= 0.75  # noqa: E731
            share, s, e = b.match(sw, words(ep["id"], a.lang, cache, long=True, stop_when=done))
            if share > best[0]:
                best = (share, ep, s, e)
        share, ep, s, e = best
        print(f"  short {sh['id']} ({(sh['title'] or '')[:45]!r}): best {share:.0%}" + (f" in {ep['id']} {s:.0f}-{e:.0f}s" if ep else ""), flush=True)
        if share < b.MIN_MATCH or not ep or e - s > 240:
            continue
        pad = max(0.0, (b.RAW_TARGET_S - (e - s)) / 2)
        lo, hi = max(0.0, s - pad), e + pad
        gid = f"{chan.lower()}_{sh['id']}"
        d = b.GOLD / gid
        if not (d / "final.mp4").exists():
            b.download(f"https://www.youtube.com/shorts/{sh['id']}", d / "final.mp4")
            b.download(f"https://www.youtube.com/watch?v={ep['id']}", d / "raw" / "raw.mp4", (lo, hi))
        dur = float(sh["duration"] or (sw[-1][1] + 2))
        (d / "brief.json").write_text(json.dumps({
            "project": gid, "language": "hinglish" if a.lang == "hi" else "en", "genre_hint": a.genre,
            "target_length_s": [round(max(10, dur * 0.8), 1), round(dur * 1.25, 1)],
            "notes": "Cut a vertical short-form reel from this podcast/talking-head footage."}, indent=1))
        (d / "source.json").write_text(json.dumps({
            "final": f"https://www.youtube.com/shorts/{sh['id']}", "episode": f"https://www.youtube.com/watch?v={ep['id']}",
            "episode_span_s": [round(lo, 1), round(hi, 1)], "matched_span_s": [round(s, 1), round(e, 1)], "match_share": round(share, 3),
            "matched_by": "local whisper transcripts", "channel": a.handle,
            "licence": "YouTube Standard License — internal evaluation only, not redistributed"}, indent=1))
        v = verify(d, a.lang, cache)
        if v < 0.6:  # the located window is wrong (e.g. timestamp drift): never keep an unverified pair
            import shutil

            shutil.move(str(d), str(b.GOLD.parent / "_rejected" / gid))
            print(f"  ✗ rejected {gid}: only {v:.0%} of the final's words are in the raw window", flush=True)
            continue
        made += 1
        print(f"  → gold pair {gid}: raw {hi - lo:.0f}s, final {dur:.0f}s, verified {v:.0%}", flush=True)
    print(f"{chan}: {made} pair(s)", flush=True)


if __name__ == "__main__":
    main()
