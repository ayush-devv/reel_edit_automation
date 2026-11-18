# /// script
# requires-python = ">=3.11"
# dependencies = ["yt-dlp"]
# ///
"""Connectivity + metadata probe: list a few Shorts and long videos of a channel (no media download)."""
import json, sys
import yt_dlp

opts = {"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": int(sys.argv[2]) if len(sys.argv) > 2 else 5}
with yt_dlp.YoutubeDL(opts) as y:
    info = y.extract_info(sys.argv[1], download=False)
for e in info.get("entries", [])[: opts["playlistend"]]:
    print(json.dumps({k: e.get(k) for k in ("id", "title", "duration", "view_count")}, ensure_ascii=False))
