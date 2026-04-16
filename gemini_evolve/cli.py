"""CLI entry point for gemini-evolve."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from .config import EvolutionConfig

console = Console()


@click.group()
@click.version_option(package_name="gemini-evolve")
def main():
    """gemini-evolve — Self-evolution system for Gemini CLI."""
    pass


@main.command()
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--generations", "-g", default=5, help="Number of evolution generations.")
@click.option("--population", "-p", default=4, help="Population size per generation.")
@click.option(
    "--eval-source",
    type=click.Choice(["synthetic", "session", "golden"]),
    default="synthetic",
    help="Where to source evaluation data.",
)
@click.option("--eval-dataset", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, help="Validate only, don't optimize.")
@click.option("--llm-judge", is_flag=True, help="Use LLM judge instead of fast heuristic.")
@click.option("--output", "-o", type=click.Path(path_type=Path), default="output")
@click.option("--apply", is_flag=True, help="Write back to original file if improved (backup created).")
def evolve(
    target: Path,
    generations: int,
    population: int,
    eval_source: str,
    eval_dataset: Path | None,
    dry_run: bool,
    llm_judge: bool,
    output: Path,
    apply: bool,
):
    """Evolve a single target file (GEMINI.md, command, or skill)."""
    from .evolve import evolve as run_evolve

    config = EvolutionConfig.from_env()
    config.generations = generations
    config.population_size = population
    config.output_dir = output

    result = run_evolve(
        target_path=target,
        config=config,
        eval_source=eval_source,
        eval_dataset_path=eval_dataset,
        dry_run=dry_run,
        use_llm_judge=llm_judge,
        apply=apply,
    )

    if result.improved and result.constraints_passed:
        raise SystemExit(0)
    elif dry_run:
        raise SystemExit(0)
    else:
        raise SystemExit(1)


@main.command("evolve-all")
@click.option(
    "--type",
    "target_type",
    type=click.Choice(["instructions", "commands", "skills"]),
    default="instructions",
)
@click.option("--generations", "-g", default=5)
@click.option("--population", "-p", default=4)
@click.option("--eval-source", default="synthetic")
@click.option("--eval-dataset", type=click.Path(exists=True, path_type=Path), default=None)
@click.option("--dry-run", is_flag=True)
@click.option("--llm-judge", is_flag=True)
@click.option("--output", "-o", type=click.Path(path_type=Path), default="output")
@click.option("--apply", is_flag=True, help="Write back to original files if improved.")
def evolve_all(
    target_type: str,
    generations: int,
    population: int,
    eval_source: str,
    eval_dataset: Path | None,
    dry_run: bool,
    llm_judge: bool,
    output: Path,
    apply: bool,
):
    """Discover and evolve all targets of a given type."""
    from .evolve import evolve as run_evolve, discover_targets

    if eval_source == "golden" and eval_dataset is None:
        raise click.UsageError("--eval-dataset is required when using --eval-source golden")

    config = EvolutionConfig.from_env()
    config.generations = generations
    config.population_size = population
    config.output_dir = output

    targets = discover_targets(config, target_type)
    if not targets:
        console.print(f"[yellow]No {target_type} targets found.[/yellow]")
        raise SystemExit(0)

    console.print(f"Found {len(targets)} {target_type} target(s)")
    results = []

    for target in targets:
        try:
            result = run_evolve(
                target_path=target,
                config=config,
                eval_source=eval_source,
                eval_dataset_path=eval_dataset,
                dry_run=dry_run,
                use_llm_judge=llm_judge,
                apply=apply,
            )
            results.append(result)
        except Exception as e:
            console.print(f"[red]Failed: {target} — {e}[/red]")

    improved = sum(1 for r in results if r.improved and r.constraints_passed)
    console.print(f"\n[bold]Summary: {improved}/{len(results)} targets improved[/bold]")


@main.command()
@click.option("--type", "target_type", default="instructions")
def discover(target_type: str):
    """List all discoverable evolution targets."""
    from .evolve import discover_targets

    config = EvolutionConfig.from_env()
    targets = discover_targets(config, target_type)

    if not targets:
        console.print(f"[yellow]No {target_type} targets found.[/yellow]")
        return

    for t in targets:
        size_kb = t.stat().st_size / 1024
        console.print(f"  {t} ({size_kb:.1f}KB)")


# --- Trigger commands ---


@main.group()
def trigger():
    """Manage evolution triggers (cron, watcher, hook)."""
    pass


@trigger.command("cron-install")
@click.option("--interval", default=24, help="Run every N hours.")
@click.option("--type", "target_type", default="instructions")
@click.option("--apply", is_flag=True, help="Auto-apply evolved results back to original files.")
def cron_install(interval: int, target_type: str, apply: bool):
    """Install a macOS launchd cron job for scheduled evolution."""
    from .triggers.cron import install_cron

    path = install_cron(interval_hours=interval, target_type=target_type, apply=apply)
    mode = "evolve + apply" if apply else "evolve only (results in output/)"
    console.print(f"[green]Installed:[/green] {path}")
    console.print(f"Evolution will run every {interval} hours ({mode}).")


@trigger.command("cron-remove")
def cron_remove():
    """Remove the scheduled evolution cron job."""
    from .triggers.cron import uninstall_cron

    if uninstall_cron():
        console.print("[green]Removed scheduled evolution job.[/green]")
    else:
        console.print("[yellow]No cron job found.[/yellow]")


@trigger.command("cron-status")
def cron_status():
    """Check the status of the scheduled evolution job."""
    from .triggers.cron import status

    s = status()
    if s["installed"]:
        console.print(f"[green]Installed:[/green] {s['plist_path']}")
        console.print(f"Loaded: {'yes' if s['loaded'] else 'no'}")
    else:
        console.print("[yellow]Not installed.[/yellow]")


@trigger.command("watch")
@click.option("--dir", "watch_dir", type=click.Path(path_type=Path), default=None)
@click.option("--debounce", default=60.0, help="Seconds to wait after last file change.")
@click.option("--type", "target_type", default="instructions")
@click.option("--apply", is_flag=True, help="Auto-apply evolved results back to original files.")
def watch(watch_dir: Path | None, debounce: float, target_type: str, apply: bool):
    """Watch for Gemini CLI session changes and auto-evolve."""
    from .triggers.watcher import run_watcher_blocking

    run_watcher_blocking(
        watch_dir=watch_dir,
        debounce_seconds=debounce,
        target_type=target_type,
        apply=apply,
    )


@trigger.command("hook-install")
@click.argument("repo", type=click.Path(exists=True, path_type=Path), default=".")
def hook_install(repo: Path):
    """Install a git post-commit hook for evolution."""
    from .triggers.hook import install_hook

    path = install_hook(repo)
    console.print(f"[green]Hook installed:[/green] {path}")


@trigger.command("hook-remove")
@click.argument("repo", type=click.Path(exists=True, path_type=Path), default=".")
def hook_remove(repo: Path):
    """Remove the git post-commit hook."""
    from .triggers.hook import uninstall_hook

    if uninstall_hook(repo):
        console.print("[green]Hook removed.[/green]")
    else:
        console.print("[yellow]No hook found.[/yellow]")


if __name__ == "__main__":
    main()
