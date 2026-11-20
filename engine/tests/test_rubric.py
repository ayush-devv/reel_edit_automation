"""3b.1: a rubric fixed from the brief before the edit; the Reviewer answers it one for one."""

from __future__ import annotations

from reel import rubric, verdict
from reel.brief import Brief
from reel.schemas.review import Review
from reel.validate import errors
from reel.workspace import Workspace


def _review(*answers, sendable=True):
    return Review.model_validate({"sendable": sendable, "summary": "s", "issues": [], "strengths": [],
                                  "rubric": [{"id": i, "met": m, "evidence": e} for i, m, e in answers]})


def test_criteria_come_from_the_brief_and_the_client():
    b = Brief(project="p", must_keep_lines=["save first"], cta="Follow for part 2", banned_claims=["guaranteed returns"], tone="warm",
              genre_hint="genre.testimonial", product_names=["DearMa"])
    items = rubric.build(b, {"recurring_settings": [{"kind": "music_track", "value": "none", "reels": 2}]})
    ids = [c["id"] for c in items]
    assert ids == ["hook_2s", "must_keep_1", "cta", "banned_1", "length", "tone", "genre", "product_1", "client_1"]
    assert [c["id"] for c in items if c["required"]] == ["must_keep_1", "cta", "banned_1"]
    assert rubric.build(None, None) == [items[0]]  # no brief: only the hook criterion


def test_the_reviewer_may_not_change_the_list():
    items = rubric.build(Brief(project="p", cta="Follow"), None)
    ok = _review(("hook_2s", True, "0:01 a claim"), ("cta", True, "0:31"), ("length", True, ""))
    assert rubric.check(ok, items) == []
    changed = _review(("hook_2s", True, ""), ("vibes", True, ""))
    assert [i.code for i in errors(rubric.check(changed, items))] == ["rubric_changed"]
    unanswered = rubric.check(_review(), items)
    assert [i.code for i in unanswered] == ["rubric_unanswered"] and not errors(unanswered)


def test_unmet_required_criteria_hold_the_reel_and_others_warn():
    items = rubric.build(Brief(project="p", cta="Follow"), None)
    r = _review(("hook_2s", False, "opens on a greeting"), ("cta", False, "no CTA heard"), ("length", True, ""))
    v = verdict.decide_verdict([], r, items)
    assert v["status"] == "hold" and any("rubric cta" in x for x in v["reasons"])
    assert any("rubric hook_2s" in x for x in v["warnings"])
    fine = verdict.decide_verdict([], _review(("hook_2s", True, ""), ("cta", True, ""), ("length", True, "")), items)
    assert fine["status"] == "sendable"
    assert "didn't score" in verdict.decide_verdict([], _review(), items)["warnings"][0]


def test_rubric_file_and_review_input(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    items = rubric.write(ws, Brief(project="p", must_keep_lines=["x"]), None)
    assert rubric.load(ws) == items
    md = "\n".join(rubric.md(items))
    assert "fixed before the edit existed" in md and "`must_keep_1` **(required)**" in md
