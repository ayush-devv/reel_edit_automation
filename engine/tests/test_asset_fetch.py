"""`reel assets fetch`: procedural SFX synthesis, Kenney / Incompetech / Sonniss ingestion (network
mocked), provenance fields, portable index paths, credits for a timeline and the package README."""

import io
import json
import socket
import subprocess
import zipfile
from pathlib import Path

import numpy as np
import pytest

from reel import assets, config, fetch_assets, library, package, procedural_sfx
from reel.schemas.timeline import Asset, AssetKind, AudioClip, Timeline

try:
    config.ffmpeg_path()
    import librosa  # noqa: F401
    import soundfile  # noqa: F401

    READY = True
except Exception:  # noqa: BLE001
    READY = False

needs_ffmpeg = [pytest.mark.integration, pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + librosa/soundfile")]
PROV_FIELDS = ("source", "license", "license_url", "attribution", "download_url", "fetched", "sha256")


def _encode(tmp: Path, name: str, expr: str, dur: float, codec: list[str]) -> bytes:
    out = tmp / name
    subprocess.run([str(config.ffmpeg_path()), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"aevalsrc='{expr}':s=44100:d={dur}", *codec, str(out)], check=True)
    return out.read_bytes()


# ------------------------------------------------------------------ unit (no ffmpeg, no network)


def test_kenney_and_procedural_names_categorise():
    cases = {"impactPunch_heavy_000": "hit", "click_001": "click", "switch23": "click", "mouseclick1": "click", "confirmation_002": "ding",
             "zapTwoTone": "glitch", "threeTone1": "ding", "drop_003": "pop", "pluck_001": "pop", "glitch_004": "glitch",
             "footstep_grass_000": None, "laser3": None, "camera_shutter_click": "camera", "cash_register_ding": "cash"}
    for stem, cat in cases.items():
        assert library.sfx_category(Path(f"{stem}.wav")) == cat, stem
    for r in procedural_sfx.recipes():
        assert library.sfx_category(Path(f"{r.name}.wav")) == r.category, r.name
    cats = {r.category for r in procedural_sfx.recipes()}
    assert cats == set(library.TYPICAL_MS), "every editor SFX category has procedural variants"
    assert all(sum(r.category == c for r in procedural_sfx.recipes()) >= 3 for c in cats)


def test_forbidden_licences_and_hosts_refused(tmp_path):
    f = tmp_path / "x.wav"
    f.write_bytes(b"x")
    for bad in ("CC-BY-SA-4.0", "CC-BY-NC-4.0", "CC-BY-ND-4.0"):
        with pytest.raises(ValueError):
            fetch_assets.provenance(f, source="s", licence=bad)
    p = fetch_assets.provenance(f, source="s", licence="CC0-1.0")
    assert all(k in p for k in PROV_FIELDS) and p["license_url"].startswith("https://creativecommons.org/publicdomain/zero")
    for url in ("http://kenney.nl/x", "https://evil.example/x.zip", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            fetch_assets.http_get(url)


def test_kenney_download_link_must_be_kenney():
    calls = []

    def get(url, headers):
        calls.append((url, headers))
        return json.dumps({"url": "https://kenney.nl/download/abc/def?expires=1"}).encode()

    assert fetch_assets.kenney_zip_url("ui-audio", get).startswith("https://kenney.nl/download/")
    assert calls[0][0] == "https://kenney.nl/download-link/" + b"assets/ui-audio".hex()
    assert calls[0][1]["Referer"] == "https://kenney.nl/assets/ui-audio"
    with pytest.raises(ValueError):
        fetch_assets.kenney_zip_url("ui-audio", lambda u, h: b'{"url": "https://evil.example/x.zip"}')


def _tl(*clips: tuple[str, str]) -> Timeline:
    return Timeline(fps="30/1", width=1080, height=1920, duration_f=300,
                    assets={a: Asset(id=a, kind=AssetKind.music if r == "music" else AssetKind.sfx, uri=f"/x/{a}.wav") for a, r in clips},
                    video=[], audio=[AudioClip(id=f"a{i}", asset=a, at_f=0, dur_f=30, role=r) for i, (a, r) in enumerate(clips)])


def _idx() -> assets.Indexes:
    att = fetch_assets.ATTRIBUTION.format(title="Carefree")
    return assets.Indexes(
        sfx={"whoosh_1": {"id": "whoosh_1", "name": "whoosh_soft", "source": "reel procedural", "license": "owned", "attribution": ""},
             "click_2": {"id": "click_2", "name": "click_001", "source": "Kenney UI Audio", "license": "CC0-1.0",
                         "license_url": fetch_assets.LICENCE_URLS["CC0-1.0"], "attribution": ""}},
        music={"music_c": {"id": "music_c", "title": "Carefree", "source": "Incompetech (Kevin MacLeod)", "license": "CC-BY-4.0",
                           "license_url": fetch_assets.LICENCE_URLS["CC-BY-4.0"], "attribution": att}})


def test_credits_for_incompetech_track_and_none_for_owned_or_cc0():
    idx = _idx()
    lines = library.credit_lines(_tl(("music_c", "music"), ("whoosh_1", "sfx"), ("click_2", "sfx")), idx)
    assert lines == ['"Carefree" Kevin MacLeod (incompetech.com)\n'
                     "Licensed under Creative Commons: By Attribution 4.0 License\n"
                     "http://creativecommons.org/licenses/by/4.0/"]
    assert library.credit_lines(_tl(("whoosh_1", "sfx"), ("click_2", "sfx")), idx) == []
    text = package.credits_text(lines)
    assert "paste into the post caption" in text and '"Carefree" Kevin MacLeod' in text
    md = package.readme(_tl(("music_c", "music"), ("click_2", "sfx")), idx, None, "PASS", lines)
    assert "CREDITS.txt" in md and "CC-BY-4.0" in md and "attribution required" in md
    assert "CREDITS.txt" not in package.readme(_tl(("click_2", "sfx")), idx, None, "PASS", [])


def test_relative_index_paths_resolve_and_missing_audio_is_not_offered(tmp_path):
    (tmp_path / "sfx" / "procedural").mkdir(parents=True)
    (tmp_path / "sfx" / "procedural" / "pop_bubble.wav").write_bytes(b"RIFF")
    owner = tmp_path / "owner" / "hit.wav"
    owner.parent.mkdir()
    owner.write_bytes(b"RIFF")
    (tmp_path / "sfx" / "sfx_index.json").write_text(json.dumps({"sfx": [
        {"id": "pop_1", "file": "sfx/procedural/pop_bubble.wav", "duration_ms": 180, "peak_ms": 0},
        {"id": "hit_2", "file": str(owner), "duration_ms": 500, "peak_ms": 10},
        {"id": "boom_3", "file": "sfx/procedural/boom_subdrop.wav", "duration_ms": 1500, "peak_ms": 10},  # index committed, audio not fetched
        {"id": "hit_4", "file": "/unplugged/drive/hit.wav", "duration_ms": 500, "peak_ms": 10}]}))
    idx = assets.load(tmp_path)
    assert idx.sfx["pop_1"]["file"] == str((tmp_path / "sfx/procedural/pop_bubble.wav").resolve())
    assert idx.sfx["hit_2"]["file"] == str(owner)
    assert set(idx.sfx) == {"pop_1", "hit_2"}


def test_sfx_menu_alternates_sources():
    sfx = {f"hit_{s}{i}": {"id": f"hit_{s}{i}", "category": "hit", "duration_ms": 700, "peak_ms": 0, "source": s}
           for s in ("A", "B") for i in range(5)}
    picked = library.sfx_menu(sfx, per_category=4)["hit"]
    assert [e["source"] for e in picked] == ["A", "B", "A", "B"]


# ------------------------------------------------------------------ integration (pinned ffmpeg, network mocked)


@needs_ffmpeg[0]
@needs_ffmpeg[1]
def test_procedural_sfx_deterministic_with_sensible_shape(tmp_path):
    import soundfile as sf

    entries = fetch_assets.fetch_procedural(tmp_path)
    recipes = {r.name: r for r in procedural_sfx.recipes()}
    assert len(entries) == len(recipes)
    for e in entries:
        r = recipes[e["name"]]
        assert e["category"] == r.category and e["license"] == "owned" and e["attribution"] == ""
        assert all(k in e for k in PROV_FIELDS) and len(e["sha256"]) == 64
        assert e["file"] == f"sfx/procedural/{r.name}.wav" and e["id"] == library._id(r.category, e["file"])  # portable
        assert abs(e["duration_ms"] - r.dur * 1000) <= 1
        assert 0 <= e["peak_ms"] < e["duration_ms"], e["name"]  # aligned point lies inside the sound
        y, rate = sf.read(str(tmp_path / e["file"]), always_2d=True)
        assert rate == 48000 and y.shape[1] == 2 and sf.info(str(tmp_path / e["file"])).subtype == "PCM_24"
        assert abs(20 * np.log10(np.abs(y).max()) - procedural_sfx.PEAK_DBFS) < 0.1
        frac = e["peak_ms"] / e["duration_ms"]
        if r.category in ("riser",):
            assert frac > 0.8, e["name"]  # builds into the cut
        if r.category in ("hit", "boom", "pop", "click"):
            assert e["peak_ms"] <= 250, e["name"]  # transient up front
        if r.category in ("whoosh", "swipe"):
            assert 0.2 < frac < 0.98, e["name"]  # swells through the middle
    # deterministic: a second render is byte-identical
    again = procedural_sfx.render_all(tmp_path / "again", only=["whoosh_soft", "riser_tension", "cash_coins_spill", "typing_fast"])
    for p in again:
        assert p.read_bytes() == (tmp_path / "sfx" / "procedural" / p.name).read_bytes(), p.name


@needs_ffmpeg[0]
@needs_ffmpeg[1]
def test_kenney_zip_ingest_skips_junk_and_records_cc0(tmp_path):
    ogg = ["-c:a", "libvorbis"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("License.txt", "Interface Sounds (1.0)\nLicense: (Creative Commons Zero, CC0)\n")
        z.writestr("Kenney.url", "[InternetShortcut]\nURL=https://kenney.nl\n")
        z.writestr("Audio/click_001.ogg", _encode(tmp_path, "c.ogg", "sin(2*PI*2000*t)*exp(-t/0.01)", 0.1, ogg))
        z.writestr("Audio/footstep_grass_000.ogg", _encode(tmp_path, "f.ogg", "sin(2*PI*200*t)*exp(-t/0.05)", 0.2, ogg))
        z.writestr("../../impactPunch_heavy_000.ogg", _encode(tmp_path, "h.ogg", "sin(2*PI*80*t)*exp(-t/0.1)", 0.4, ogg))
    zbytes = buf.getvalue()

    def get(url, headers):
        if "/download-link/" in url:
            return json.dumps({"url": "https://kenney.nl/download/x/y?expires=1"}).encode()
        assert url.startswith("https://kenney.nl/download/") and headers.get("Referer")
        return zbytes

    root = tmp_path / "assets"
    entries, problems = fetch_assets.fetch_kenney(root, get=get, packs={"interface-sounds": "Interface Sounds"})
    assert not problems
    assert sorted(e["category"] for e in entries) == ["click", "hit"]  # footsteps skipped
    assert {Path(e["file"]).parent.as_posix() for e in entries} == {"sfx/kenney/interface-sounds"}  # zip-slip name flattened
    for e in entries:
        assert e["license"] == "CC0-1.0" and e["attribution"] == "" and e["download_url"] == "https://kenney.nl/assets/interface-sounds"
        assert e["source_file"].endswith(".ogg") and all(k in e for k in PROV_FIELDS)
    assert "CC0" in (root / "licenses" / "kenney-interface-sounds.txt").read_text()
    assert not list(root.rglob("*.ogg")) and not list(root.rglob("*.url"))
    # a pack whose download fails is skipped with a message, not an exception
    def broken(url, headers):
        raise OSError("offline")
    entries, problems = fetch_assets.fetch_kenney(root, get=broken, packs={"ui-audio": "UI Audio"})
    assert entries == [] and "UI Audio" in problems[0]


@needs_ffmpeg[0]
@needs_ffmpeg[1]
def test_incompetech_fetch_attribution_and_provenance(tmp_path):
    mp3 = _encode(tmp_path, "m.mp3", "0.4*sin(2*PI*220*t)*(0.5+0.5*gt(mod(t,0.5),0.4))", 70.0, ["-c:a", "libmp3lame", "-b:a", "64k"])
    pieces = [{"title": "Carefree", "filename": "Carefree.mp3", "length": "00:03:25", "bpm": "96", "feel": "Bouncy, Bright", "isrc": "X1"},
              {"title": "Too Long", "filename": "Too Long.mp3", "length": "00:08:00", "bpm": "90", "feel": "Calming", "isrc": "X2"}]
    got = []

    def get(url, headers):
        got.append(url)
        if url == fetch_assets.PIECES_URL:
            return json.dumps(pieces).encode()
        assert url.startswith(fetch_assets.MP3_BASE)
        return mp3

    tracks = {"Carefree.mp3": ("upbeat", "medium"), "Too Long.mp3": ("chill", "low"), "Gone.mp3": ("chill", "low")}
    entries, problems = fetch_assets.fetch_incompetech(tmp_path, get=get, tracks=tracks)
    assert len(entries) == 1 and len(problems) == 2  # too long + no longer listed
    e = entries[0]
    assert e["title"] == "Carefree" and e["mood"] == "upbeat" and e["energy"] == "medium" and e["bpm"] > 0
    assert e["license"] == "CC-BY-4.0" and e["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert e["attribution"].splitlines() == ['"Carefree" Kevin MacLeod (incompetech.com)',
                                             "Licensed under Creative Commons: By Attribution 4.0 License",
                                             "http://creativecommons.org/licenses/by/4.0/"]
    assert e["download_url"] == fetch_assets.MP3_BASE + "Carefree.mp3" and e["file"] == "music/incompetech/carefree.mp3"
    assert all(k in e for k in PROV_FIELDS)
    # cached: a re-run does not download the MP3 again, and keeps the first fetch date
    got.clear()
    library.write_index("music", entries, root=tmp_path)
    again, _ = fetch_assets.fetch_incompetech(tmp_path, get=get, tracks={"Carefree.mp3": ("upbeat", "medium")})
    assert got == [fetch_assets.PIECES_URL]
    again[0]["fetched"] = "2000-01-01"
    assert fetch_assets.keep_dates("music", again, tmp_path) == [] and again[0]["fetched"] == entries[0]["fetched"]


@needs_ffmpeg[0]
@needs_ffmpeg[1]
def test_sonniss_reads_single_members_by_range_and_marks_restrictions(tmp_path):
    import soundfile as sf

    wav = tmp_path / "w.wav"
    t = np.arange(4800) / 48000
    sf.write(str(wav), (0.5 * np.sin(2 * np.pi * 300 * t) * np.exp(-t / 0.03)).astype(np.float32), 48000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("Bundle/Impacts/Big Hit 01.wav", wav.read_bytes())
        z.writestr("Bundle/Foley/Door Creak.wav", wav.read_bytes())  # no category → never downloaded
        z.writestr("Bundle/Big Ambience.wav", b"\0" * 2_000_000)  # filler the reader must not fetch
    data = buf.getvalue()
    ranges = []

    def get_range(url, a, b):
        ranges.append((a, b))
        return data[a:b + 1]

    url = "https://downloads.sonniss.com/gdc2024-bundle.zip"
    entries, problems = fetch_assets.fetch_sonniss(tmp_path, [url], size=lambda u: len(data), get_range=get_range)
    assert not problems and len(entries) == 1
    e = entries[0]
    assert e["category"] == "hit" and e["license"] == "Sonniss-GDC-2.0" and "RENDERS ONLY" in e["restrictions"]
    assert "NO AI TRAINING" in e["restrictions"] and e["download_url"] == f"{url}#Bundle/Impacts/Big Hit 01.wav"
    assert sum(b - a + 1 for a, b in ranges) < len(data) / 2  # only the directory + one member were read
    with pytest.raises(ValueError):
        fetch_assets.fetch_sonniss(tmp_path, ["https://evil.example/x.zip"], size=lambda u: 0, get_range=get_range)


# ------------------------------------------------------------------ live network (skipped offline)


def _online(host: str) -> bool:
    try:
        socket.create_connection((host, 443), timeout=3).close()
        return True
    except OSError:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _online("kenney.nl") or not _online("incompetech.com"), reason="needs network")
def test_live_sources_still_answer():
    assert fetch_assets.kenney_zip_url("ui-audio").startswith("https://kenney.nl/download/")
    pieces = {p["filename"] for p in json.loads(fetch_assets.http_get(fetch_assets.PIECES_URL))}
    missing = set(fetch_assets.INCOMPETECH_TRACKS) - pieces
    assert not missing, f"pinned tracks no longer listed: {missing}"
