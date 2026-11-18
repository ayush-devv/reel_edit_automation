"""Footage tables Claude reads in the story pass (ADR-0016, ADR-0030 context rules).

Compact and high-signal: a tagged script, per-segment facts, takes, a word index for
on-demand lookup, a project summary, and contact sheets.
"""

from __future__ import annotations

import statistics

from reel.schemas.perception import SegmentTable, WordTable

PAUSE_MARK_US = 300_000  # pauses inside a segment (segments already split at ≥ 0.5 s)
GAP_MARK_US = 700_000  # gaps between consecutive segments of a clip, shown on their own line


def _fmt(us: int) -> str:
    s = us / 1e6
    return f"{int(s // 60)}:{s % 60:04.1f}"


def word_markup(w) -> str:
    if w.filler:
        return "{" + w.text + "}"
    t = w.text
    if w.vocab_suspect:
        t = f"⚠{t}" + (f"→{w.vocab_suggestion}" if w.vocab_suggestion else "")
    elif w.low_conf:
        t = f"{t}(?)"
    if w.original_text:
        t = f"{t}[asr:{w.original_text}]"
    return t


def segment_rows(words: WordTable, segments: SegmentTable, prosody: list[dict], takes: dict,
                 faces: dict, energy: dict, scenes: dict) -> list[dict]:
    by = words.by_index()
    pstats = {p["seg_id"]: p for p in prosody}
    rows = []
    for s in segments.segments:
        ws = [by[i] for i in range(s.word_start, s.word_end + 1)]
        fs = [x for x in (faces.get(s.clip) or {}).get("samples", []) if s.start_us <= x["t_us"] <= s.end_us]
        with_face = [x["faces"][0] for x in fs if x["faces"]]
        mot = (energy.get(s.clip) or {}).get("motion") or {}
        mfps = mot.get("fps") or 10
        mvals = (mot.get("values") or [])[int(s.start_us / 1e6 * mfps): int(s.end_us / 1e6 * mfps) + 1]
        cuts = (scenes.get(s.clip) or {}).get("cuts_us") or []
        st = pstats.get(s.seg_id, {})
        rows.append({
            "seg_id": s.seg_id, "clip": s.clip,
            "t0": round(s.start_us / 1e6, 2), "t1": round(s.end_us / 1e6, 2),
            "words": [s.word_start, s.word_end],
            "text": " ".join(w.text for w in ws if not w.filler),
            "wps": st.get("words_per_s"), "pause_ratio": st.get("pause_ratio"),
            "loudness_db": st.get("loudness_db"), "asr_conf": st.get("asr_conf"),
            "fillers": st.get("fillers"), "proof_words": st.get("proof_words", []),
            "face": round(len(with_face) / len(fs), 2) if fs else None,
            "face_box": ({k: round(statistics.median(f[k] for f in with_face), 3) for k in ("x", "y", "w", "h")} if with_face else None),
            "motion": round(statistics.fmean(mvals), 1) if mvals else None,
            "scene_cut_inside": any(s.start_us < c < s.end_us for c in cuts),
            "take": takes.get("by_segment", {}).get(s.seg_id),
        })
    return rows


def script_md(words: WordTable, segments: SegmentTable, rows: list[dict]) -> str:
    by = words.by_index()
    row_by = {r["seg_id"]: r for r in rows}
    lines = ["# Script", "",
             "Markers: {um} filler · word(?) low confidence · ⚠word→Suggestion unconfirmed name (proof list) · "
             "word[asr:orig] auto-corrected · (… 1.2 s) pause. Reference segments by [sNNN], words by index via words.tsv.", ""]
    clip, prev_seg_end = None, None
    for s in segments.segments:
        if s.clip != clip:
            clip, prev_seg_end = s.clip, None
            lines += ["", f"## Clip {clip}", ""]
        if prev_seg_end is not None and s.start_us - prev_seg_end >= GAP_MARK_US:
            lines.append(f"(… {(s.start_us - prev_seg_end) / 1e6:.1f} s)")
        prev_seg_end = s.end_us
        r = row_by[s.seg_id]
        tag = f"[{s.seg_id} {_fmt(s.start_us)}–{_fmt(s.end_us)}"
        if r["take"]:
            t = r["take"]
            tag += f" · take {t['take']}/{t['of']} of {t['group']} (suggested #{t['suggested_rank']})"
        if r["wps"] is not None:
            tag += f" · {r['wps']} w/s"
        tag += "]"
        parts, prev_end = [], None
        for i in range(s.word_start, s.word_end + 1):
            w = by[i]
            if prev_end is not None and w.start_us - prev_end >= PAUSE_MARK_US:
                parts.append(f"(… {(w.start_us - prev_end) / 1e6:.1f} s)")
            parts.append(word_markup(w))
            prev_end = w.end_us
        lines.append(f"{tag} {' '.join(parts)}")
    return "\n".join(lines) + "\n"


def words_tsv(words: WordTable, edges: dict[int, tuple[int, int]]) -> str:
    out = ["i\tclip\tstart_ms\tend_ms\theard_start_ms\theard_end_ms\ttext\tflags"]
    for w in words.words:
        hs, he = edges.get(w.i, (w.start_us, w.end_us))
        flags = ",".join(f for f, on in (("filler", w.filler), ("cand_filler", w.candidate_filler), ("low_conf", w.low_conf),
                                         ("suspect", w.suspect), ("proof", w.vocab_suspect)) if on)
        out.append(f"{w.i}\t{w.clip}\t{w.start_us // 1000}\t{w.end_us // 1000}\t{hs // 1000}\t{he // 1000}\t{w.text}\t{flags}")
    return "\n".join(out) + "\n"


def meaningful_ocr(texts: list[str], min_letters: int = 3) -> list[str]:
    """Drop timecodes/numbers/noise and near-duplicates ('DearMa MoneyTips' ≈ 'DearMa Money Tips')."""
    seen, out = set(), []
    for t in texts:
        letters = sum(ch.isalpha() for ch in t)
        key = "".join(ch for ch in t.casefold() if ch.isalnum())
        if letters >= min_letters and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def summary_md(manifest: dict, words: WordTable, rows: list[dict], takes: dict, palette: dict, ocr: dict, brief) -> str:
    lines = ["# Footage summary", ""]
    lines.append(f"Project fps {manifest['project_fps']} · {len(manifest['clips'])} clip(s) · language {words.language} · "
                 f"{len(words.words)} words · {len(rows)} segments · {len(takes.get('groups', []))} repeated-line groups")
    for c in manifest["clips"]:
        v = c["probe"]["video"]
        pal = palette.get(c["id"]) or {}
        cols = ", ".join(x["hex"] for x in pal.get("colors", [])[:5])
        lines.append(f"- {c['id']}: {c['probe']['duration_s']:.1f} s, {v['display_width']}x{v['display_height']}"
                     f"{', HDR ' + v['hdr'] if v.get('hdr') else ''}{', VFR' if v.get('is_vfr') else ''}"
                     f" · palette {cols or 'n/a'} · caption-zone luma {pal.get('caption_zone_luma', 'n/a')} · warmth {pal.get('warmth', 'n/a')}")
    proof = [(w.i, w.text, w.vocab_suggestion) for w in words.words if w.vocab_suspect]
    if proof:
        lines += ["", "Proof list (unconfirmed names — never burn in unverified): " + "; ".join(f"{i}:{t}→{s or '?'}" for i, t, s in proof)]
    texts = meaningful_ocr([it["text"] for v in ocr.values() for it in (v.get("items") or [])])
    if texts:
        lines += ["", "On-screen text seen: " + " | ".join(texts[:30])]
    if brief:
        lines += ["", "## Brief"]
        for k in ("goal", "audience", "genre_hint", "platform", "target_length_s", "cta", "tone", "language", "caption_script"):
            val = getattr(brief, k)
            if val:
                lines.append(f"- {k}: {val}")
        for k in ("must_keep_lines", "product_names", "banned_claims"):
            val = getattr(brief, k)
            if val:
                lines.append(f"- {k}: " + " | ".join(val))
    return "\n".join(lines) + "\n"
