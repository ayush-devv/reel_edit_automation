"""4.2: the verdict lists what it couldn't measure and what no gate looks at, from stored QA files, without touching the QA
stage's fingerprint (no project re-buys a Reviewer call)."""

from __future__ import annotations

import json
from pathlib import Path

from reel import coverage


def _qa(tmp_path: Path, gates: list[dict], review: bool = True) -> Path:
    (tmp_path / "qa").mkdir(parents=True)
    (tmp_path / "qa" / "gates.json").write_text(json.dumps(gates))
    if review:
        (tmp_path / "qa" / "review.json").write_text("{}")
    return tmp_path


def test_unmeasured_and_partial_checks_are_listed_never_passed(tmp_path):
    ws = _qa(tmp_path, [
        {"gate": "pace", "ok": False, "mode": "warn", "detail": "pace not measured (no reference)"},
        {"gate": "caption_over_face", "ok": True, "mode": "warn", "detail": "0 page(s) cover the face", "measured": {"skipped": ["0:03", "0:07"]}},
        {"gate": "dead_air", "ok": True, "mode": "block", "detail": "0 gap(s)"},
    ], review=False)
    rep = coverage.report(ws)
    assert [x["gate"] for x in rep["not_measured"]] == ["pace", "reviewer"]
    assert rep["partial"] == [{"gate": "caption_over_face", "skipped": 2, "why": "2 item(s) couldn't be checked"}]
    assert rep["never"] and rep["reviewer"] is False
    assert "3 check(s) couldn't run fully" in coverage.reply_tail(ws)
    assert any("couldn't check pace" in line for line in coverage.lines(rep))


def test_a_clean_render_has_nothing_unmeasured(tmp_path):
    ws = _qa(tmp_path, [{"gate": "dead_air", "ok": True, "mode": "block", "detail": "0 gap(s)"}])
    rep = coverage.report(ws)
    assert rep["not_measured"] == [] and rep["partial"] == [] and coverage.reply_tail(ws) == ""
    assert coverage.report(tmp_path / "nope") is None


def test_coverage_stays_out_of_the_qa_fingerprint():
    """The QA stage hashes verdict.py, qa.py and cuts.py: none of them may import coverage, or every project's next run
    would re-buy a Reviewer call."""
    import reel

    src = Path(reel.__file__).parent
    for name in ("verdict.py", "qa.py", "cuts.py"):
        assert "coverage" not in (src / name).read_text(), name


def test_the_studio_and_the_revise_reply_carry_it(tmp_path):
    from reel.studio import projects

    ws = _qa(tmp_path, [{"gate": "pace", "ok": False, "mode": "warn", "detail": "pace not measured"}])
    (ws / "qa" / "verdict.json").write_text(json.dumps({"status": "sendable", "reasons": [], "warnings": ["pace: not measured"]}))
    d = projects.verdict_detail(ws)
    assert d["coverage"]["not_measured"][0]["gate"] == "pace"
    assert "couldn't run fully" in projects.with_measured_verdict(ws, "Fixed the caption")
