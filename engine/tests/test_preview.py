"""Hook preview in two looks (reel.preview, roadmap G1.6)."""

from __future__ import annotations

import json

import pytest

from reel import assets, preview
from reel.brief import Brand
from reel.schemas.plan import FinishPlan, HookTitle
from reel.workspace import Workspace

from test_plan_compile import CLIPS, FPS, IDX, WORDS, _finish, _story


def test_b_is_another_style_and_a_contrasting_look_unless_the_brand_locks_them():
    fams = assets.load().caption_families
    fin, story = _finish(), _story()  # bold_pop, look "clean", genre talking head
    fam, look = preview.alternative(fin, story, fams)
    assert fam and fam != "bold_pop" and look == "warm"
    assert preview.alternative(fin, story, fams, Brand(client="x", caption_family="bold_pop"))[0] is None
    assert preview.alternative(fin, story, fams, Brand(client="x", look="clean"))[1] is None
    assert preview.alternative(fin, story, fams, Brand(client="x", caption_family="bold_pop", look="clean")) == (None, None)
    b = preview.variant(fin, fam, look)
    assert b.captions.family == fam and b.captions.tokens == [] and b.grade.look == "warm" and b.punch_ins == fin.punch_ins


def test_trim_keeps_the_opening_as_a_renderable_timeline():
    from reel.compile import compile_timeline

    tl = compile_timeline(_story(), _finish(hook_title=HookTitle(text="One trick", style="card", reason="r")), WORDS, CLIPS, FPS, IDX)
    n = preview.hook_end_f(tl, _story()) + 15
    short = preview.trim(tl, n)
    base = sorted((c for c in short.video if c.id.startswith("v_")), key=lambda c: c.at_f)
    assert short.duration_f == n and sum(c.dur_f for c in base) == n  # back to back, exactly n frames
    assert all(e.end_f <= n for e in short.titles + short.graphics) and all(a.at_f + a.dur_f <= n for a in short.audio)
    assert all(p.end_f <= n for p in short.captions.pages)


def test_choose_rewrites_the_plan_for_b_and_records_the_pick(tmp_path):
    ws = Workspace.create(tmp_path / "p")
    ws.path("plan").mkdir(parents=True, exist_ok=True)
    ws.path("plan", "finish.json").write_text(_finish().model_dump_json())
    pv = ws.path("export", "preview")
    pv.mkdir(parents=True)
    (pv / "preview.json").write_text(json.dumps({"frames": 90, "options": {
        "A": {"caption_family": "bold_pop", "look": "clean", "plan": {}},
        "B": {"caption_family": "clean_phrase", "look": "warm", "plan": {"caption_family": "clean_phrase", "look": "warm"}}}, "chosen": None}))
    with pytest.raises(ValueError):
        preview.choose(ws, "C")
    assert preview.choose(ws, "B")["chosen"] == "B"
    fin = FinishPlan.model_validate_json(ws.path("plan", "finish.json").read_text())
    assert fin.captions.family == "clean_phrase" and fin.grade.look == "warm"
