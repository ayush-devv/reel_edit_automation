"""useAnimations pack, recolouring dark icons, the Editor's Lottie menu and `reel add-asset` (roadmap G1.8)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from reel import assets, library, licences, lottie


def _anim(colour):
    shape = {"ty": "gr", "it": [{"ty": "st", "c": {"a": 0, "k": [*colour, 1]}}, {"ty": "fl", "c": {"a": 0, "k": [0.5, 0.5, 0.5, 1]}}]}
    return {"v": "5.6", "fr": 30, "ip": 0, "op": 30, "w": 32, "h": 32, "layers": [{"ty": 4, "shapes": [shape]}]}


def _colours(data) -> list[list[float]]:
    out = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("ty") in ("st", "fl"):
                out.append([round(x, 3) for x in n["c"]["k"][:3]])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(data["layers"])
    return out


def test_dark_icons_recolour_to_the_accent_or_white(tmp_path):
    f = tmp_path / "icon.json"
    f.write_text(json.dumps(_anim([0, 0, 0])))
    meta = {"file": str(f), "recolour": True, "recolour_from": "#000000"}
    assert _colours(lottie.load_for_render(meta, "#FF0066")) == [[1.0, 0.0, 0.4], [0.5, 0.5, 0.5]]  # only the drawing colour
    assert _colours(lottie.load_for_render(meta, None))[0] == [1.0, 1.0, 1.0]  # never black on video
    white = tmp_path / "w.json"
    white.write_text(json.dumps(_anim([1, 1, 1])))
    assert _colours(lottie.load_for_render({"file": str(white), "recolour": True}, None))[0] == [1.0, 1.0, 1.0]


def test_vendored_pack_is_indexed_safe_licensed_and_hashed():
    raw = json.loads((assets.ASSETS_DIR / "lottie" / "index.json").read_text())["animations"]
    ua = [e for e in raw if e["source"] == "useAnimations"]
    assert len(ua) == 298  # 300 in the pack; error.json and twitter.json use expressions and were refused
    reg = licences.load_registry()
    for e in ua:
        f = assets.ASSETS_DIR / e["file"]
        assert e["licence_id"] == "mit" and len(e["sha256"]) == 64 and e["recolour_from"] == "#000000"
        assert lottie.problems(json.loads(f.read_text())) == []
    assert reg.notice(ua[0]) == "useanimations-LICENSE.txt"
    marks = {e["name"] for e in ua if e.get("trademark")}
    assert {"instagram", "youtube", "facebook", "linkedin"} <= marks and len(marks) == 21


def test_menu_offers_our_pack_plus_matching_icons_and_never_logos():
    lib = assets.load().lottie
    m = lottie.menu(lib, "Follow for more. Like and share this video, then check the link in the bell icon. Instagram and YouTube.")
    own = [i for i, a in lib.items() if a["source"] == "reel procedural"]
    assert set(own) <= set(m) and len(m) <= len(own) + 14
    names = {lib[i]["name"] for i in m}
    assert not any(lib[i].get("trademark") for i in m)
    assert {"notification", "like", "share"} & names or any("bell" in lib[i].get("tags", []) for i in m)
    assert lottie.menu(lib, "") == {i: lib[i] for i in own}  # nothing matches: only our pack


def _wav(path, seconds=0.3):
    import soundfile as sf

    y = np.zeros(int(48000 * seconds), dtype=np.float32)
    y[2000:2400] = 0.8
    sf.write(str(path), y, 48000)
    return path


def test_add_asset_needs_a_registered_unblocked_licence_and_attribution(tmp_path):
    root = tmp_path / "assets"
    (root / "sfx").mkdir(parents=True)
    src = _wav(tmp_path / "click_soft.wav")
    e = library.add_file(src, kind="sfx", licence_id="cc0-1.0", source="Freesound", source_url="https://freesound.org/s/1/", root=root)
    assert e["category"] == "click" and e["licence_id"] == "cc0-1.0" and e["source_url"].startswith("https://freesound")
    assert (root / e["file"]).is_file() and len(e["sha256"]) == 64 and e["downloaded_at"]
    saved = json.loads((root / "sfx" / "sfx_index.json").read_text())["sfx"]
    assert [x["id"] for x in saved] == [e["id"]]
    for kw, msg in ((dict(licence_id="nope"), "not in"), (dict(licence_id="sonniss-gdc-2.0"), "blocked"),
                    (dict(licence_id="cc-by-4.0"), "attribution")):
        with pytest.raises(ValueError, match=msg):
            library.add_file(src, kind="sfx", source="X", root=root, **kw)
    with pytest.raises(ValueError, match="category"):
        library.add_file(_wav(tmp_path / "mystery.wav"), kind="sfx", licence_id="cc0-1.0", source="X", root=root)


def test_add_asset_lottie_runs_the_safety_checks(tmp_path):
    root = tmp_path / "assets"
    (root / "lottie").mkdir(parents=True)
    good = tmp_path / "check.json"
    good.write_text(json.dumps(_anim([1, 1, 1])))
    e = library.add_file(good, kind="lottie", licence_id="mit", source="SomePack", root=root)
    assert e["licence_id"] == "mit" and (root / "lottie" / "index.json").exists()
    evil = tmp_path / "evil.json"
    evil.write_text(json.dumps({**_anim([1, 1, 1]), "layers": [{"ks": {"x": "eval(1)"}}]}))
    with pytest.raises(ValueError, match="expressions"):
        library.add_file(evil, kind="lottie", licence_id="mit", source="SomePack", root=root)
