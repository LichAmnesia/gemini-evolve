"""Core evolution loop — tournament selection with LLM-guided mutation."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import EvolutionConfig, EVOLUTION_TARGETS
from .constraints import ConstraintValidator
from .dataset import EvalDataset, EvalExample, SyntheticDatasetBuilder, GoldenDatasetLoader
from .fitness import LLMJudge, fast_heuristic_score
from .mutator import Mutator
from .session_miner import GeminiSessionMiner

console = Console()


@dataclass
class EvolutionResult:
    target_name: str
    target_path: str
    baseline_score: float
    evolved_score: float
    improvement_pct: float
    baseline_size: int
    evolved_size: int
    generations: int
    elapsed_seconds: float
    evolved_content: str
    baseline_content: str
    constraints_passed: bool
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def improved_above(self, min_pct: float = 0.0) -> bool:
        return self.improvement_pct > min_pct

    @property
    def improved(self) -> bool:
        return self.improvement_pct > 0

    def to_dict(self) -> dict:
        return {
            "target_name": self.target_name,
            "target_path": self.target_path,
            "baseline_score": self.baseline_score,
            "evolved_score": self.evolved_score,
            "improvement_pct": self.improvement_pct,
            "baseline_size": self.baseline_size,
            "evolved_size": self.evolved_size,
            "generations": self.generations,
            "elapsed_seconds": self.elapsed_seconds,
            "constraints_passed": self.constraints_passed,
            "timestamp": self.timestamp,
        }


def _get_project_search_paths() -> list[Path]:
    """Get directories to scan for project-level GEMINI.md files."""
    import os
    custom = os.environ.get("GEMINI_EVOLVE_PROJECT_PATHS")
    if custom:
        return [Path(p) for p in custom.split(":") if p]
    # Default: ~/ws, ~/projects, ~/code
    candidates = [Path.home() / d for d in ("ws", "projects", "code")]
    return [c for c in candidates if c.exists()]


def discover_targets(config: EvolutionConfig, target_type: str = "instructions") -> list[Path]:
    """Find all evolution targets of a given type."""
    targets = []

    if target_type == "instructions":
        # Global GEMINI.md
        global_md = config.gemini_home / "GEMINI.md"
        if global_md.exists():
            targets.append(global_md)
        # Project-level .gemini/GEMINI.md files (up to 3 levels deep)
        for search_dir in _get_project_search_paths():
            for gemini_dir in search_dir.glob("**/.gemini"):
                # Skip anything deeper than 3 levels to avoid traversal explosion
                try:
                    rel = gemini_dir.relative_to(search_dir)
                except ValueError:
                    continue
                if len(rel.parts) > 4:
                    continue
                md = gemini_dir / "GEMINI.md"
                if md.exists():
                    targets.append(md)

    elif target_type == "commands":
        cmd_dir = config.commands_dir
        if cmd_dir.exists():
            targets.extend(cmd_dir.glob("*.toml"))

    elif target_type == "skills":
        skills_dir = config.skills_dir
        if skills_dir.is_symlink():
            skills_dir = skills_dir.resolve()
        if skills_dir.exists():
            targets.extend(skills_dir.rglob("*.md"))

    return targets


def _detect_target_type(path: Path) -> str:
    """Detect the evolution target type from a file path."""
    if path.name == "GEMINI.md":
        return "instructions"
    if path.suffix == ".toml":
        return "commands"
    return "skills"


def _size_limit_for_type(target_type: str, config: EvolutionConfig) -> float:
    """Get the size limit for a target type, preferring per-type config."""
    target_info = EVOLUTION_TARGETS.get(target_type)
    if target_info:
        return target_info["max_size_kb"]
    return config.max_size_kb


def load_target(path: Path) -> dict:
    """Load a target file and parse its content."""
    content = path.read_text()
    name = path.stem
    if path.name == "GEMINI.md":
        name = path.parent.name if path.parent.name != ".gemini" else "global"
    return {
        "name": name,
        "path": str(path),
        "content": content,
        "size": len(content.encode("utf-8")),
    }


def _simulate_agent(
    instructions: str,
    task_input: str,
    model: str,
    target_path: Path | None = None,
    **kwargs,
) -> str:
    """Simulate an agent response via Gemini CLI.

    Runs the prompt through `gemini -p` in plan/sandbox mode so the CLI loads
    the full environment (GEMINI.md, tools, skills, MCP). This evaluates
    instruction quality in the real deployment context.
    """
    from .cli_runner import run_gemini_cli, find_gemini_cli

    if not find_gemini_cli():
        console.print("[red]gemini CLI not found on PATH — cannot evaluate[/red]")
        return ""

    # Determine cwd: use the project directory that contains the target GEMINI.md
    cwd = None
    if target_path:
        # Walk up to find the project root (parent of .gemini/ dir)
        if target_path.parent.name == ".gemini":
            cwd = target_path.parent.parent
        else:
            cwd = target_path.parent

    result = run_gemini_cli(
        prompt=task_input,
        timeout_seconds=300,
        cwd=cwd,
    )
    if result.ok:
        return result.response
    if result.error:
        console.print(f"[dim red]CLI error: {result.error}[/dim red]")
    return ""


_judge_cache: dict[str, LLMJudge] = {}


def _get_judge(model: str) -> LLMJudge:
    """Reuse a single LLMJudge instance per model."""
    if model not in _judge_cache:
        _judge_cache[model] = LLMJudge(model=model)
    return _judge_cache[model]


def _evaluate_variant(
    variant: str,
    examples: list[EvalExample],
    config: EvolutionConfig,
    use_llm_judge: bool = False,
    target_path: Path | None = None,
) -> float:
    """Score a variant against evaluation examples using Gemini CLI."""
    if not examples:
        return 0.0

    scores = []
    for ex in examples:
        output = _simulate_agent(
            variant, ex.task_input, config.mutator_model,
            target_path=target_path,
        )

        # Skip examples where CLI timed out or failed — don't penalize with 0
        if not output:
            continue

        if use_llm_judge:
            judge = _get_judge(config.judge_model)
            score = judge.score(variant, ex.task_input, ex.expected_behavior, output)
            scores.append(score.composite)
        else:
            scores.append(fast_heuristic_score(ex.expected_behavior, output))

    return sum(scores) / len(scores) if scores else 0.0


def evolve(
    target_path: Path,
    config: EvolutionConfig | None = None,
    eval_source: str = "synthetic",
    eval_dataset_path: Path | None = None,
    dry_run: bool = False,
    use_llm_judge: bool = False,
    apply: bool = False,
) -> EvolutionResult:
    """Run the full evolution loop on a single target.

    Steps:
    1. Load target
    2. Generate/load evaluation dataset
    3. Validate baseline constraints
    4. For each generation:
       a. Generate mutant population
       b. Evaluate each variant on train set
       c. Select best (tournament)
       d. Optionally crossover top variants
    5. Validate evolved constraints
    6. Evaluate on holdout set vs baseline
    7. Save results
    """
    if config is None:
        config = EvolutionConfig.from_env()

    start_time = time.time()
    target = load_target(target_path)
    console.print(f"[bold]Evolving:[/bold] {target['name']} ({target['path']})")

    # --- Step 2: Dataset ---
    console.print("[dim]Generating evaluation dataset...[/dim]")
    dataset = _build_dataset(target["content"], eval_source, eval_dataset_path, config)
    console.print(
        f"  train={len(dataset.train)} val={len(dataset.val)} holdout={len(dataset.holdout)}"
    )

    if not dataset.train:
        console.print("[red]No training examples generated. Aborting.[/red]")
        return _empty_result(target, time.time() - start_time)

    # --- Step 3: Baseline constraints ---
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

    # --- Step 4-5: Evolution loop ---
    mutator = Mutator(model=config.mutator_model)
    best_variant = target["content"]
    eval_kw = dict(target_path=target_path)
    best_score = _evaluate_variant(best_variant, dataset.val, config, use_llm_judge, **eval_kw)
    console.print(f"[dim]Baseline val score: {best_score:.3f}[/dim]")

    feedback_acc = ""

    for gen in range(config.generations):
        console.print(f"\n[bold cyan]Generation {gen + 1}/{config.generations}[/bold cyan]")

        # Generate population
        variants = mutator.generate_population(
            best_variant,
            size=config.population_size,
            feedback=feedback_acc,
            temperature=config.mutation_temperature,
        )
        console.print(f"  Generated {len(variants)} variants")

        # Evaluate each variant
        scored: list[tuple[str, float]] = []
        for i, variant in enumerate(variants):
            # Quick constraint check
            constraints = validator.validate_all(variant, baseline=target["content"])
            if not validator.all_passed(constraints):
                console.print(f"  Variant {i+1}: [red]CONSTRAINT FAIL[/red]")
                continue

            score = _evaluate_variant(variant, dataset.val, config, use_llm_judge, **eval_kw)
            scored.append((variant, score))
            delta = score - best_score
            color = "green" if delta > 0 else "red" if delta < 0 else "yellow"
            console.print(f"  Variant {i+1}: {score:.3f} ([{color}]{delta:+.3f}[/{color}])")

        if not scored:
            console.print("  [yellow]No valid variants this generation[/yellow]")
            continue

        # Tournament selection
        scored.sort(key=lambda x: x[1], reverse=True)
        top_variant, top_score = scored[0]

        # Crossover if we have 2+ good variants
        if len(scored) >= 2 and config.crossover_rate > 0:
            import random as _rand

            if _rand.random() < config.crossover_rate:
                child = mutator.crossover(
                    scored[0][0], scored[0][1], scored[1][0], scored[1][1]
                )
                child_score = _evaluate_variant(
                    child, dataset.val, config, use_llm_judge, **eval_kw
                )
                if child_score > top_score:
                    constraints = validator.validate_all(child, baseline=target["content"])
                    if validator.all_passed(constraints):
                        top_variant, top_score = child, child_score
                        console.print(f"  Crossover: {child_score:.3f} [green]adopted[/green]")

        if top_score > best_score:
            best_variant = top_variant
            best_score = top_score
            console.print(f"  [green]New best: {best_score:.3f}[/green]")

        # Accumulate feedback for next generation
        if use_llm_judge:
            judge = _get_judge(config.judge_model)
            sample_ex = dataset.val[0] if dataset.val else dataset.train[0]
            output = _simulate_agent(
                best_variant, sample_ex.task_input, config.mutator_model,
                target_path=target_path,
            )
            judge_score = judge.score(
                best_variant, sample_ex.task_input, sample_ex.expected_behavior, output
            )
            feedback_acc = judge_score.feedback

    # --- Step 6: Final validation ---
    console.print("\n[bold]Final constraint validation...[/bold]")
    final_constraints = validator.validate_all(best_variant, baseline=target["content"])
    constraints_passed = validator.all_passed(final_constraints)
    for c in final_constraints:
        status = "[green]PASS[/green]" if c.passed else "[red]FAIL[/red]"
        console.print(f"  {status} {c.name}: {c.message}")

    # --- Step 7: Holdout evaluation ---
    console.print("\n[bold]Holdout evaluation...[/bold]")
    baseline_holdout = _evaluate_variant(
        target["content"], dataset.holdout, config, use_llm_judge, **eval_kw
    )
    evolved_holdout = _evaluate_variant(
        best_variant, dataset.holdout, config, use_llm_judge, **eval_kw
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
        evolved_size=len(best_variant.encode("utf-8")),
        generations=config.generations,
        elapsed_seconds=elapsed,
        evolved_content=best_variant,
        baseline_content=target["content"],
        constraints_passed=constraints_passed,
    )

    # --- Step 8: Report & Apply ---
    _print_report(result, config)
    _save_result(result, config)

    if apply:
        _apply_result(result, config)

    return result


def _build_dataset(
    instructions: str,
    eval_source: str,
    eval_dataset_path: Path | None,
    config: EvolutionConfig,
) -> EvalDataset:
    if eval_source == "golden" and eval_dataset_path:
        return GoldenDatasetLoader.load(
            eval_dataset_path, config.train_ratio, config.val_ratio
        )
    if eval_source == "session":
        miner = GeminiSessionMiner(config.gemini_home)
        examples = miner.extract_examples(max_examples=config.dataset_size)
        if examples:
            from .dataset import EvalDataset

            n = len(examples)
            t = int(n * config.train_ratio)
            v = t + int(n * config.val_ratio)
            return EvalDataset(train=examples[:t], val=examples[t:v], holdout=examples[v:])

    # Default: synthetic
    builder = SyntheticDatasetBuilder(model=config.dataset_model)
    return builder.generate(
        instructions, count=config.dataset_size, train_ratio=config.train_ratio, val_ratio=config.val_ratio
    )


def _empty_result(target: dict, elapsed: float) -> EvolutionResult:
    return EvolutionResult(
        target_name=target["name"],
        target_path=target["path"],
        baseline_score=0.0,
        evolved_score=0.0,
        improvement_pct=0.0,
        baseline_size=target["size"],
        evolved_size=target["size"],
        generations=0,
        elapsed_seconds=elapsed,
        evolved_content=target["content"],
        baseline_content=target["content"],
        constraints_passed=True,
    )


def _print_report(result: EvolutionResult, config: EvolutionConfig | None = None) -> None:
    min_pct = config.min_improvement_pct if config else 2.0
    meets_threshold = result.improved_above(min_pct)

    table = Table(title="Evolution Results")
    table.add_column("Metric", style="bold")
    table.add_column("Baseline")
    table.add_column("Evolved")
    table.add_column("Delta")

    score_delta = result.evolved_score - result.baseline_score
    score_color = "green" if score_delta > 0 else "red" if score_delta < 0 else "yellow"

    table.add_row(
        "Holdout Score",
        f"{result.baseline_score:.3f}",
        f"{result.evolved_score:.3f}",
        f"[{score_color}]{score_delta:+.3f} ({result.improvement_pct:+.1f}%)[/{score_color}]",
    )

    size_delta = result.evolved_size - result.baseline_size
    table.add_row(
        "Size (bytes)",
        str(result.baseline_size),
        str(result.evolved_size),
        f"{size_delta:+d}",
    )

    table.add_row("Generations", "", str(result.generations), "")
    table.add_row("Time", "", f"{result.elapsed_seconds:.1f}s", "")
    table.add_row(
        "Constraints",
        "",
        "[green]PASS[/green]" if result.constraints_passed else "[red]FAIL[/red]",
        "",
    )
    table.add_row(
        f"Min improvement ({min_pct}%)",
        "",
        "[green]PASS[/green]" if meets_threshold else "[yellow]BELOW[/yellow]",
        "",
    )

    console.print(table)

    if meets_threshold and result.constraints_passed:
        console.print(
            f"\n[bold green]Evolution improved {result.target_name} "
            f"by {result.improvement_pct:+.1f}%[/bold green]"
        )
    elif result.improved and not meets_threshold:
        console.print(
            f"\n[bold yellow]Improvement {result.improvement_pct:+.1f}% below "
            f"threshold {min_pct}% — not recommended for deployment[/bold yellow]"
        )
    elif not result.constraints_passed:
        console.print(
            f"\n[bold red]Evolution failed constraints for {result.target_name}[/bold red]"
        )
    else:
        console.print(
            f"\n[bold yellow]Evolution did not improve {result.target_name}[/bold yellow]"
        )


def _save_result(result: EvolutionResult, config: EvolutionConfig) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = config.output_dir / result.target_name / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    meets_threshold = result.improved_above(config.min_improvement_pct)
    metrics = result.to_dict()
    metrics["meets_min_improvement"] = meets_threshold
    metrics["min_improvement_pct"] = config.min_improvement_pct

    (out_dir / "evolved.md").write_text(result.evolved_content)
    (out_dir / "baseline.md").write_text(result.baseline_content)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    if not meets_threshold and result.improved:
        console.print(
            f"\n[dim]Results saved to {out_dir} "
            f"[yellow](below {config.min_improvement_pct}% threshold — not recommended)[/yellow][/dim]"
        )
    else:
        console.print(f"\n[dim]Results saved to {out_dir}[/dim]")


def _apply_result(result: EvolutionResult, config: EvolutionConfig) -> None:
    """Write evolved content back to the original file if it passes all gates.

    Gates:
    1. Constraints passed (size, growth)
    2. Improvement >= min threshold
    3. Content actually changed

    Creates a timestamped .bak backup before overwriting.
    """
    meets_threshold = result.improved_above(config.min_improvement_pct)

    if not result.constraints_passed:
        console.print("[yellow]--apply: skipped — constraints not passed[/yellow]")
        return
    if not meets_threshold:
        console.print(
            f"[yellow]--apply: skipped — improvement {result.improvement_pct:+.1f}% "
            f"below {config.min_improvement_pct}% threshold[/yellow]"
        )
        return
    if result.evolved_content == result.baseline_content:
        console.print("[yellow]--apply: skipped — no change[/yellow]")
        return

    target = Path(result.target_path)
    if not target.exists():
        console.print(f"[red]--apply: target file not found: {target}[/red]")
        return

    # Backup: GEMINI.md -> GEMINI.md.20260415_143000.bak
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = target.with_name(f"{target.name}.{ts}.bak")
    backup_path.write_text(result.baseline_content)

    # Write evolved content back
    target.write_text(result.evolved_content)

    console.print(
        f"\n[bold green]Applied:[/bold green] {target}\n"
        f"  Backup: {backup_path}\n"
        f"  Improvement: {result.improvement_pct:+.1f}%\n"
        f"  Next Gemini CLI session will use the evolved version."
    )
