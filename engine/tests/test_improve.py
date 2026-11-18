"""Build step 11b: acceptance statistics, knowledge overrides, and the improvement night (fake evaluator)."""

import pytest

from reel import improve, knowledge
from reel.evalh import acceptance


def _runs(scores: dict[str, list[float]], lang="en", fam=None):
    return {r: [{"primary": p, "families": fam or {"story": p / 100}, "vetoes": [], "language": lang} for p in ps] for r, ps in scores.items()}


def test_permutation_p_and_delta_min():
    assert acceptance.permutation_p([5, 6, 4, 5, 7, 5]) == pytest.approx(1 / 64)  # all positive: only the identity flip is as extreme
    assert acceptance.permutation_p([3, -3, 2, -2]) > 0.3
    base = _runs({"a": [60, 64], "b": [70, 66], "c": [50, 52]})
    assert acceptance.delta_min(base) >= 2.0


def test_acceptance_accepts_consistent_gain_and_rejects_noise_or_regression():
    base = _runs({r: [60, 61, 60] for r in "abcdef"})
    good = _runs({r: [66, 65, 66] for r in "abcdef"})
    d = acceptance.decide(base, good)
    assert d["accepted"], d["reasons"]
    noisy = _runs({"a": [70, 70, 70], "b": [55, 55, 55], "c": [66, 66, 66], "d": [57, 57, 57], "e": [62, 62, 62], "f": [59, 59, 59]})
    assert not acceptance.decide(base, noisy)["accepted"]
    one_crash = {**good, "a": [{"primary": None, "families": {}, "vetoes": ["crash"], "language": "en"}] * 3}
    assert any("new veto" in r for r in acceptance.decide(base, one_crash)["reasons"])
    hinglish_hurt = {**_runs({r: [70, 70, 70] for r in "abcd"}), **_runs({r: [55, 55, 55] for r in "ef"}, lang="hi")}
    base_l = {**_runs({r: [60, 61, 60] for r in "abcd"}), **_runs({r: [60, 61, 60] for r in "ef"}, lang="hi")}
    assert any("hinglish subset" in r for r in acceptance.decide(base_l, hinglish_hurt)["reasons"])
    cap_drop = _runs({r: [67, 67, 67] for r in "abcdef"}, fam={"story": 0.9, "captions": 0.5})
    base_c = _runs({r: [60, 61, 60] for r in "abcdef"}, fam={"story": 0.6, "captions": 0.6})
    assert any("captions" in r for r in acceptance.decide(base_c, cap_drop)["reasons"])


def test_overrides_edit_and_add_without_touching_the_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "LEARNED", tmp_path / "overrides.yaml")
    knowledge.nodes.cache_clear()
    nid = next(iter(knowledge.nodes()))
    ch = [improve.Change(id="c1", kind="edit", node_id=nid, fields=[improve.Field_(key="summary", value="Sharper guidance.")], evidence="e", expected_effect="x"),
          improve.Change(id="c2", kind="add", node_id="tech.hook.result_first_learned",
                         fields=[improve.Field_(key=k, value=v) for k, v in (("type", "technique"), ("name", "Result first"),
                                                                            ("summary", "Open on the result."), ("genres", "genre.talking_head"))],
                         evidence="e", expected_effect="x")]
    assert improve.check_changes(ch, {}) == []
    improve.write_overrides(improve.with_changes({}, ch))
    nodes = knowledge.nodes()
    assert nodes[nid]["summary"] == "Sharper guidance." and nodes[nid]["learned"]
    assert nodes["tech.hook.result_first_learned"]["genres"] == ["genre.talking_head"]
    bad = [improve.Change(id="c3", kind="edit", node_id="nope", fields=[improve.Field_(key="id", value="x")], evidence="e", expected_effect="x")]
    assert len(improve.check_changes(bad, {})) == 2
    knowledge.nodes.cache_clear()


def test_night_accepts_a_real_improvement_and_rejects_a_useless_one(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge, "LEARNED", tmp_path / "overrides.yaml")
    monkeypatch.setattr(improve, "LOG", tmp_path / "log.jsonl")
    knowledge.nodes.cache_clear()
    good_node, useless_node = list(knowledge.nodes())[:2]

    def evaluate(reels, runs, label):  # +6 points on every reel when the good edit is active, else noise-free 60
        ov = knowledge.load_overrides()
        bonus = 6 if good_node in (ov.get("edit") or {}) else 0
        return _runs({r: [60 + bonus] * runs for r in (reels or list("abcdef"))})

    proposals = iter([
        improve.Proposal(diagnosis="hooks late", changes=[
            improve.Change(id="g", kind="edit", node_id=good_node, fields=[improve.Field_(key="summary", value="better")], evidence="e", expected_effect="+"),
            improve.Change(id="u", kind="edit", node_id=useless_node, fields=[improve.Field_(key="summary", value="meh")], evidence="e", expected_effect="?")]),
        improve.Proposal(diagnosis="nothing left", changes=[
            improve.Change(id="u2", kind="edit", node_id=useless_node, fields=[improve.Field_(key="summary", value="meh")], evidence="e", expected_effect="?")]),
        improve.Proposal(diagnosis="still nothing", changes=[
            improve.Change(id="u3", kind="edit", node_id=useless_node, fields=[improve.Field_(key="avoid_when", value="x")], evidence="e", expected_effect="?")]),
    ])
    res = improve.run_night(evaluate, lambda ev: next(proposals), runs=2, rounds=5, budget=1000, commit=False)
    outcomes = [r["outcome"] for r in res["rounds"]]
    assert outcomes == ["accepted", "rejected", "rejected"]  # stops after 2 rejected rounds
    assert [c["node_id"] for c in res["accepted"]] == [good_node]  # the useless edit died in stage A
    ov = knowledge.load_overrides()
    assert good_node in ov["edit"] and useless_node not in ov["edit"]  # rejected deltas reverted
    knowledge.nodes.cache_clear()
