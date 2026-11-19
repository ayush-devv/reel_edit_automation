"""NLE escape-hatch package (ADR-0018), written every run to export/package/:

  reel.mp4                 the deliverable
  overlay.mov              captions/titles/flashes, ProRes 4444 with alpha
  stems/{dialogue,music,sfx}.wav   finished buses before delivery loudness
  captions.srt / captions.vtt      caption pages
  timeline.fcpxml          Final Cut Pro (1.10): the cut on the mezzanines + overlay + stems
  timeline.otio            OpenTimelineIO (DaVinci Resolve, Premiere via plugin, Avid)
  edit_list.md             every decision with the Editor's reason
  README.md                what is baked where, how to open it, licences of assets used
  CREDITS.txt              only when a used asset requires attribution (CC BY music) — paste into the caption
"""

from __future__ import annotations

import os
import shutil
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from reel import library, render
from reel import timebase as tb
from reel.schemas.plan import FinishPlan, StoryPlan
from reel.schemas.timeline import Timeline
from reel.workspace import atomic_write_bytes

STEMS = ("dialogue", "music", "sfx")


def _link(src: Path, dst: Path) -> None:
    """Hard link when possible (same disk, no extra space), else copy."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


# ------------------------------------------------------------------ captions


def _ts(frame: int, fps: Fraction, sep: str) -> str:
    ms = int(round(float(Fraction(frame) / fps) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def srt(tl: Timeline) -> str:
    fps = tb.parse_rate(tl.fps)
    out = []
    for n, p in enumerate(tl.captions.pages if tl.captions else [], 1):
        out += [str(n), f"{_ts(p.start_f, fps, ',')} --> {_ts(p.end_f, fps, ',')}", " ".join(w.text for w in p.words), ""]
    return "\n".join(out)


def vtt(tl: Timeline) -> str:
    fps = tb.parse_rate(tl.fps)
    out = ["WEBVTT", ""]
    for p in tl.captions.pages if tl.captions else []:
        out += [f"{_ts(p.start_f, fps, '.')} --> {_ts(p.end_f, fps, '.')}", " ".join(w.text for w in p.words), ""]
    return "\n".join(out)


# ------------------------------------------------------------------ FCPXML


def _t(frames: int, fps: Fraction) -> str:
    """Rational time on the frame grid, as FCPXML wants it ("N/Ds")."""
    v = Fraction(frames) / fps
    return f"{v.numerator}/{v.denominator}s" if v.denominator != 1 else f"{v.numerator}s"


def fcpxml(tl: Timeline, root: Path, pkg: Path, name: str) -> str:
    fps = tb.parse_rate(tl.fps)
    frame_dur = f"{fps.denominator}/{fps.numerator}s"
    doc = ET.Element("fcpxml", version="1.10")
    res = ET.SubElement(doc, "resources")
    ET.SubElement(res, "format", id="r_seq", frameDuration=frame_dur, width=str(tl.width), height=str(tl.height), name=f"{tl.width}x{tl.height}")
    base = sorted((c for c in tl.video if c.id.startswith("v_")), key=lambda c: c.at_f)
    formats, assets = {}, {}
    for c in base:
        if c.asset in assets:
            continue
        uri = (root / tl.assets[c.asset].uri).resolve()
        w, h = render.source_size(uri)
        if (w, h) not in formats:
            formats[(w, h)] = f"r_fmt{len(formats) + 1}"
            ET.SubElement(res, "format", id=formats[(w, h)], frameDuration=frame_dur, width=str(w), height=str(h))
        fid = formats[(w, h)]
        dur_f = tb.us_to_frame(tl.assets[c.asset].duration_us or 0, fps, mode="floor")
        a = ET.SubElement(res, "asset", id=f"a_{c.asset}", name=c.asset, start="0s", duration=_t(dur_f, fps), hasVideo="1",
                          hasAudio="1", format=fid, audioSources="1", audioChannels="2", audioRate="48000")
        ET.SubElement(a, "media-rep", kind="original-media", src=uri.as_uri())
        assets[c.asset] = a
    extra = {"overlay": pkg / "overlay.mov", **{s: pkg / "stems" / f"{s}.wav" for s in STEMS}}
    for key, path in extra.items():
        a = ET.SubElement(res, "asset", id=f"a_{key}", name=key, start="0s", duration=_t(tl.duration_f, fps),
                          hasVideo="1" if key == "overlay" else "0", hasAudio="0" if key == "overlay" else "1",
                          **({"format": "r_seq"} if key == "overlay" else {"audioSources": "1", "audioChannels": "2", "audioRate": "48000"}))
        ET.SubElement(a, "media-rep", kind="original-media", src=path.resolve().as_uri())
    lib = ET.SubElement(doc, "library")
    event = ET.SubElement(lib, "event", name=name)
    proj = ET.SubElement(event, "project", name=name)
    seq = ET.SubElement(proj, "sequence", format="r_seq", duration=_t(tl.duration_f, fps), tcStart="0s", tcFormat="NDF",
                        audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(seq, "spine")
    first = None
    for c in base:
        in_f = tb.us_to_frame(c.src_in_us, fps)
        src_frames = round(c.dur_f * c.speed)
        clip = ET.SubElement(spine, "asset-clip", ref=f"a_{c.asset}", name=c.src.item, offset=_t(c.at_f, fps),
                             start=_t(in_f, fps), duration=_t(c.dur_f, fps), tcFormat="NDF")
        if c.speed != 1.0:
            tm = ET.SubElement(clip, "timeMap")
            ET.SubElement(tm, "timept", time="0s", value=_t(in_f, fps), interp="linear")
            ET.SubElement(tm, "timept", time=_t(c.dur_f, fps), value=_t(in_f + src_frames, fps), interp="linear")
        if first is None:
            first = (clip, in_f)
    if first:  # connected clips hang off the first spine clip, in its local time
        parent, in_f = first
        ET.SubElement(parent, "asset-clip", ref="a_overlay", name="overlay (captions, titles)", lane="1", offset=_t(in_f, fps),
                      start="0s", duration=_t(tl.duration_f, fps))
        for lane, s in zip((-1, -2, -3), STEMS):
            ET.SubElement(parent, "asset-clip", ref=f"a_{s}", name=f"{s} stem (finished)", lane=str(lane), offset=_t(in_f, fps),
                          start="0s", duration=_t(tl.duration_f, fps), enabled="0")
    ET.indent(doc)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + ET.tostring(doc, encoding="unicode") + "\n"


# ------------------------------------------------------------------ OTIO


def otio_timeline(tl: Timeline, root: Path, pkg: Path, name: str):
    import opentimelineio as otio

    fps = tb.parse_rate(tl.fps)
    rate = float(fps)
    rt = lambda f: otio.opentime.RationalTime(f, rate)  # noqa: E731
    t = otio.schema.Timeline(name=name, global_start_time=rt(0))
    v1 = otio.schema.Track(name="V1 cut", kind=otio.schema.TrackKind.Video)
    a1 = otio.schema.Track(name="A1 production audio", kind=otio.schema.TrackKind.Audio)
    for c in sorted((c for c in tl.video if c.id.startswith("v_")), key=lambda c: c.at_f):
        ref = otio.schema.ExternalReference(target_url=(root / tl.assets[c.asset].uri).resolve().as_uri())
        sr = otio.opentime.TimeRange(rt(tb.us_to_frame(c.src_in_us, fps)), rt(round(c.dur_f * c.speed)))
        for track in (v1, a1):
            clip = otio.schema.Clip(name=c.src.item, media_reference=ref.clone() if track is a1 else ref, source_range=sr)
            if c.speed != 1.0:
                clip.effects.append(otio.schema.LinearTimeWarp(time_scalar=c.speed))
            track.append(clip)
    v2 = otio.schema.Track(name="V2 overlay (alpha)", kind=otio.schema.TrackKind.Video)
    v2.append(otio.schema.Clip(name="overlay", media_reference=otio.schema.ExternalReference(target_url=(pkg / "overlay.mov").resolve().as_uri()),
                               source_range=otio.opentime.TimeRange(rt(0), rt(tl.duration_f))))
    t.tracks.extend([v1, v2, a1])
    for s in STEMS:
        tr = otio.schema.Track(name=f"{s} stem (finished)", kind=otio.schema.TrackKind.Audio)
        tr.enabled = False  # reference only: production audio on A1 stays live
        tr.append(otio.schema.Clip(name=s, media_reference=otio.schema.ExternalReference(target_url=(pkg / "stems" / f"{s}.wav").resolve().as_uri()),
                                   source_range=otio.opentime.TimeRange(rt(0), rt(tl.duration_f))))
        t.tracks.append(tr)
    return t


# ------------------------------------------------------------------ edit list + README


def edit_list(tl: Timeline, story: StoryPlan, finish: FinishPlan, words) -> str:
    fps = tb.parse_rate(tl.fps)
    by = words.by_index()
    tc = lambda f: _ts(f, fps, ".")[3:]  # noqa: E731  mm:ss.mmm
    clips: dict[str, list] = {}
    for c in sorted((c for c in tl.video if c.id.startswith("v_")), key=lambda c: c.at_f):
        clips.setdefault(c.src.item, []).append(c)
    lines = [f"# Edit list — {story.summary}", "", f"Genre `{story.genre}` · {len(story.items)} items · "
             f"{float(Fraction(tl.duration_f) / fps):.2f} s @ {tl.fps}", "", "## Story", "",
             "| out | item | beat | source | text | reason |", "|---|---|---|---|---|---|"]
    for it in story.items:
        shots = clips[it.id]
        c = shots[0]
        text = " ".join(by[i].text for i in range(it.word_start, it.word_end + 1))
        src = (f"{c.asset} {c.src_in_us / 1e6:.2f}–{shots[-1].src_out_us / 1e6:.2f} s" + (f" @ {c.speed}×" if c.speed != 1 else "")
               + (f" ({len(shots) - 1} pause cut{'s' if len(shots) > 2 else ''})" if len(shots) > 1 else ""))
        lines.append(f"| {tc(c.at_f)} | {it.id} | {it.beat} | {src} | {text} | {it.reason} |")
    hook = next((h for h in story.hook_options if h.id == story.hook), None)
    lines += ["", f"**Hook:** {hook.reason if hook else '—'}", "", "## Finish", ""]
    if finish.hook_title.text:
        lines.append(f"- **Hook title** “{finish.hook_title.text}” — {finish.hook_title.reason}")
    lines.append(f"- **Captions** `{finish.captions.family}` ({tl.captions.timing if tl.captions else '—'} timing) — {finish.captions.reason}")
    lines.append(f"- **Look** `{finish.grade.look}` at {finish.grade.strength} — {finish.grade.reason}")
    lines += [f"- **Punch-in** {p.id} on {p.item} at word {p.at_word} → {p.scale}× — {p.reason}" for p in finish.punch_ins]
    lines += [f"- **Transition** {t.type.value} after {t.after_item} ({t.frames} f) — {t.reason}" for t in finish.transitions]
    lines += [f"- **SFX** {x.sfx} ({x.anchor.value} {x.item}) — {x.reason}" for x in finish.sfx]
    lines.append(f"- **Music** {finish.music.track} — {finish.music.reason}")
    lines += [f"- **Speed** {x.item} {x.rate}× — {x.reason}" for x in finish.speeds]
    return "\n".join(lines) + "\n"


def credits_text(lines: list[str]) -> str:
    """CREDITS.txt: paste into the post caption — the licences of these tracks require it."""
    return "Credits (paste into the post caption / description):\n\n" + "\n\n".join(lines) + "\n"


def readme(tl: Timeline, idx, lufs_offset_db: float | None, verdict: str | None, credits: list[str] | None = None) -> str:
    used = {a.asset for a in tl.audio if a.role in ("sfx", "music")} | {c.asset for c in tl.video if c.id.startswith("br_")}
    by_file = {m.get("file"): k for k, m in idx.broll.items()}
    used |= {by_file[p.uri] for p in tl.pips if p.uri in by_file}
    lic = []
    for aid in sorted(used):
        meta = idx.sfx.get(aid) or idx.music.get(aid) or idx.broll.get(aid) or {}
        credit = f" — credit {meta['credit']}" if meta.get("credit") else ""
        credit += " — attribution required (CREDITS.txt)" if meta.get("attribution") else ""
        credit += f" — {meta['restrictions']}" if meta.get("restrictions") else ""
        url = f" <{meta['license_url']}>" if meta.get("license_url") else ""
        lic.append(f"- `{aid}` ({meta.get('name') or meta.get('title') or ''}): {meta.get('source', '?')} — {meta.get('license', '?')}{url}{credit}")
    credits_row = "| CREDITS.txt | **attribution the music licence requires — paste it into the post caption** |\n" if credits else ""
    gain = f"{lufs_offset_db:+.1f} dB" if lufs_offset_db is not None else "see qa/verdict.md"
    return f"""# Reel package

Verdict: **{verdict or 'n/a'}** (see qa/verdict.md in the project).

| file | what |
|---|---|
| reel.mp4 | deliverable (H.264, AAC, −14 LUFS) |
| overlay.mov | captions, hook title, flashes — ProRes 4444 **with alpha**; put it on the top video track |
| stems/dialogue.wav, music.wav, sfx.wav | finished buses (voice chain + room tone, ducked music, SFX) **before** delivery loudness; the deliverable applies {gain} on the sum |
| captions.srt / .vtt | caption pages (platform captions or NLE subtitle track) |
| timeline.fcpxml | Final Cut Pro: cut on the mezzanines (production audio), overlay on lane 1, stems on lanes −1…−3 (disabled) |
| timeline.otio | OpenTimelineIO for DaVinci Resolve / Avid / Premiere (OTIO plugin) |
| edit_list.md | every cut and finishing decision with the Editor's reason |
{credits_row}
**What is baked where.** The cut, speed changes and timing are in the timelines. Punch-ins, transitions, colour (per-clip correction + look) and the audio finishing are baked into `reel.mp4` and the stems, **not** rebuilt as NLE effects. The mezzanine clips are the ungraded, unzoomed source at the project frame rate. Re-grade or re-zoom there if needed.

**Media paths** point into the project folder (absolute `file://` URLs). Keep the project where it is, or relink.

## Licences of library assets used
{chr(10).join(lic) or '- none'}
"""


def build(ws, tl: Timeline, story: StoryPlan, finish: FinishPlan, words, idx, *, lufs_in: float | None = None, verdict: str | None = None) -> dict:
    import opentimelineio as otio

    from reel import mix

    pkg = ws.path("export", "package")
    pkg.mkdir(parents=True, exist_ok=True)
    _link(ws.path("render", "final.mp4"), pkg / "reel.mp4")
    _link(ws.path("render", "overlay.mov"), pkg / "overlay.mov")
    for s in STEMS:
        src = ws.path("render", "stems", f"{s}.wav")
        if src.exists():
            _link(src, pkg / "stems" / f"{s}.wav")
    name = ws.root.name
    atomic_write_bytes(pkg / "captions.srt", srt(tl).encode())
    atomic_write_bytes(pkg / "captions.vtt", vtt(tl).encode())
    atomic_write_bytes(pkg / "timeline.fcpxml", fcpxml(tl, ws.root, pkg, name).encode())
    otio.adapters.write_to_file(otio_timeline(tl, ws.root, pkg, name), str(pkg / "timeline.otio"))
    atomic_write_bytes(pkg / "edit_list.md", edit_list(tl, story, finish, words).encode())
    offset = (mix.TARGET_I - lufs_in) if lufs_in is not None and lufs_in > mix.SILENT_LUFS else None
    credits = library.credit_lines(tl, idx)
    if credits:
        atomic_write_bytes(pkg / "CREDITS.txt", credits_text(credits).encode())
    elif (pkg / "CREDITS.txt").exists():
        (pkg / "CREDITS.txt").unlink()  # a revision dropped the credited track
    atomic_write_bytes(pkg / "README.md", readme(tl, idx, offset, verdict, credits).encode())
    return {"files": sorted(str(p.relative_to(pkg)) for p in pkg.rglob("*") if p.is_file())}
