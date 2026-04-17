# Core Loop Codemap

**Last Updated:** 2026-04-16
**Entry Points:** `gemini_evolve/cli.py`, `gemini_evolve/evolve.py`, `gemini_evolve/gepa_evolve.py`

## Architecture

```text
CLI command
  -> EvolutionConfig.from_env()
  -> discover/load target
  -> build eval dataset
       synthetic: SyntheticDatasetBuilder
       session:   GeminiSessionMiner
       golden:    GoldenDatasetLoader
  -> choose engine
       ga:
         -> ConstraintValidator on baseline
         -> Mutator.generate_population()
         -> run_gemini_cli() for each simulated task
         -> fast_heuristic_score() or LLMJudge.score()
         -> select best variant / optional crossover
       gepa:
         -> GeminiCLILM worker + reflector
         -> dspy.GEPA compile()
         -> optional trace-informed reflection
  -> holdout compare vs baseline
  -> save baseline.md, evolved.md, metrics.json
  -> optional backup + overwrite target
```

## Key Modules

| Module | Purpose | Key Exports | Dependencies |
| --- | --- | --- | --- |
| `gemini_evolve/cli.py` | Public CLI surface | `main`, `evolve`, `evolve_all`, `discover`, `trigger` | `click`, `rich`, `EvolutionConfig` |
| `gemini_evolve/evolve.py` | Orchestrates one evolution run end to end | `EvolutionResult`, `discover_targets`, `evolve` | `dataset`, `mutator`, `fitness`, `constraints`, `session_miner` |
| `gemini_evolve/gepa_evolve.py` | GEPA-based optimizer that keeps the same result/report/apply contract | `evolve_with_gepa`, `_build_metric`, `_build_program` | `dspy`, `dspy_adapter`, `dataset`, `fitness` |
| `gemini_evolve/dspy_adapter.py` | Makes DSPy call the Gemini CLI instead of provider HTTP | `GeminiCLILM`, `CapturedTrace` | `cli_runner`, `dspy`, session files |
| `gemini_evolve/config.py` | Runtime defaults and env overrides | `EvolutionConfig`, `EVOLUTION_TARGETS` | `os`, `pathlib` |
| `gemini_evolve/dataset.py` | Builds and persists eval datasets | `EvalExample`, `EvalDataset`, `SyntheticDatasetBuilder`, `GoldenDatasetLoader` | `cli_runner`, `json_utils` |
| `gemini_evolve/mutator.py` | Produces variant instructions | `Mutator` | `cli_runner`, `ThreadPoolExecutor` |
| `gemini_evolve/fitness.py` | Scores outputs | `FitnessScore`, `LLMJudge`, `fast_heuristic_score` | `cli_runner`, `json_utils` |
| `gemini_evolve/constraints.py` | Enforces hard gates | `ConstraintValidator`, `ConstraintResult` | standard library only |
| `gemini_evolve/json_utils.py` | Parses JSON from noisy LLM output | `extract_json` | `json`, `re` |

## Data Flow

1. CLI command builds `EvolutionConfig` from env.
2. `discover_targets()` resolves artifact paths.
3. `load_target()` reads the source file and infers a target name.
4. `_build_dataset()` chooses synthetic, session, or golden eval input.
5. `--engine ga` uses `ConstraintValidator`, `Mutator`, and `_simulate_agent()`.
6. `--engine gepa` uses `GeminiCLILM` plus `dspy.GEPA`, optionally with captured CLI tool traces.
7. Both engines produce the same `EvolutionResult` shape.
8. `_save_result()` writes result artifacts under `output/<target>/<timestamp>/`.
9. `_apply_result()` optionally backs up the original file and overwrites it.

## Output Artifacts

| File | Purpose |
| --- | --- |
| `baseline.md` | Original artifact content |
| `evolved.md` | Best evolved candidate |
| `metrics.json` | Scores, sizes, elapsed time, threshold result |

## Constraints

| Gate | Source |
| --- | --- |
| Non-empty | `ConstraintValidator._check_non_empty()` |
| Size limit | `ConstraintValidator._check_size()` |
| Growth limit | `ConstraintValidator._check_growth()` |
| Min improvement | `_apply_result()` compares against `config.min_improvement_pct` |
| Actual change | `_apply_result()` rejects identical content |

## Notes

- `gemini_evolve/evolve.py` is the orchestration center and the largest file in the repo.
- Session evaluation uses user prompts only, not assistant responses.
- Secret-looking session files are skipped wholesale before extraction.
- The DSPy path is optional and requires the `dspy` extra from `pyproject.toml`.
- `GeminiCLILM` runs in an isolated cwd by default so stray local `GEMINI.md` files do not contaminate evaluation.

## Related Areas

- [Triggers](triggers.md)
- [Integrations](integrations.md)
