"""Constraint validation for evolved artifacts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConstraintResult:
    name: str
    passed: bool
    message: str
    value: float | None = None
    limit: float | None = None


class ConstraintValidator:
    """Validates evolved artifacts against hard gates."""

    def __init__(self, max_size_kb: float = 15.0, max_growth_pct: float = 20.0):
        self.max_size_kb = max_size_kb
        self.max_growth_pct = max_growth_pct

    def validate_all(
        self,
        content: str,
        baseline: str | None = None,
    ) -> list[ConstraintResult]:
        results = [
            self._check_non_empty(content),
            self._check_size(content),
        ]
        if baseline is not None:
            results.append(self._check_growth(content, baseline))
        return results

    def all_passed(self, results: list[ConstraintResult]) -> bool:
        return all(r.passed for r in results)

    def _check_non_empty(self, content: str) -> ConstraintResult:
        stripped = content.strip()
        return ConstraintResult(
            name="non_empty",
            passed=len(stripped) > 0,
            message="Content is non-empty" if stripped else "Content is empty",
        )

    def _check_size(self, content: str) -> ConstraintResult:
        size_kb = len(content.encode("utf-8")) / 1024
        passed = size_kb <= self.max_size_kb
        return ConstraintResult(
            name="size_limit",
            passed=passed,
            message=f"{size_kb:.1f}KB {'<=' if passed else '>'} {self.max_size_kb}KB",
            value=size_kb,
            limit=self.max_size_kb,
        )

    def _check_growth(self, content: str, baseline: str) -> ConstraintResult:
        baseline_len = len(baseline.encode("utf-8"))
        evolved_len = len(content.encode("utf-8"))
        if baseline_len == 0:
            return ConstraintResult(
                name="growth_limit",
                passed=True,
                message="No baseline to compare (new content)",
            )
        growth_pct = ((evolved_len - baseline_len) / baseline_len) * 100
        passed = growth_pct <= self.max_growth_pct
        return ConstraintResult(
            name="growth_limit",
            passed=passed,
            message=f"Growth {growth_pct:+.1f}% {'<=' if passed else '>'} {self.max_growth_pct}%",
            value=growth_pct,
            limit=self.max_growth_pct,
        )
