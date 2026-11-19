"""Lottie graphics: safety checks on files, the owned starter pack, validation, compile → props, and a real render."""

from __future__ import annotations

import json

import numpy as np
import pytest

from reel import config, lottie, lottie_pack, overlay, tools
from reel.compile import compile_timeline
from reel.schemas.timeline import GraphicEvent, Timeline
from reel.validate import validate_finish

from test_overlay import READY, _g
from test_plan_compile import CLIPS, FPS, IDX, WORDS, _finish, _story


def _anim(**extra):
    return {"v": "5.7.4", "fr": 30, "ip": 0, "op": 30, "w": 100, "h": 100, "layers": [], **extra}


def test_unsafe_files_are_refused():
    assert lottie.problems(_anim()) == []
    expr = _anim(layers=[{"ty": 4, "ks": {"o": {"a": 0, "k": 100, "x": "var a = fetch('x')"}}}])
    assert any("expressions" in p for p in lottie.problems(expr))
    web = _anim(assets=[{"id": "img", "u": "https://evil.example/", "p": "a.png"}])
    assert any("internet" in p for p in lottie.problems(web))
    text = _anim(layers=[{"ty": 5, "t": {"d": {}}}])
    assert any("text layers" in p for p in lottie.problems(text))
    assert any("length" in p for p in lottie.problems(_anim(op=30 * 20)))
    assert lottie.problems({"layers": []}) and lottie.problems("nope")


def test_index_folder_refuses_bad_files_and_bad_licences(tmp_path):
    (tmp_path / "ok_check.json").write_text(json.dumps(_anim()))
    (tmp_path / "evil.json").write_text(json.dumps(_anim(layers=[{"ks": {"x": "eval(1)"}}])))
    (tmp_path / "huge.json").write_text(json.dumps(_anim(pad="x" * (lottie.MAX_BYTES + 10))))
    (tmp_path / "broken.json").write_text("{")
    entries = lottie.index_folder(tmp_path, source="LottieFiles", license_="Lottie Simple License", rel_to=tmp_path)
    assert [e["name"] for e in entries] == ["ok_check"] and entries[0]["tags"] == ["ok", "check"]
    assert {f for f, _ in lottie.SKIPPED} == {"evil.json", "huge.json", "broken.json"}
    with pytest.raises(ValueError):
        lottie.index_folder(tmp_path, source="x", license_="CC BY-NC 4.0", rel_to=tmp_path)


def test_starter_pack_is_safe_and_recolours_to_the_accent(tmp_path):
    meta = lottie_pack.build_all(tmp_path)
    entries = lottie.index_folder(tmp_path, source="reel procedural", license_="owned", rel_to=tmp_path, meta=meta)
    assert len(entries) == len(lottie_pack.PACK) and not lottie.SKIPPED and all(e["recolour"] for e in entries)
    e = next(x for x in entries if x["name"] == "check_draw")
    data = lottie.load_for_render({**e, "file": str(tmp_path / e["file"])}, "#FF0066")
    colours = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("ty") in ("st", "fl"):
                colours.append(n["c"]["k"][:3])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(data["layers"])
    assert colours and all(np.allclose(c, [1.0, 0.0, 0.4], atol=0.01) for c in colours)


def test_validation_and_compile():
    lid = next(iter(IDX.lottie), None)
    if lid is None:
        pytest.skip("no Lottie library in assets/ (run `reel assets fetch`)")
    ok = _finish(graphics=[_g("l1", "lottie", 7, 8, asset=lid, style="small", position="upper_right")])
    assert not [i for i in validate_finish(ok, _story(), WORDS, IDX) if i.severity == "error"]
    bad = _finish(graphics=[_g("l1", "lottie", 7, 8, asset="lt_missing"), _g("l2", "lottie", 7, 8),
                            *[_g(f"m{n}", "lottie", 7, 8, asset=lid, position="center") for n in range(3)]])
    codes = {i.code for i in validate_finish(bad, _story(), WORDS, IDX)}
    assert {"unknown_lottie", "graphic_needs_asset", "too_many_lottie"} <= codes
    tl = compile_timeline(_story(), ok, WORDS, CLIPS, FPS, IDX)
    (g,) = tl.graphics
    assert g.kind == "lottie" and g.uri == lid and g.end_f - g.start_f >= 36  # ≥ 1.2 s at 30 fps


@pytest.mark.integration
@pytest.mark.skipif(not READY, reason="needs pinned ffmpeg + renderer")
def test_every_pack_animation_renders_recoloured(tmp_path):
    names = list(lottie_pack.PACK)
    by_name = {a["name"]: lid for lid, a in IDX.lottie.items() if a.get("source") == "reel procedural"}
    if set(names) - set(by_name):
        pytest.skip("starter pack not installed (run `reel assets fetch`)")
    span = 30
    events = [GraphicEvent(id=f"l{k}", kind="lottie", start_f=k * span, end_f=(k + 1) * span, accent="#FF0066", style="large", position="center",
                           uri=by_name[n]) for k, n in enumerate(names)]
    events.append(GraphicEvent(id="ghost", kind="lottie", start_f=0, end_f=10, uri="lt_not_in_library"))
    tl = Timeline(fps="30/1", width=1080, height=1920, duration_f=span * len(names), assets={}, video=[], audio=[], graphics=events)
    props = overlay.build_props(tl, tmp_path, None)
    assert [g["id"] for g in props["graphics"]] == [e.id for e in events[:-1]]  # an unknown id is dropped, never rendered blank
    ov = tmp_path / "overlay.mov"
    overlay.render_overlay(props, ov)
    sel = "+".join(f"eq(n\\,{k * span + 12})" for k in range(len(names)))  # mid-animation for every one (rings fade out by their end)
    sheet = tmp_path / "sheet.png"
    tools.ffmpeg(["-y", "-i", str(ov), "-vf", f"select='{sel}',scale=108:192,tile={len(names)}x1", "-frames:v", "1", "-update", "1",
                  "-pix_fmt", "rgba", str(sheet)])
    raw = tools.run([str(config.ffmpeg_path()), "-v", "error", "-i", str(sheet), "-f", "rawvideo", "-pix_fmt", "rgba", "-"]).stdout
    px = np.frombuffer(raw, dtype=np.uint8).reshape(192, 108 * len(names), 4).astype(int)
    for k, n in enumerate(names):
        tile = px[:, k * 108:(k + 1) * 108]
        drawn = tile[..., 3] > 128
        assert drawn.mean() > 0.002, (n, drawn.mean())
        r, g, b = (tile[..., c][drawn].mean() for c in range(3))
        assert r > 150 and g < 90 and b > 50, (n, r, g, b)  # pink accent (#FF0066), not the pack's white
