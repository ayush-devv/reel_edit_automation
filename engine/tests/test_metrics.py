import pytest

from reel.evalh import metrics as m


def test_hook_iou_and_f1():
    assert m.hook_iou(range(10, 20), range(10, 20)) == 1.0
    assert m.hook_iou(range(0, 10), range(5, 15)) == pytest.approx(5 / 15)
    assert m.f1([1, 2, 3, 4], [3, 4, 5, 6]) == pytest.approx(0.5)
    assert m.f1([], []) == 1.0
    assert m.f1([1], [2]) == 0.0


def test_kendall_tau():
    assert m.kendall_tau(["a", "b", "c", "d"], ["a", "b", "c", "d"]) == 1.0
    assert m.kendall_tau(["d", "c", "b", "a"], ["a", "b", "c", "d"]) == -1.0
    assert m.kendall_tau(["a", "x"], ["a", "x"]) is None  # < 3 shared


def test_cut_rate_score():
    assert m.cut_rate_score(25, 25) == 1.0
    assert m.cut_rate_score(50, 25) == 0.0
    assert m.cut_rate_score(25 * 2 ** 0.5, 25) == pytest.approx(0.5)


def test_story_score_drops_tau_and_reweights():
    with_tau = m.story_score(1, 1, 1.0, 1)
    without = m.story_score(1, 1, None, 1)
    assert with_tau == pytest.approx(1.0) and without == pytest.approx(1.0)
    assert m.story_score(0, 1, None, 0) == pytest.approx(0.35 / 0.85)


def test_wer():
    assert m.word_error_rate("the cat sat".split(), "the cat sat".split()) == 0.0
    assert m.word_error_rate("the cat sat".split(), "the sat".split()) == pytest.approx(1 / 3)
    assert m.word_error_rate("a b".split(), []) == 1.0


def test_caption_score():
    assert m.caption_score(0.0, 0.0) == pytest.approx(1.0)
    assert m.caption_score(0.1, 75.0) == pytest.approx(0.6 * 0.9 + 0.4 * 0.5)
    assert m.caption_score(0.0, None) == pytest.approx(0.6)


def test_style_score_inside_iqr():
    ref = [20, 22, 24, 25, 26, 28, 30]
    assert m.robust_style_score(25, ref) == 1.0
    assert m.robust_style_score(60, ref) < 0.5


def test_primary_score_veto_and_reviewer_weight():
    s = m.ReelScore(families={"story": 1.0, "reviewer": 0.0})
    assert s.primary == 100.0  # reviewer uncalibrated → weight 0
    s.reviewer_kappa = 0.7
    assert s.primary == pytest.approx(100 * 0.40 / 0.55, abs=0.01)  # primary is rounded to 2 dp
    s.vetoes.append("crash")
    assert s.primary is None
    assert m.ReelScore().primary is None
