# Codemaps

**Last Updated:** 2026-04-16
**Package:** `gemini-evolve`
**Primary Entry Points:** `gemini_evolve/cli.py`, `gemini_evolve/evolve.py`

## Architecture

```text
Click CLI
  -> EvolutionConfig
  -> discover_targets()
  -> evolve()
       -> load target
       -> build dataset
            -> synthetic builder
            -> session miner
            -> golden loader
       -> mutate variants
       -> simulate agent via gemini CLI
       -> score + validate
       -> save output artifacts
       -> optionally apply + back up original

Trigger CLI
  -> watcher | cron | hook
  -> invoke evolve-all / evolve later
```

## Areas

| Area | Purpose | Main Files |
| --- | --- | --- |
| [Core Loop](core.md) | Target discovery, dataset build, GA engine, GEPA engine, scoring, apply | `cli.py`, `evolve.py`, `gepa_evolve.py`, `config.py` |
| [Triggers](triggers.md) | Watch sessions, install launchd job, install git hook | `triggers/watcher.py`, `triggers/cron.py`, `triggers/hook.py` |
| [Integrations](integrations.md) | Gemini CLI subprocesses, DSPy adapter, filesystem paths, launchctl, git hooks | `cli_runner.py`, `dspy_adapter.py`, `session_miner.py`, `triggers/*.py` |

## Module Inventory

| Module | Purpose | Key Dependencies |
| --- | --- | --- |
| `gemini_evolve/cli.py` | Click commands for evolve, discover, triggers | `click`, `rich`, `EvolutionConfig` |
| `gemini_evolve/evolve.py` | Main orchestration, reporting, result save/apply | `dataset`, `mutator`, `fitness`, `constraints`, `session_miner` |
| `gemini_evolve/gepa_evolve.py` | GEPA-based optimizer that returns the same `EvolutionResult` shape | `dspy`, `dspy_adapter`, `dataset`, `fitness` |
| `gemini_evolve/dspy_adapter.py` | DSPy LM adapter that shells out to the Gemini CLI and can capture traces | `dspy`, `cli_runner`, `session files` |
| `gemini_evolve/cli_runner.py` | Runs `gemini -p ... -o json` and tolerates prefix noise | `subprocess`, `shutil`, `json` |
| `gemini_evolve/dataset.py` | Synthetic dataset generation and JSONL load/save | `cli_runner`, `json_utils` |
| `gemini_evolve/mutator.py` | Mutation and crossover prompts | `cli_runner` |
| `gemini_evolve/fitness.py` | Heuristic overlap score and LLM judge | `cli_runner`, `json_utils` |
| `gemini_evolve/constraints.py` | Hard gates for empty/size/growth | standard library only |
| `gemini_evolve/session_miner.py` | Mines Gemini session files, filters secrets | `dataset`, `re`, `json` |
| `gemini_evolve/json_utils.py` | Pulls JSON from code fences or embedded blobs | `json`, `re` |
| `gemini_evolve/triggers/*` | Automation entry points | `watchdog`, `launchctl`, git hooks |

## Test Coverage

Tests currently cover:

- CLI JSON parsing
- dataset serialization
- constraint gates
- fitness scoring math
- session mining and secret filtering
- git hook install/remove
- apply backup behavior
- DSPy adapter trace capture
- GEPA smoke tests

## Related Docs

- [README.md](../../README.md)
- [docs/CONTRIB.md](../CONTRIB.md)
- [docs/RUNBOOK.md](../RUNBOOK.md)
