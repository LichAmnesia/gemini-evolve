"""Tests for constraint validation."""

from gemini_evolve.constraints import ConstraintValidator


def test_non_empty_pass():
    v = ConstraintValidator()
    results = v.validate_all("hello world")
    assert results[0].name == "non_empty"
    assert results[0].passed


def test_non_empty_fail():
    v = ConstraintValidator()
    results = v.validate_all("   ")
    assert results[0].name == "non_empty"
    assert not results[0].passed


def test_size_limit_pass():
    v = ConstraintValidator(max_size_kb=1.0)
    content = "x" * 500  # ~0.5KB
    results = v.validate_all(content)
    size_result = next(r for r in results if r.name == "size_limit")
    assert size_result.passed


def test_size_limit_fail():
    v = ConstraintValidator(max_size_kb=1.0)
    content = "x" * 2000  # ~2KB
    results = v.validate_all(content)
    size_result = next(r for r in results if r.name == "size_limit")
    assert not size_result.passed


def test_growth_limit_pass():
    v = ConstraintValidator(max_growth_pct=20.0)
    baseline = "x" * 100
    evolved = "x" * 115  # +15%
    results = v.validate_all(evolved, baseline=baseline)
    growth_result = next(r for r in results if r.name == "growth_limit")
    assert growth_result.passed


def test_growth_limit_fail():
    v = ConstraintValidator(max_growth_pct=20.0)
    baseline = "x" * 100
    evolved = "x" * 130  # +30%
    results = v.validate_all(evolved, baseline=baseline)
    growth_result = next(r for r in results if r.name == "growth_limit")
    assert not growth_result.passed


def test_growth_shrink_always_passes():
    v = ConstraintValidator(max_growth_pct=20.0)
    baseline = "x" * 100
    evolved = "x" * 80  # -20%
    results = v.validate_all(evolved, baseline=baseline)
    growth_result = next(r for r in results if r.name == "growth_limit")
    assert growth_result.passed


def test_all_passed_helper():
    v = ConstraintValidator()
    results = v.validate_all("hello world")
    assert v.all_passed(results)


def test_all_passed_false():
    v = ConstraintValidator(max_size_kb=0.001)
    results = v.validate_all("hello world this is too big")
    assert not v.all_passed(results)
