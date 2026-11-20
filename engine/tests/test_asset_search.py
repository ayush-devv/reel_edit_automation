"""G2.3: b-roll ranked by meaning (text only), near-duplicates folded, sibling use penalised, the broll_repeat gate."""

from reel import asset_search, qa
from reel.schemas.plan import Broll

POOL = {
    "b_coins": {"description": "hand dropping coins into a glass jar on a wooden table", "shot": "close", "mood": "calm"},
    "b_coins2": {"description": "hand dropping coins into a glass jar on a wooden table, warm light", "shot": "close", "mood": "calm"},
    "b_gym": {"description": "man lifting weights in a busy gym", "shot": "wide", "mood": "energetic"},
    "b_laptop": {"description": "woman typing on a laptop at a cafe, budgeting spreadsheet on screen", "shot": "medium"},
}
LINES = [("k01", "Start saving coins in a jar every single day"), ("k02", "I track my budget in a spreadsheet on my laptop"),
         ("k03", "and then I go to the gym")]


def test_each_line_gets_the_clips_that_match_it():
    rows = {r["id"]: r for r in asset_search.rank_broll(POOL, LINES, per_item=1)}
    assert "k01" in rows["b_coins"]["for"] or "k01" in rows["b_coins2"]["for"]
    assert rows["b_laptop"]["for"] == ["k02"] and rows["b_gym"]["for"] == ["k03"]


def test_near_duplicates_are_folded_into_the_better_one():
    rows = asset_search.rank_broll(POOL, LINES)
    twins = [r for r in rows if r["same_as"]]
    assert len(twins) == 1 and {twins[0]["id"], twins[0]["same_as"]} == {"b_coins", "b_coins2"}
    assert ("b_coins", "b_coins2", ) == asset_search.near_duplicates(POOL)[0][:2]


def test_a_clip_a_sibling_reel_used_is_pushed_down():
    fresh = asset_search.rank_broll(POOL, [("k02", "budget spreadsheet laptop")], per_item=1)
    assert fresh[0]["id"] == "b_laptop"
    penalised = asset_search.rank_broll(POOL, [("k02", "budget spreadsheet laptop")], batch_used={"b_laptop"}, per_item=4)
    row = next(r for r in penalised if r["id"] == "b_laptop")
    assert row["batch_used"] and row["score"] == 0.5


def test_matched_clips_come_first_and_the_pool_is_never_hidden():
    pool = {f"b{n:02d}": {"description": f"unrelated scenery number {n}"} for n in range(20)} | {"b_jar": {"description": "coins in a jar"}}
    rows = asset_search.rank_broll(pool, [("k01", "coins jar saving")], per_item=3)
    assert rows[0]["id"] == "b_jar" and rows[0]["for"] == ["k01"] and len(rows) == 21
    small = asset_search.rank_broll(POOL, [("k01", "coins")])
    assert len(small) == len(POOL)


def test_devanagari_lines_still_get_a_full_menu():
    pool = {f"b{n:02d}": {"description": f"person walking in a park, shot {n}"} for n in range(20)}
    rows = asset_search.rank_broll(pool, [("k01", "हर महीने अपनी सैलरी का दस प्रतिशत बचाइए"), ("k02", "पैसे बचाना आसान है")])
    assert len(rows) == 20 and not any(r["for"] for r in rows)  # nothing matches by words, but nothing is hidden
    big = {f"b{n:03d}": {"description": f"clip {n}"} for n in range(40)}
    assert len(asset_search.rank_broll(big, [("k01", "कुछ नहीं")])) == asset_search.MAX_MENU  # only the cap applies


def test_optional_embedder_adds_a_cosine_term():
    calls = []

    def embed(texts):
        calls.append(len(texts))
        return [[1.0, 0.0] if ("gym" in t or "weights" in t) else [0.0, 1.0] for t in texts]

    rows = asset_search.rank_broll(POOL, [("k09", "kasrat karna zaroori hai gym")], embed=embed, per_item=1)
    assert rows[0]["id"] == "b_gym" and calls == [4, 1]


def test_tokens_drop_stopwords_and_fold_plurals():
    assert asset_search.tokens("The coins are in jars, aur yeh hai") == ["coin", "jar"]


def _b(bid, asset):
    return Broll(id=bid, asset=asset, item="k01", from_word=0, to_word=1, mode="full", reason="r")


class _Fin:
    def __init__(self, broll):
        self.broll = broll


def test_broll_repeat_gate():
    ok = qa.broll_repeat(_Fin([_b("r1", "b_coins"), _b("r2", "b_gym")]), POOL)
    twice = qa.broll_repeat(_Fin([_b("r1", "b_gym"), _b("r2", "b_gym")]), POOL)
    twins = qa.broll_repeat(_Fin([_b("r1", "b_coins"), _b("r2", "b_coins2")]), POOL)
    assert ok.ok and not twice.ok and "b_gym used 2×" in twice.detail
    assert not twins.ok and twins.measured["twins"] and qa.broll_repeat(None, POOL).ok
