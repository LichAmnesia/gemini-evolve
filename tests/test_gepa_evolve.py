"""Smoke tests for the GEPA evolve module — fully mocked, no network / CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("dspy")

import dspy  # noqa: E402

from gemini_evolve.dataset import EvalDataset, EvalExample  # noqa: E402
from gemini_evolve.gepa_evolve import (  # noqa: E402
    _build_program,
    _extract_evolved_text,
    _to_examples,
    _build_metric,
    evolve_with_gepa,
)
from gemini_evolve.dspy_adapter import GeminiCLILM  # noqa: E402


def test_build_program_sets_instructions():
    lm = _make_fake_lm()
    prog = _build_program("be concise", lm)
    assert prog.predict.signature.instructions == "be concise"


def test_build_program_deploy_mode_writes_gemini_md(tmp_path):
    """In deploy_mode, forward() must drop the current candidate into .gemini/GEMINI.md
    before the LM runs — so the CLI's auto-discovery picks up the candidate."""
    lm = _make_fake_lm()
    prog = _build_program("first candidate", lm, deploy_cwd=tmp_path)

    gemini_md = tmp_path / ".gemini" / "GEMINI.md"
    top_md = tmp_path / "GEMINI.md"
    assert not gemini_md.exists()  # Not written until forward runs.

    prog(task="anything")
    assert gemini_md.read_text() == "first candidate"
    assert top_md.read_text() == "first candidate"

    # Simulate GEPA mutating the signature between calls.
    prog.predict.signature = prog.predict.signature.with_instructions("second candidate")
    prog(task="anything else")
    assert gemini_md.read_text() == "second candidate"


def test_build_program_without_deploy_mode_does_not_write(tmp_path):
    lm = _make_fake_lm()
    prog = _build_program("x", lm, deploy_cwd=None)
    prog(task="task")
    assert not (tmp_path / ".gemini" / "GEMINI.md").exists()


def test_extract_evolved_text_from_built_program():
    lm = _make_fake_lm()
    prog = _build_program("first version", lm)
    assert _extract_evolved_text(prog) == "first version"
    # And after mutation, it reflects the updated text.
    prog.predict.signature = prog.predict.signature.with_instructions("second version")
    assert _extract_evolved_text(prog) == "second version"


def test_to_examples_preserves_inputs():
    raw = [EvalExample(task_input="a", expected_behavior="b")]
    examples = _to_examples(raw)
    assert len(examples) == 1
    assert examples[0].task == "a"
    assert examples[0].expected == "b"
    # .inputs() must include `task` so DSPy can call the program.
    assert "task" in examples[0].inputs()


def _make_fake_lm(response: str = "fake answer", monkeypatch=None) -> GeminiCLILM:
    """Build a real GeminiCLILM but stub out the CLI so nothing shells out.

    Going through the real __init__ keeps every dspy.LM attribute that
    Predict expects (`.kwargs`, `.model_type`, `.history`, etc.) — our
    earlier hand-rolled subclass kept drifting out of sync with dspy.
    """
    from gemini_evolve.cli_runner import CLIResult
    from gemini_evolve import dspy_adapter as _adapter

    def fake_run(prompt, *, model, timeout_seconds, cwd=None, **kw):
        return CLIResult(response=response, exit_code=0)

    if monkeypatch is not None:
        monkeypatch.setattr(_adapter, "run_gemini_cli", fake_run)
    else:  # Used in tests that construct the LM at module scope.
        _adapter.run_gemini_cli = fake_run  # type: ignore[assignment]
    return GeminiCLILM(model="fake-model")


def test_metric_returns_score_and_feedback():
    lm = _make_fake_lm()
    metric = _build_metric(lm, config=None)  # type: ignore[arg-type]

    gold = dspy.Example(task="add 2 and 2", expected="four").with_inputs("task")
    pred = dspy.Prediction(response="the answer is four")

    out = metric(gold, pred)
    assert hasattr(out, "score")
    assert hasattr(out, "feedback")
    assert 0.0 <= out.score <= 1.0
    assert "task:" in out.feedback
    assert "actual response:" in out.feedback


def test_metric_includes_trace_when_available():
    from gemini_evolve.dspy_adapter import CapturedTrace

    lm = _make_fake_lm()
    lm.last_trace = CapturedTrace(
        prompt="search",
        response="found",
        tool_calls=[{"name": "grep", "args": "foo", "result": "ok"}],
    )

    metric = _build_metric(lm, config=None)  # type: ignore[arg-type]
    gold = dspy.Example(task="find foo", expected="the answer").with_inputs("task")
    pred = dspy.Prediction(response="found")

    out = metric(gold, pred)
    assert "execution trace:" in out.feedback
    assert "grep" in out.feedback


def test_evolve_with_gepa_dry_run(tmp_path, monkeypatch):
    """Dry run should not invoke GEPA or the CLI — just validate constraints."""
    target = tmp_path / "GEMINI.md"
    target.write_text("# Seed\n- be brief\n")

    # Make dataset build return a nonempty set so we reach the dry-run short-circuit.
    def fake_build_dataset(*a, **kw):
        ex = [EvalExample(task_input="t", expected_behavior="e")]
        return EvalDataset(train=ex, val=ex, holdout=ex)

    monkeypatch.setattr("gemini_evolve.gepa_evolve._build_dataset", fake_build_dataset)

    # If GEPA accidentally runs it will fail hard (no LM / no CLI), so this
    # test also asserts the dry-run guard works.
    def boom(*a, **kw):
        raise AssertionError("GEPA.compile should not run during --dry-run")

    monkeypatch.setattr("dspy.GEPA.compile", boom)

    result = evolve_with_gepa(target_path=target, dry_run=True)
    assert result.baseline_content == "# Seed\n- be brief\n"
    assert result.evolved_content == "# Seed\n- be brief\n"
    assert result.generations == 0
