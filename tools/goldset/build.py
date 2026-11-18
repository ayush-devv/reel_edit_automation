# /// script
# requires-python = ">=3.11"
# dependencies = ["yt-dlp"]
# ///
"""Build gold pairs from channels that publish full episodes + official Shorts cut from them.

gold final = the official Short (made by the channel's editors)
raw        = the stretch of the episode the Short was cut from, padded to a 2–3 min client clip
Matching uses YouTube auto-captions (word-timed json3) only; video is downloaded only for
matched pairs and only the needed section of the episode.

Internal evaluation only: files stay in the gitignored samples/ folder, never redistributed.

usage: uv run --script tools/goldset/build.py <channel handle> <lang en|hi> [--shorts 15] [--episodes 25] [--max-pairs 4]
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import yt_dlp

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "samples" / "_goldsrc"
GOLD = ROOT / "samples" / "gold"
RAW_TARGET_S = 150.0  # simulated client clip length around the matched span
NGRAM = 4
MIN_MATCH = 0.55  # share of the Short's words that must be found in one episode


def ydl(**kw):
    return yt_dlp.YoutubeDL({"compat_opts": {"no-certifi"}, "js_runtimes": {"node": {}}, "quiet": True, "no_warnings": True, "noprogress": True, "retries": 3, "sleep_interval_requests": 0.5, **kw})


def list_tab(handle: str, tab: str, n: int) -> list[dict]:
    with ydl(extract_flat=True, playlistend=n, skip_download=True) as y:
        info = y.extract_info(f"https://www.youtube.com/{handle}/{tab}", download=False)
    return [{"id": e["id"], "title": e.get("title"), "duration": e.get("duration")} for e in info.get("entries", [])[:n]]


def words_json3(path: Path) -> list[tuple[str, float]]:
    """(word, start_s) from a YouTube json3 caption file (auto captions carry per-word offsets)."""
    data = json.loads(path.read_text())
    out = []
    for ev in data.get("events", []):
        t0 = ev.get("tStartMs", 0)
        for seg in ev.get("segs", []) or []:
            for w in re.split(r"\s+", seg.get("utf8", "").strip()):
                w = re.sub(r"[^\wऀ-ॿ']", "", w.lower())
                if w:
                    out.append((w, (t0 + seg.get("tOffsetMs", 0)) / 1000))
    return out


class RateLimited(RuntimeError):
    pass


def captions(video_id: str, lang: str, cache: Path) -> list[tuple[str, float]] | None:
    cache.mkdir(parents=True, exist_ok=True)
    hit = sorted(cache.glob(f"{video_id}*.json3"))
    if not hit:
        langs = [lang, f"{lang}-orig", "en", "en-orig"] if lang != "en" else ["en", "en-orig"]
        with ydl(skip_download=True, writeautomaticsub=True, writesubtitles=True, subtitleslangs=langs, subtitlesformat="json3",
                 outtmpl=str(cache / "%(id)s.%(ext)s")) as y:
            try:
                y.download([f"https://www.youtube.com/watch?v={video_id}"])
            except yt_dlp.utils.DownloadError as exc:
                if "429" in str(exc):
                    raise RateLimited("YouTube is throttling caption requests (HTTP 429) — stop and retry later") from exc
                return None
        hit = sorted(cache.glob(f"{video_id}*.json3"))
        time.sleep(4.0)  # be gentle: YouTube throttles caption bursts
    return words_json3(hit[0]) if hit else None


def dehallucinate(words: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Whisper writes music as one token repeated ("दुप दुप दुप …"): keep at most 2 of any run."""
    out = []
    for w in words:
        if len(out) >= 2 and out[-1][0] == w[0] and out[-2][0] == w[0]:
            continue
        out.append(w)
    return out


def match(short: list[tuple[str, float]], episode: list[tuple[str, float]]) -> tuple[float, float, float]:
    """(share of the Short's words found, span start s, span end s) via shared word 4-grams; densest cluster.
    Hallucinated repeats are dropped and an n-gram must contain ≥ 3 distinct words to count."""
    short, episode = dehallucinate(short), dehallucinate(episode)
    idx: dict[tuple, list[int]] = {}
    ew = [w for w, _ in episode]
    for k in range(len(ew) - NGRAM + 1):
        idx.setdefault(tuple(ew[k:k + NGRAM]), []).append(k)
    sw = [w for w, _ in short]
    hits = []  # episode positions of matched short words
    covered = set()
    for k in range(len(sw) - NGRAM + 1):
        if len(set(sw[k:k + NGRAM])) < 3:
            continue
        pos = idx.get(tuple(sw[k:k + NGRAM]))
        if pos:
            covered.update(range(k, k + NGRAM))
            hits += [p for p in pos]
    if not hits:
        return 0.0, 0.0, 0.0
    hits.sort()
    # densest window of matched positions within ~4 minutes of episode time
    best, i = (0, 0, 0), 0
    for j in range(len(hits)):
        while episode[hits[j]][1] - episode[hits[i]][1] > 240:
            i += 1
        if j - i + 1 > best[0]:
            best = (j - i + 1, i, j)
    _, i, j = best
    s, e = episode[hits[i]][1], episode[min(hits[j] + NGRAM, len(episode) - 1)][1]
    return len(covered) / max(1, len(sw)), s, e


def download(url: str, out: Path, section: tuple[float, float] | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    opts = {"format": "bv*[height<=1920][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b", "merge_output_format": "mp4", "outtmpl": str(out.with_suffix(".%(ext)s"))}
    if section:
        opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [section])
        opts["force_keyframes_at_cuts"] = True
    with ydl(**opts) as y:
        y.download([url])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("lang", choices=["en", "hi"])
    ap.add_argument("--shorts", type=int, default=15)
    ap.add_argument("--episodes", type=int, default=25)
    ap.add_argument("--max-pairs", type=int, default=4)
    ap.add_argument("--genre", default="genre.podcast_clip")
    a = ap.parse_args()
    chan = a.handle.lstrip("@")
    cache = SRC / chan
    shorts = list_tab(a.handle, "shorts", a.shorts)
    eps = [e for e in list_tab(a.handle, "videos", a.episodes) if (e.get("duration") or 0) > 600]
    print(f"{chan}: {len(shorts)} shorts, {len(eps)} episodes > 10 min")
    ep_caps = {}
    made = 0
    for sh in shorts:
        if made >= a.max_pairs:
            break
        sc = captions(sh["id"], a.lang, cache)
        if not sc or len(sc) < 25:
            continue
        best = (0.0, None, 0.0, 0.0)
        for ep in eps:
            if ep["id"] not in ep_caps:
                ep_caps[ep["id"]] = captions(ep["id"], a.lang, cache)
            ec = ep_caps[ep["id"]]
            if not ec:
                continue
            share, s, e = match(sc, ec)
            if share > best[0]:
                best = (share, ep, s, e)
        share, ep, s, e = best
        print(f"  short {sh['id']} ({sh['title'][:50]!r}): best match {share:.0%}" + (f" in {ep['id']} {s:.0f}-{e:.0f}s" if ep else ""))
        if share < MIN_MATCH or not ep or e - s > 240:
            continue
        pad = max(0.0, (RAW_TARGET_S - (e - s)) / 2)
        lo, hi = max(0.0, s - pad), e + pad
        gid = f"{chan.lower()}_{sh['id']}"
        d = GOLD / gid
        if (d / "final.mp4").exists():
            made += 1
            continue
        download(f"https://www.youtube.com/shorts/{sh['id']}", d / "final.mp4")
        download(f"https://www.youtube.com/watch?v={ep['id']}", d / "raw" / "raw.mp4", (lo, hi))
        short_dur = sc[-1][1] - sc[0][1] + 2
        (d / "brief.json").write_text(json.dumps({
            "project": gid, "language": "hinglish" if a.lang == "hi" else "en", "genre_hint": a.genre,
            "target_length_s": [round(max(10, short_dur * 0.8), 1), round(short_dur * 1.25, 1)],
            "notes": "Cut a vertical short-form reel from this podcast/talking-head footage."}, indent=1))
        (d / "source.json").write_text(json.dumps({
            "final": f"https://www.youtube.com/shorts/{sh['id']}", "episode": f"https://www.youtube.com/watch?v={ep['id']}",
            "episode_span_s": [round(lo, 1), round(hi, 1)], "matched_span_s": [round(s, 1), round(e, 1)], "match_share": round(share, 3),
            "channel": a.handle, "licence": "YouTube Standard License — internal evaluation only, not redistributed"}, indent=1))
        made += 1
        print(f"  → gold pair {gid}: raw {hi - lo:.0f}s, final ~{short_dur:.0f}s")
    print(f"{chan}: {made} pair(s)")


if __name__ == "__main__":
    try:
        main()
    except RateLimited as exc:
        print(f"ERROR: {exc}")
