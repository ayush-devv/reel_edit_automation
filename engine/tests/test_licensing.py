import pytest

from reel import library, package
from reel.assets import Indexes
from reel.compile import compile_timeline

from test_plan_compile import CLIPS, FPS, IDX, WORDS, _finish, _story


def _idx(music_meta: dict) -> Indexes:
    idx = Indexes(sfx=dict(IDX.sfx), music=dict(IDX.music), broll=dict(IDX.broll), caption_families=IDX.caption_families)
    idx.music["bed_cc"] = {"id": "bed_cc", "file": "assets/music/bed_cc.mp3", "duration_ms": 60_000, **music_meta}
    idx.sfx["whoosh_01"] = {**idx.sfx["whoosh_01"], "license": "owned"}
    return idx


def test_credits_survive_the_library_going_missing():
    idx = _idx({"license": "CC-BY-4.0", "attribution": "Track by Someone, CC BY 4.0"})
    fin = _finish(music=_finish().music.model_copy(update={"track": "bed_cc"}))
    tl = compile_timeline(_story(), fin, WORDS, CLIPS, FPS, idx)
    assert tl.assets["bed_cc"].attribution == "Track by Someone, CC BY 4.0"  # snapshotted at compile time
    empty = Indexes(sfx={}, music={}, broll={}, caption_families=IDX.caption_families)
    assert library.credit_lines(tl, empty) == ["Track by Someone, CC BY 4.0"]  # library gone: credit kept
    assert library.unknown_licences(tl, empty) == []


def test_unknown_licence_blocks_packaging_instead_of_dropping_credits():
    idx = _idx({})  # no licence recorded anywhere
    fin = _finish(music=_finish().music.model_copy(update={"track": "bed_cc"}))
    tl = compile_timeline(_story(), fin, WORDS, CLIPS, FPS, idx)
    assert library.unknown_licences(tl, idx) == ["bed_cc"]


def test_share_alike_and_non_commercial_are_never_indexed(tmp_path):
    for bad in ("CC-BY-SA-4.0", "CC BY-NC 4.0", "cc-by-nd", "Creative Commons ShareAlike"):
        with pytest.raises(ValueError):
            library.check_licence(bad)
    library.check_licence("CC-BY-4.0")
    library.check_licence("CC0-1.0")
    with pytest.raises(ValueError):
        library.index_sfx(tmp_path, source="x", license_="CC-BY-NC-4.0")


def test_cc_by_credit_says_the_music_was_edited():
    assert "edited and synchronised" in package.credits_text(["Track by Someone, CC BY 4.0"])
