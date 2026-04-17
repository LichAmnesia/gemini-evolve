"""Tests for applying evolved content back to the target file."""

from gemini_evolve.config import EvolutionConfig
from gemini_evolve.evolve import EvolutionResult, _apply_result


def test_apply_creates_backup_with_full_original_filename(tmp_path):
    target = tmp_path / "GEMINI.md"
    target.write_text("baseline")

    result = EvolutionResult(
        target_name="global",
        target_path=str(target),
        baseline_score=0.5,
        evolved_score=0.6,
        improvement_pct=20.0,
        baseline_size=len("baseline"),
        evolved_size=len("evolved"),
        generations=1,
        elapsed_seconds=0.0,
        evolved_content="evolved",
        baseline_content="baseline",
        constraints_passed=True,
    )

    _apply_result(result, EvolutionConfig())

    backups = list(tmp_path.glob("GEMINI.md.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == "baseline"
    assert target.read_text() == "evolved"
