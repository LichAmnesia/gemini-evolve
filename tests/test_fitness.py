"""Tests for fitness scoring."""

from gemini_evolve.fitness import FitnessScore, fast_heuristic_score


def test_fitness_composite():
    score = FitnessScore(correctness=0.8, procedure_following=0.6, conciseness=0.9)
    # 0.5*0.8 + 0.3*0.6 + 0.2*0.9 = 0.4 + 0.18 + 0.18 = 0.76
    assert abs(score.composite - 0.76) < 0.001


def test_fitness_composite_zeros():
    score = FitnessScore()
    assert score.composite == 0.0


def test_fast_heuristic_perfect_overlap():
    score = fast_heuristic_score("hello world test", "hello world test")
    assert score == 1.0


def test_fast_heuristic_no_overlap():
    score = fast_heuristic_score("hello world", "foo bar baz")
    assert score == 0.3  # base score


def test_fast_heuristic_partial_overlap():
    score = fast_heuristic_score("hello world test", "hello foo bar")
    # 1/3 overlap
    expected = 0.3 + 0.7 * (1 / 3)
    assert abs(score - expected) < 0.01


def test_fast_heuristic_empty():
    assert fast_heuristic_score("", "anything") == 0.0
    assert fast_heuristic_score("anything", "") == 0.0
    assert fast_heuristic_score("", "") == 0.0
