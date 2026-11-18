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


def meta(video_id: str) -> dict:
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, **JS}) as y:
        i = y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    return {"id": video_id, "date": i.get("upload_date"), "duration": i.get("duration"), "title": i.get("title")}


def audio(video_id: str, cache: Path) -> Path:
    out = cache / f"{video_id}.m4a"
    if not out.exists():
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True, "format": "bestaudio[ext=m4a]/bestaudio",
                               "outtmpl": str(cache / "%(id)s.%(ext)s"), **JS}) as y:
            y.download([f"https://www.youtube.com/watch?v={video_id}"])
        out = next(cache.glob(f"{video_id}.*"))
    return out


def words(video_id: str, lang: str, cache: Path) -> list[tuple[str, float]]:
    j = cache / f"{video_id}.words.json"
    if j.exists():
        return [tuple(x) for x in json.loads(j.read_text())]
    a = audio(video_id, cache)
    raw, _ = ASR.transcribe(extract_wav(a, cache / f"{video_id}.wav"), lang, None)
    out = []
    for w in raw:
        t = re.sub(r"[^\wऀ-ॿ']", "", w.text.lower())
        if t:
            out.append((t, w.start_s))
    j.write_text(json.dumps(out, ensure_ascii=False))
    (cache / f"{video_id}.wav").unlink(missing_ok=True)
    return out


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
    shorts = [meta(s["id"]) for s in b.list_tab(a.handle, "shorts", a.shorts)]
    eps = [meta(e["id"]) for e in b.list_tab(a.handle, "videos", a.episodes)]
    eps = [e for e in eps if (e["duration"] or 0) > 600 and e["date"]]
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
            share, s, e = b.match(sw, words(ep["id"], a.lang, cache))
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
        made += 1
        print(f"  → gold pair {gid}: raw {hi - lo:.0f}s, final {dur:.0f}s", flush=True)
    print(f"{chan}: {made} pair(s)", flush=True)


if __name__ == "__main__":
    main()
