"""GEPA-based evolution loop — drop-in replacement for the tournament GA.

Wraps `dspy.GEPA` with gemini-evolve's existing dataset / constraint / fitness
infrastructure. Produces the same `EvolutionResult` as the classic engine so
the CLI, trigger, and apply code paths don't need to know which engine ran.

What changes vs. the GA:
  * No hand-written mutation strategies. GEPA's reflector LLM reads the
    current prompt, the task, the agent's response (and optionally its
    execution trace), then proposes a targeted edit.
  * One optimization call replaces the generations × population × variants
    nested loop.
  * A metric that returns `dspy.Prediction(score, feedback)` gives GEPA the
    signal it needs to do reflective mutation. Without feedback the engine
    degenerates into a random-restart baseline, so Step 2 (trace capture)
    wires the Gemini CLI's tool trajectory into `feedback`.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from .config import EVOLUTION_TARGETS, EvolutionConfig
from .constraints import ConstraintValidator
from .dataset import EvalDataset, EvalExample
from .evolve import (
    EvolutionResult,
    _apply_result,
    _build_dataset,
    _empty_result,
    _print_report,
    _save_result,
    _size_limit_for_type,
    _detect_target_type,
    load_target,
)
from .fitness import fast_heuristic_score

console = Console()


def _require_dspy():
    from .dspy_adapter import is_dspy_available

    if not is_dspy_available():
        raise ImportError(
            "dspy is required for the 'gepa' engine. Install with:\n"
            "  pip install 'dspy>=2.6'"
        )


def _build_program(instructions: str, lm, deploy_cwd: Path | None = None):
    """Build a one-predictor DSPy program whose instructions == `instructions`.

    GEPA will mutate `self.predict.signature.instructions` in place; after
    compile finishes we pull that field back out as the evolved content.

    If `deploy_cwd` is set, the module writes the current candidate to
    `<deploy_cwd>/.gemini/GEMINI.md` (and `<deploy_cwd>/GEMINI.md`) before
    each forward pass. This is the deploy-like evaluation mode: the Gemini
    CLI auto-loads the candidate as if it were the active system
    instruction, so we measure the candidate's effect in the same path a
    real session would hit. Without this, the candidate lives only inside
    the DSPy-rendered prompt (cleaner isolation, less realistic).
    """
    import dspy

    signature = dspy.Signature(
        "task -> response",
        instructions,
    )

    class InstructionModule(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(signature)
            # Mutable fields GEPA can't see — we consult them in forward().
            self._deploy_cwd = deploy_cwd

        def _write_candidate(self) -> None:
            if self._deploy_cwd is None:
                return
            text = self.predict.signature.instructions or ""
            gemini_dir = self._deploy_cwd / ".gemini"
            gemini_dir.mkdir(parents=True, exist_ok=True)
            (gemini_dir / "GEMINI.md").write_text(text)
            # Some users keep a top-level GEMINI.md; write both so either
            # discovery rule picks up the candidate.
            (self._deploy_cwd / "GEMINI.md").write_text(text)

        def forward(self, task: str):
            self._write_candidate()
            return self.predict(task=task)

    module = InstructionModule()
    # Make sure the underlying predictor uses our CLI LM specifically; GEPA
    # may call this module outside a `with dspy.context(lm=...)` block.
    module.predict.lm = lm
    return module


def _to_examples(items: list[EvalExample]):
    import dspy

    return [
        dspy.Example(task=ex.task_input, expected=ex.expected_behavior).with_inputs("task")
        for ex in items
    ]


def _score_with_heuristic(expected: str, actual: str) -> float:
    """Reuse the fast heuristic — same scoring the GA uses for train/val."""
    return fast_heuristic_score(expected, actual)


def _build_metric(lm, config: EvolutionConfig):
    """Produce a GEPAFeedbackMetric closure bound to our LM + config.

    GEPA calls this once per (candidate, example) pair. Returning
    `dspy.Prediction(score=..., feedback=...)` is what enables reflective
    mutation — the `feedback` string gets fed into the reflector LLM so it
    can diagnose why a particular response failed.
    """
    import dspy
    from .dspy_adapter import GeminiCLILM

    def metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
        # pred may be a Prediction (with .response) or a raw string on failure.
        response_text = getattr(pred, "response", "") if pred is not None else ""
        score = _score_with_heuristic(gold.expected, response_text)

        feedback_parts: list[str] = [
            f"task: {gold.task[:300]}",
            f"expected behavior rubric: {gold.expected[:300]}",
            f"actual response: {response_text[:600]}",
            f"heuristic score: {score:.3f}",
        ]

        # Step 2: if the LM captured a CLI trajectory, append it. This is the
        # signal that separates GEPA-with-traces from GEPA-without, and from
        # traditional GA.
        if isinstance(lm, GeminiCLILM) and lm.last_trace is not None:
            tool_summary = lm.last_trace.to_text(max_chars=1200)
            if tool_summary:
                feedback_parts.append("execution trace:")
                feedback_parts.append(tool_summary)

        # Heuristic diagnosis — cheap hints for the reflector to build on.
        if score < 0.4:
            feedback_parts.append(
                "Response scored poorly against the rubric — the instruction "
                "may need clearer directives about what to emit."
            )
        elif score >= 0.9:
            feedback_parts.append(
                "Response matched the rubric well; preserve the directives "
                "that produced this behavior."
            )

        feedback = "\n".join(feedback_parts)
        return dspy.Prediction(score=score, feedback=feedback)

    return metric


def _extract_evolved_text(program) -> str:
    """Pull the optimized instruction string out of a GEPA-compiled module."""
    if hasattr(program, "predict") and hasattr(program.predict, "signature"):
        return program.predict.signature.instructions or ""
    # Defensive: walk predictors if the module shape differs.
    for p in program.predictors():
        if hasattr(p, "signature"):
            return p.signature.instructions or ""
    return ""


def _evaluate_text(
    instructions: str,
    examples: list[EvalExample],
    lm,
    deploy_cwd: Path | None = None,
) -> float:
    """Re-evaluate a final instruction string on a holdout without GEPA's overhead.

    Builds a fresh Predict program whose signature.instructions == the given
    text, runs each example, and averages the heuristic score. Matches
    `evolve._evaluate_variant` so baseline/evolved holdout scores are
    directly comparable across engines.
    """
    if not examples:
        return 0.0

    program = _build_program(instructions, lm, deploy_cwd=deploy_cwd)
    scores: list[float] = []
    for ex in examples:
        try:
            pred = program(task=ex.task_input)
            text = getattr(pred, "response", "") or ""
        except Exception as e:  # pragma: no cover - defensive
            console.print(f"[dim red]eval error: {e}[/dim red]")
            continue
        if not text:
            continue
        scores.append(_score_with_heuristic(ex.expected_behavior, text))
    return sum(scores) / len(scores) if scores else 0.0


def evolve_with_gepa(
    target_path: Path,
    config: EvolutionConfig | None = None,
    *,
    eval_source: str = "synthetic",
    eval_dataset_path: Path | None = None,
    dry_run: bool = False,
    apply: bool = False,
    reflection_model: str | None = None,
    capture_trace: bool = False,
    auto_budget: str = "light",
    deploy_mode: bool = True,
) -> EvolutionResult:
    """Run GEPA against a single target and return an `EvolutionResult`.

    Parameters
    ----------
    target_path:
        GEMINI.md / skill / command file to evolve.
    config:
        EvolutionConfig; defaults to `.from_env()`.
    eval_source:
        "synthetic" | "session" | "golden" — same semantics as the GA.
    reflection_model:
        Model used for the reflector LM (the one that reads traces and
        proposes edits). Defaults to `config.judge_model` because reflection
        benefits from a stronger model than the one producing responses.
    capture_trace:
        If True, the worker LM reads Gemini CLI session files after each
        call and feeds the tool trajectory into GEPA's reflective feedback.
        This is the Step 2 switch.
    auto_budget:
        GEPA "auto" budget — "light" | "medium" | "heavy". Light is ~1-2x
        the number of examples in calls to the metric; heavy is ~10x.
    deploy_mode:
        When True (default), each forward pass writes the current candidate
        to `<isolated_cwd>/.gemini/GEMINI.md` and the CLI runs with that as
        its cwd. This matches real-deployment behaviour — the Gemini CLI
        picks up the candidate via its normal GEMINI.md discovery. When
        False, the candidate is only placed in the DSPy prompt (more
        isolated, doesn't exercise GEMINI.md auto-loading).
    """
    _require_dspy()

    import dspy
    import tempfile
    from dspy import GEPA

    from .dspy_adapter import GeminiCLILM

    if config is None:
        config = EvolutionConfig.from_env()

    start_time = time.time()
    target = load_target(target_path)
    console.print(
        f"[bold]Evolving (GEPA):[/bold] {target['name']} ({target['path']})"
    )

    # Dataset
    console.print("[dim]Generating evaluation dataset...[/dim]")
    dataset: EvalDataset = _build_dataset(
        target["content"], eval_source, eval_dataset_path, config
    )
    console.print(
        f"  train={len(dataset.train)} val={len(dataset.val)} holdout={len(dataset.holdout)}"
    )
    if not dataset.train:
        console.print("[red]No training examples generated. Aborting.[/red]")
        return _empty_result(target, time.time() - start_time)

    # Constraints on baseline
    target_type = _detect_target_type(target_path)
    size_limit = _size_limit_for_type(target_type, config)
    validator = ConstraintValidator(
        max_size_kb=size_limit, max_growth_pct=config.max_growth_pct
    )
    baseline_constraints = validator.validate_all(target["content"])
    for c in baseline_constraints:
        status = "[green]PASS[/green]" if c.passed else "[red]FAIL[/red]"
        console.print(f"  {status} {c.name}: {c.message}")

    if dry_run:
        console.print("[yellow]Dry run — skipping optimization.[/yellow]")
        return _empty_result(target, time.time() - start_time)

    # Set up the isolated working dir. In deploy_mode this is where each
    # candidate gets written as `.gemini/GEMINI.md` before the CLI runs, so
    # the CLI's normal auto-discovery picks up the CANDIDATE (not whatever
    # baseline happens to be on disk). Without this every variant would be
    # evaluated against the same unchanging GEMINI.md — exactly the bug in
    # the classic GA path's `_simulate_agent`.
    isolated_cwd = Path(tempfile.mkdtemp(prefix="gemini_evolve_gepa_"))
    deploy_cwd = isolated_cwd if deploy_mode else None

    # LMs: one for running the program (generating responses) and one for
    # reflection (reading feedback and proposing edits).
    worker_lm = GeminiCLILM(
        model=config.mutator_model,
        capture_trace=capture_trace,
        gemini_home=config.gemini_home,
        isolated_cwd=isolated_cwd,
    )
    reflector_lm = GeminiCLILM(
        model=reflection_model or config.judge_model,
        # Reflection never needs its own trace; cheap and unambiguous.
        capture_trace=False,
        gemini_home=config.gemini_home,
        # Reflector runs prompt-only — give it an empty cwd so its calls
        # don't see whatever candidate the worker just wrote to disk.
        isolated_cwd=Path(tempfile.mkdtemp(prefix="gemini_evolve_reflector_")),
    )
    dspy.settings.configure(lm=worker_lm)

    # Build program, dataset, metric
    program = _build_program(target["content"], worker_lm, deploy_cwd=deploy_cwd)
    trainset = _to_examples(dataset.train)
    valset = _to_examples(dataset.val) if dataset.val else None
    metric = _build_metric(worker_lm, config)

    console.print(
        f"[dim]Running GEPA (auto={auto_budget}, reflector={reflector_lm._cli_model})...[/dim]"
    )
    gepa = GEPA(
        metric=metric,
        auto=auto_budget,  # type: ignore[arg-type]
        reflection_lm=reflector_lm,
        num_threads=3,  # Parallel Gemini CLI calls; bump higher if no rate-limit hits.
        track_stats=False,
    )

    try:
        optimized = gepa.compile(program, trainset=trainset, valset=valset)
    except Exception as e:
        console.print(f"[red]GEPA run failed: {e}[/red]")
        return _empty_result(target, time.time() - start_time)

    evolved_text = _extract_evolved_text(optimized) or target["content"]

    # Post-GEPA: constraints + holdout eval (same shape as GA engine)
    console.print("\n[bold]Final constraint validation...[/bold]")
    final_constraints = validator.validate_all(evolved_text, baseline=target["content"])
    constraints_passed = validator.all_passed(final_constraints)
    for c in final_constraints:
        status = "[green]PASS[/green]" if c.passed else "[red]FAIL[/red]"
        console.print(f"  {status} {c.name}: {c.message}")

    console.print("\n[bold]Holdout evaluation...[/bold]")
    baseline_holdout = _evaluate_text(
        target["content"], dataset.holdout, worker_lm, deploy_cwd=deploy_cwd
    )
    evolved_holdout = _evaluate_text(
        evolved_text, dataset.holdout, worker_lm, deploy_cwd=deploy_cwd
    )

    if baseline_holdout > 0:
        improvement_pct = ((evolved_holdout - baseline_holdout) / baseline_holdout) * 100
    else:
        improvement_pct = 100.0 if evolved_holdout > 0 else 0.0

    elapsed = time.time() - start_time
    result = EvolutionResult(
        target_name=target["name"],
        target_path=target["path"],
        baseline_score=baseline_holdout,
        evolved_score=evolved_holdout,
        improvement_pct=improvement_pct,
        baseline_size=target["size"],
        evolved_size=len(evolved_text.encode("utf-8")),
        generations=1,  # GEPA collapses the concept of generations.
        elapsed_seconds=elapsed,
        evolved_content=evolved_text,
        baseline_content=target["content"],
        constraints_passed=constraints_passed,
    )

    _print_report(result, config)
    _save_result(result, config)
    if apply:
        _apply_result(result, config)

    return result
