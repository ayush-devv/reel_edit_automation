"""`reel assets fetch`: fill the SFX and music libraries reproducibly with commercially safe audio,
each file carrying its licence provenance (source, licence id + URL, attribution, download URL,
date, sha256).

  SFX   1. procedural — synthesised here (reel.procedural_sfx), owned, no licence
        2. Kenney CC0 audio packs (kenney.nl): Interface Sounds, Impact Sounds, UI Audio, Digital Audio
        3. Sonniss GDC bundles — OFF unless --include-sonniss: licence v2.0 says "NO AI TRAINING OR
           USAGE", so the owner needs a legal read first; renders only, never deliver source files
  Music Incompetech (Kevin MacLeod, CC BY 4.0): a pinned list of ~30 tracks across reel moods;
        the exact attribution goes into CREDITS.txt of every package that uses one.

Audio lands under assets/ (gitignored); the indexes and licence records under assets/ are committed.
Index paths are relative to assets/, so the committed index works in any checkout once fetched.
Downloads are untrusted data: only https on an allow-listed host, zips are read member by member
(no extraction paths, size caps) and every sound is decoded by ffmpeg into a fresh WAV.
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import logging
import os
import re
import ssl
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Callable

from reel import assets as assets_mod
from reel import library, procedural_sfx

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; reel-editor/0.1 asset fetch)"
ALLOWED_HOSTS = {"kenney.nl", "incompetech.com", "downloads.sonniss.com"}
Get = Callable[[str, dict], bytes]

LICENCE_URLS = {
    "owned": "",
    "CC0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "Sonniss-GDC-2.0": "https://sonniss.com/gdc-bundle-license/",
}
# never: ShareAlike / NonCommercial / NoDerivatives (credits on a reel are fine; these terms are not)
_FORBIDDEN_LICENCE = re.compile(r"(^|-)(SA|NC|ND)(-|$)", re.I)

MAX_MEMBER_BYTES = 40 * 1024 * 1024
MAX_ZIP_BYTES = 400 * 1024 * 1024


# ------------------------------------------------------------------ http (allow-listed, https only)


def _check_url(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or (u.hostname or "") not in ALLOWED_HOSTS:
        raise ValueError(f"refusing to fetch {url!r}: only https on {sorted(ALLOWED_HOSTS)}")
    return url


def http_get(url: str, headers: dict | None = None, timeout: int = 120) -> bytes:
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    req = urllib.request.Request(_check_url(url), headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:  # noqa: S310 — allow-listed https hosts
        _check_url(r.geturl())  # redirects must stay on the allow-list too
        return r.read()


# ------------------------------------------------------------------ provenance


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def provenance(path: Path, *, source: str, licence: str, attribution: str = "", download_url: str = "", **extra) -> dict:
    if _FORBIDDEN_LICENCE.search(licence):
        raise ValueError(f"{path.name}: licence {licence} is not allowed (no ShareAlike / NonCommercial / NoDerivatives)")
    return {"source": source, "license": licence, "license_url": LICENCE_URLS.get(licence, ""), "attribution": attribution,
            "download_url": download_url, "fetched": datetime.date.today().isoformat(), "sha256": sha256(path), **extra}


def _annotate(entries: list[dict], prov_by_name: dict[str, dict]) -> list[dict]:
    """Merge per-file provenance into index entries (by file name); entries without provenance are dropped."""
    out = []
    for e in entries:
        p = prov_by_name.get(PurePosixPath(e["file"]).name)
        if p is not None:
            out.append({**e, **p})
    return out


def keep_dates(kind: str, entries: list[dict], root: Path) -> list[str]:
    """Unchanged files keep their first `fetched` date (no index churn on re-runs); changed hashes are reported."""
    path = root / ("sfx/sfx_index.json" if kind == "sfx" else "music/music_index.json")
    old = {e["id"]: e for e in json.loads(path.read_text()).get("sfx" if kind == "sfx" else "tracks", [])} if path.exists() else {}
    warnings = []
    for e in entries:
        o = old.get(e["id"])
        if not o or not o.get("sha256"):
            continue
        if o["sha256"] == e["sha256"]:
            e["fetched"] = o.get("fetched", e["fetched"])
        elif e["license"] != "owned":
            warnings.append(f"{e['file']}: content changed since {o.get('fetched')} (sha256 {o['sha256'][:12]} → {e['sha256'][:12]})")
    return warnings


def _safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "_", PurePosixPath(name).stem).strip("_")
    return stem[:80] or "sound"


def _write_sound(src_bytes: bytes, suffix: str, dest: Path, work: Path) -> Path:
    """Untrusted bytes → temp file in `work` → ffmpeg decode → peak-normalised 48 kHz / 24-bit WAV at dest."""
    tmp = work / f"in{suffix}"
    tmp.write_bytes(src_bytes)
    try:
        y = procedural_sfx.decode(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return procedural_sfx.write_wav(dest, procedural_sfx.normalise_peak(y, dest.name))


# ------------------------------------------------------------------ 1. procedural


def fetch_procedural(root: Path) -> list[dict]:
    folder = root / "sfx" / "procedural"
    paths = procedural_sfx.render_all(folder)
    gen = procedural_sfx.ffmpeg_version()
    prov = {p.name: provenance(p, source="reel procedural", licence="owned", generator=f"reel.procedural_sfx · {gen} lavfi", recipe=p.stem)
            for p in paths}
    entries = library.index_sfx(folder, source="reel procedural", license_="owned", rel_to=root)
    return _annotate(entries, prov)


# ------------------------------------------------------------------ 2. Kenney (CC0)

KENNEY_PACKS = {"interface-sounds": "Interface Sounds", "impact-sounds": "Impact Sounds", "ui-audio": "UI Audio", "digital-audio": "Digital Audio"}


def kenney_zip_url(slug: str, get: Get = http_get) -> str:
    """kenney.nl/download-link/<hex of "assets/<slug>"> (Referer = the asset page) → {"url": signed zip URL}."""
    page = f"https://kenney.nl/assets/{slug}"
    body = get(f"https://kenney.nl/download-link/{('assets/' + slug).encode().hex()}", {"Referer": page, "Accept": "application/json"})
    url = json.loads(body).get("url", "")
    if not url.startswith("https://kenney.nl/download/"):
        raise ValueError(f"unexpected Kenney download link for {slug}: {url[:120]!r}")
    return url


def ingest_kenney_zip(data: bytes, slug: str, title: str, root: Path, work: Path) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(data))
    infos = [i for i in z.infolist() if not i.is_dir()]
    if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
        raise ValueError(f"Kenney {title}: archive too large")
    folder = root / "sfx" / "kenney" / slug
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.wav"):
        old.unlink()
    page = f"https://kenney.nl/assets/{slug}"
    source = f"Kenney {title}"
    prov: dict[str, dict] = {}
    for info in infos:
        base = PurePosixPath(info.filename).name
        if base.lower() == "license.txt":
            lic = root / "licenses" / f"kenney-{slug}.txt"
            lic.parent.mkdir(parents=True, exist_ok=True)
            lic.write_text(z.read(info).decode("utf-8", "replace").replace("\r\n", "\n").strip() + f"\n\nDownloaded from {page}\n")
            continue
        if not base.lower().endswith(".ogg") or base.startswith(".") or info.file_size > MAX_MEMBER_BYTES:
            continue
        stem = _safe_stem(base)
        if library.sfx_category(Path(f"{stem}.wav")) is None:  # footsteps, lasers, … — not reel SFX
            continue
        wav = _write_sound(z.read(info), ".ogg", folder / f"{stem}.wav", work)
        prov[wav.name] = provenance(wav, source=source, licence="CC0-1.0", download_url=page, source_file=info.filename)
    entries = library.index_sfx(folder, source=source, license_="CC0-1.0", rel_to=root)
    return _annotate(entries, prov)


def fetch_kenney(root: Path, *, get: Get = http_get, packs: dict[str, str] = KENNEY_PACKS) -> tuple[list[dict], list[str]]:
    entries, problems = [], []
    for slug, title in packs.items():
        try:
            data = get(kenney_zip_url(slug, get), {"Referer": f"https://kenney.nl/assets/{slug}"})
            with tempfile.TemporaryDirectory(prefix="reel-kenney-") as work:
                got = ingest_kenney_zip(data, slug, title, root, Path(work))
        except Exception as e:  # noqa: BLE001 — one pack failing never blocks the rest (procedural SFX keep the library usable)
            problems.append(f"Kenney {title}: skipped ({type(e).__name__}: {e})")
            continue
        entries += got
    return entries, problems


# ------------------------------------------------------------------ 3. Sonniss GDC (opt-in, legal review pending)

SONNISS_RESTRICTIONS = ("Sonniss GDC Bundle licence v2.0: royalty-free, no attribution; RENDERS ONLY — never deliver or share the "
                        "source sound files (no supplying the SFX as SFX to others); the licence says 'NO AI TRAINING OR USAGE' "
                        "— owner's legal review pending before any use.")


class RangeFile(io.RawIOBase):
    """Seekable read-only view of a remote file through HTTP range requests (reads a zip's central
    directory and single members without downloading the multi-GB bundle)."""

    def __init__(self, url: str, size: int, get_range: Callable[[str, int, int], bytes]):
        self.url, self.size, self.pos, self.get_range, self.requests = url, size, 0, get_range, 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def readinto(self, b) -> int:
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        data = self.get_range(self.url, self.pos, self.pos + n - 1)
        self.requests += 1
        if len(data) != n:
            raise OSError(f"range request returned {len(data)} bytes, wanted {n}")
        memoryview(b).cast("B")[:n] = data
        self.pos += n
        return n


def _http_size(url: str) -> int:
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
    req = urllib.request.Request(_check_url(url), method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:  # noqa: S310
        return int(r.headers["Content-Length"])


def _http_range(url: str, start: int, end: int) -> bytes:
    return http_get(url, {"Range": f"bytes={start}-{end}"})


def fetch_sonniss(root: Path, urls: list[str], *, pattern: str | None = None, per_category: int = 12,
                  size: Callable[[str], int] = _http_size, get_range: Callable[[str, int, int], bytes] = _http_range) -> tuple[list[dict], list[str]]:
    entries, problems = [], []
    rx = re.compile(pattern, re.I) if pattern else None
    for url in urls:
        _check_url(url)
        bundle = _safe_stem(PurePosixPath(urllib.parse.urlsplit(url).path).name)
        folder = root / "sfx" / "sonniss" / bundle
        try:
            # 256 KiB read-ahead: few requests per member, little over-read past small members
            z = zipfile.ZipFile(io.BufferedReader(RangeFile(url, size(url), get_range), buffer_size=1 << 18))
        except Exception as e:  # noqa: BLE001
            problems.append(f"Sonniss {bundle}: skipped ({type(e).__name__}: {e})")
            continue
        taken: Counter = Counter()
        prov: dict[str, dict] = {}
        with tempfile.TemporaryDirectory(prefix="reel-sonniss-") as work:
            for info in sorted(z.infolist(), key=lambda i: i.filename):
                p = PurePosixPath(info.filename)
                if info.is_dir() or p.suffix.lower() not in (".wav", ".aif", ".aiff", ".flac") or info.file_size > MAX_MEMBER_BYTES:
                    continue
                cat = library.sfx_category(Path(info.filename))
                if cat is None or taken[cat] >= per_category or (rx and not rx.search(info.filename)):
                    continue
                name = f"{_safe_stem(p.parent.name)}_{_safe_stem(p.name)}.wav" if p.parent.name else f"{_safe_stem(p.name)}.wav"
                try:
                    wav = _write_sound(z.read(info), p.suffix.lower(), folder / name, Path(work))
                except Exception as e:  # noqa: BLE001
                    problems.append(f"Sonniss {info.filename}: {e}")
                    continue
                taken[cat] += 1
                prov[wav.name] = provenance(wav, source=f"Sonniss {bundle}", licence="Sonniss-GDC-2.0", download_url=f"{url}#{info.filename}",
                                            source_file=info.filename, restrictions=SONNISS_RESTRICTIONS)
        if prov:
            entries += _annotate(library.index_sfx(folder, source=f"Sonniss {bundle}", license_="Sonniss-GDC-2.0", rel_to=root), prov)
    return entries, problems


# ------------------------------------------------------------------ music: Incompetech (CC BY 4.0)

PIECES_URL = "https://incompetech.com/music/royalty-free/pieces.json"
MP3_BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
# Exact "Attribution Code" from each track page on incompetech.com (checked 2026-11-19).
ATTRIBUTION = ('"{title}" Kevin MacLeod (incompetech.com)\n'
               "Licensed under Creative Commons: By Attribution 4.0 License\n"
               "http://creativecommons.org/licenses/by/4.0/")
MUSIC_MIN_S, MUSIC_MAX_S = 60, 240

# Pinned (pieces.json drifts): filename → (mood, energy). Chosen 2026-11-19 from the catalogue's
# feel tags for short-form reels; all 60 s – 4 min.
INCOMPETECH_TRACKS: dict[str, tuple[str, str]] = {
    # upbeat / bright
    "Carefree.mp3": ("upbeat", "medium"),
    "Wallpaper.mp3": ("upbeat", "medium"),
    "Life of Riley.mp3": ("upbeat", "medium"),
    "Voxel Revolution.mp3": ("upbeat", "high"),
    "Paradise_Found.mp3": ("upbeat", "high"),
    "Happy Alley.mp3": ("upbeat", "high"),
    "Heartwarming.mp3": ("upbeat", "medium"),
    # chill / relaxed
    "Easy Lemon.mp3": ("chill", "low"),
    "Pamgaea.mp3": ("chill", "low"),
    "Lobby Time.mp3": ("chill", "medium"),
    "Dreamer.mp3": ("chill", "low"),
    "Chill Wave.mp3": ("chill", "low"),
    # cinematic / epic
    "Heroic Age.mp3": ("cinematic", "high"),
    "Hitman.mp3": ("cinematic", "high"),
    "Undaunted.mp3": ("cinematic", "high"),
    "Our Story Begins.mp3": ("cinematic", "medium"),
    "Volatile Reaction.mp3": ("cinematic", "high"),
    # corporate / driving
    "Motivator.mp3": ("corporate", "high"),
    "Nonstop.mp3": ("corporate", "high"),
    "Werq.mp3": ("corporate", "medium"),
    "Getting it Done.mp3": ("corporate", "medium"),
    "Enter the Party.mp3": ("corporate", "high"),
    # playful / quirky
    "Monkeys Spinning Monkeys.mp3": ("playful", "high"),
    "Fluffing a Duck.mp3": ("playful", "medium"),
    "Sneaky Snitch.mp3": ("playful", "medium"),
    "Investigations.mp3": ("playful", "low"),
    "Quirky Dog.mp3": ("playful", "medium"),
    # emotional
    "Bittersweet.mp3": ("emotional", "low"),
    "Rains Will Fall.mp3": ("emotional", "low"),
    "Dream Culture.mp3": ("emotional", "low"),
    "Touching Moments Two - Higher.mp3": ("emotional", "low"),
    # suspense / mystery
    "Kool Kats.mp3": ("suspense", "medium"),
    "Hidden Agenda.mp3": ("suspense", "medium"),
}


def _length_s(text: str) -> int:
    parts = [int(p) for p in (text or "0").split(":")]
    return sum(v * 60 ** i for i, v in enumerate(reversed(parts)))


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def fetch_incompetech(root: Path, *, get: Get = http_get, tracks: dict[str, tuple[str, str]] = INCOMPETECH_TRACKS,
                      refresh: bool = False) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    pieces = {p.get("filename"): p for p in json.loads(get(PIECES_URL, {}))}
    folder = root / "music" / "incompetech"
    folder.mkdir(parents=True, exist_ok=True)
    meta: dict[str, dict] = {}
    for filename, (mood, energy) in tracks.items():
        p = pieces.get(filename)
        if not p:
            problems.append(f"Incompetech {filename}: no longer in pieces.json — skipped")
            continue
        if not MUSIC_MIN_S <= _length_s(p.get("length", "")) <= MUSIC_MAX_S:
            problems.append(f"Incompetech {filename}: length {p.get('length')} outside {MUSIC_MIN_S}–{MUSIC_MAX_S} s — skipped")
            continue
        url = MP3_BASE + urllib.parse.quote(filename)
        target = folder / f"{_slug(p['title'])}.mp3"
        if refresh or not target.exists():
            try:
                data = get(url, {})
            except Exception as e:  # noqa: BLE001
                problems.append(f"Incompetech {filename}: download failed ({e})")
                continue
            if len(data) < 100_000 or not (data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
                problems.append(f"Incompetech {filename}: not an MP3 ({len(data)} bytes) — skipped")
                continue
            tmp = target.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(target)
        meta[target.name] = {
            "title": p["title"], "mood": mood, "energy": energy, "feel": p.get("feel") or "", "bpm_listed": p.get("bpm"),
            "isrc": p.get("isrc"), "instruments": p.get("instruments") or "",
            **provenance(target, source="Incompetech (Kevin MacLeod)", licence="CC-BY-4.0", attribution=ATTRIBUTION.format(title=p["title"]),
                         download_url=url, attribution_source="incompetech.com track page 'Attribution Code' (checked 2026-11-19)"),
        }
    entries = library.index_music(folder, source="Incompetech (Kevin MacLeod)", license_="CC-BY-4.0", rel_to=root)
    out = []
    for e in entries:
        m = meta.get(PurePosixPath(e["file"]).name)
        if m is not None:  # files on disk that are no longer pinned are not indexed
            out.append({**e, **m})
    return out, problems


INCOMPETECH_NOTE = """Incompetech — Kevin MacLeod — Creative Commons Attribution 4.0 (CC BY 4.0)
https://creativecommons.org/licenses/by/4.0/

Commercial use allowed; attribution REQUIRED wherever the work is used (for a reel: in the post
caption / description). The exact credit for each track is stored in assets/music/music_index.json
("attribution") and written to CREDITS.txt in every delivery package that uses the track.

Credit format (incompetech.com track page, "Attribution Code", checked 2026-11-19):
"<Title>" Kevin MacLeod (incompetech.com)
Licensed under Creative Commons: By Attribution 4.0 License
http://creativecommons.org/licenses/by/4.0/

Source catalogue: https://incompetech.com/music/royalty-free/pieces.json
Files: https://incompetech.com/music/royalty-free/mp3-royaltyfree/<file name>
Never used: ShareAlike, NonCommercial or NoDerivatives licences.
"""

PROCEDURAL_NOTE = """Procedural SFX (assets/sfx/procedural/) — owned, no licence, no attribution.

Synthesised by reel.procedural_sfx with ffmpeg lavfi (seeded noise, tone/envelope expressions,
filters); `reel assets fetch` re-creates byte-identical files on the same ffmpeg build.
"""

SONNISS_NOTE = f"""Sonniss GDC game-audio bundles (assets/sfx/sonniss/) — fetched only with --include-sonniss.

Licence: https://sonniss.com/gdc-bundle-license/
{SONNISS_RESTRICTIONS}
"""


def _write_note(root: Path, name: str, text: str) -> None:
    p = root / "licenses" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


# ------------------------------------------------------------------ orchestration


def _disk_bytes(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) if folder.exists() else 0


def fetch(root: Path = assets_mod.ASSETS_DIR, *, procedural: bool = True, kenney: bool = True, music: bool = True,
          sonniss_urls: list[str] | None = None, sonniss_pattern: str | None = None, sonniss_per_category: int = 12,
          refresh: bool = False, get: Get = http_get) -> dict:
    """Fill the libraries; each source replaces its own previous index entries. Returns a summary."""
    problems: list[str] = []
    sfx: list[dict] = []
    tracks: list[dict] = []
    if procedural:
        sfx += fetch_procedural(root)
        _write_note(root, "procedural-owned.txt", PROCEDURAL_NOTE)
    if kenney:
        got, why = fetch_kenney(root, get=get)
        sfx += got
        problems += why
    if sonniss_urls:
        got, why = fetch_sonniss(root, sonniss_urls, pattern=sonniss_pattern, per_category=sonniss_per_category)
        sfx += got
        problems += why
        _write_note(root, "sonniss-gdc.txt", SONNISS_NOTE)
    if music:
        try:
            tracks, why = fetch_incompetech(root, get=get, refresh=refresh)
            problems += why
            _write_note(root, "incompetech-cc-by-4.0.txt", INCOMPETECH_NOTE)
        except Exception as e:  # noqa: BLE001
            problems.append(f"Incompetech: skipped ({type(e).__name__}: {e})")
    if sfx:
        problems += keep_dates("sfx", sfx, root)
        library.write_index("sfx", sfx, replace=True, root=root)
    if tracks:
        problems += keep_dates("music", tracks, root)
        library.write_index("music", tracks, replace=True, root=root)
    idx = assets_mod.load(root)
    return {
        "sfx_new": len(sfx), "music_new": len(tracks),
        "sfx_by_category": dict(sorted(Counter(e.get("category", "?") for e in idx.sfx.values()).items())),
        "sfx_by_source": dict(sorted(Counter(e.get("source", "?") for e in idx.sfx.values()).items())),
        "music_by_mood": dict(sorted(Counter(e.get("mood", "?") for e in idx.music.values()).items())),
        "disk_bytes": {"sfx": _disk_bytes(root / "sfx"), "music": _disk_bytes(root / "music")},
        "problems": problems,
    }
