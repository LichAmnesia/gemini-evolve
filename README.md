# gemini-evolve

English | [简体中文](README.zh.md)

`gemini-evolve` improves Gemini CLI instruction artifacts by mutating candidates with Gemini CLI itself, scoring them against evaluation tasks, and only applying changes when hard gates pass.

- No direct Gemini SDK/API usage.
- All model calls go through `gemini -p ... -o json`.
- Docs: [Architecture](docs/CODEMAPS/INDEX.md), [Contrib](docs/CONTRIB.md), [Runbook](docs/RUNBOOK.md)

## Install

```bash
cd ~/ws/gemini-evolve
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"

./.venv/bin/gemini-evolve --version
gemini --version
```

If the venv is activated, drop the `./.venv/bin/` prefix.

To use the optional GEPA/DSPy engine:

```bash
./.venv/bin/pip install -e ".[dev,dspy]"
```

## Quickstart

1. Pick a target.

```bash
mkdir -p ~/.gemini
test -f ~/.gemini/GEMINI.md || printf '# Gemini Instructions\n' > ~/.gemini/GEMINI.md

./.venv/bin/gemini-evolve discover --type instructions
```

2. Validate constraints only.

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run
```

3. Run a small review pass.

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md -g 2 -p 2
```

4. Inspect artifacts.

```bash
find output -maxdepth 3 -type f | sort
cat output/global/$(ls -t output/global | head -1)/metrics.json
```

5. Apply only after you trust the loop.

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --apply
```

When `--apply` succeeds, the original file is backed up as `GEMINI.md.<UTC timestamp>.bak` before overwrite.

Optional GEPA pass:

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --engine gepa --capture-trace --gepa-budget light
```

## What Gets Evolved

| Target | Path pattern | Scope |
| --- | --- | --- |
| Global instructions | `~/.gemini/GEMINI.md` | All Gemini CLI sessions |
| Project instructions | `<project>/.gemini/GEMINI.md` | One project |
| Commands | `~/.gemini/commands/*.toml` | Custom slash commands |
| Skills | `~/.gemini/skills/**/*.md` | Skill definitions |

Project-level instruction discovery scans `~/ws`, `~/projects`, and `~/code` by default. Override with `GEMINI_EVOLVE_PROJECT_PATHS=/path/a:/path/b`.

## Evolution Loop

```text
target file
  -> build eval dataset
  -> validate baseline constraints
  -> mutate N variants via gemini CLI
  -> evaluate variants in sandbox/plan mode
  -> tournament select + optional crossover
  -> holdout compare vs baseline
  -> save output/<target>/<timestamp>/
  -> optionally apply back to source file
```

Real entry points:

- [gemini_evolve/cli.py](gemini_evolve/cli.py)
- [gemini_evolve/evolve.py](gemini_evolve/evolve.py)
- [gemini_evolve/gepa_evolve.py](gemini_evolve/gepa_evolve.py)
- [gemini_evolve/dspy_adapter.py](gemini_evolve/dspy_adapter.py)
- [gemini_evolve/cli_runner.py](gemini_evolve/cli_runner.py)

## Evaluation Sources

| Source | Flag | Source of truth |
| --- | --- | --- |
| Synthetic | `--eval-source synthetic` | Gemini-generated test scenarios from the current instructions |
| Session | `--eval-source session` | `~/.gemini/tmp/*/chats/session-*.json` user messages |
| Golden | `--eval-source golden --eval-dataset data.jsonl` | Hand-curated JSONL dataset |

Session mining skips messages that look like secrets or credentials.

## Outputs And Gates

Each run writes:

- `output/<target_name>/<UTC timestamp>/baseline.md`
- `output/<target_name>/<UTC timestamp>/evolved.md`
- `output/<target_name>/<UTC timestamp>/metrics.json`

`--apply` writes back only when all of these are true:

1. Content is non-empty.
2. Size stays under the per-target cap.
3. Growth stays within the configured growth cap.
4. Holdout improvement meets `min_improvement_pct` (default `2.0`).
5. Evolved content actually differs from baseline.

Current size caps:

- Instructions: `15KB`
- Skills: `15KB`
- Commands: `5KB`

## Trigger Automation

Watch for completed Gemini sessions:

```bash
./.venv/bin/gemini-evolve trigger watch --apply
```

Install a launchd job on macOS:

```bash
./.venv/bin/gemini-evolve trigger cron-install --interval 12 --apply
./.venv/bin/gemini-evolve trigger cron-status
./.venv/bin/gemini-evolve trigger cron-remove
```

Install a git post-commit hook:

```bash
./.venv/bin/gemini-evolve trigger hook-install .
./.venv/bin/gemini-evolve trigger hook-remove .
```

The hook triggers when committed files match `GEMINI.md` or `.gemini/`.

## Configuration

Environment variables read by the code:

| Variable | Default | Used by |
| --- | --- | --- |
| `GEMINI_EVOLVE_HOME` | `~/.gemini` | Base Gemini home for targets and session mining |
| `GEMINI_EVOLVE_MUTATOR_MODEL` | `gemini-3-flash-preview` | Variant generation |
| `GEMINI_EVOLVE_JUDGE_MODEL` | `gemini-3.1-pro-preview` | LLM judge scoring |
| `GEMINI_EVOLVE_POPULATION` | `4` | Population size |
| `GEMINI_EVOLVE_GENERATIONS` | `5` | Number of generations |
| `GEMINI_EVOLVE_OUTPUT` | `output` | Result directory |
| `GEMINI_EVOLVE_PROJECT_PATHS` | `~/ws:~/projects:~/code` | Project search roots for `.gemini/GEMINI.md` |

## CLI Surface

```text
gemini-evolve discover --type instructions|commands|skills
gemini-evolve evolve TARGET [--dry-run] [--apply] [-g N] [-p N] [--engine ga|gepa]
                     [--capture-trace] [--gepa-budget light|medium|heavy]
                     [--reflection-model MODEL]
gemini-evolve evolve-all --type instructions|commands|skills [--apply]
gemini-evolve trigger watch [--dir PATH] [--debounce FLOAT] [--type TYPE] [--apply]
gemini-evolve trigger cron-install [--interval N] [--type TYPE] [--apply]
gemini-evolve trigger cron-status
gemini-evolve trigger cron-remove
gemini-evolve trigger hook-install [REPO]
gemini-evolve trigger hook-remove [REPO]
```

Runtime detail: agent simulations call `gemini -p ... -o json --sandbox --approval-mode plan`, then parse the first JSON blob from stdout so MCP warnings do not break evaluation.

Engine detail:

- `ga` is the built-in tournament-style genetic loop in `gemini_evolve/evolve.py`.
- `gepa` routes optimization through DSPy GEPA in `gemini_evolve/gepa_evolve.py`.
- `evolve-all` currently uses the GA path only.

## Development

```bash
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m gemini_evolve.cli --help
./.venv/bin/pytest -q
```

Source tree:

```text
gemini_evolve/
  cli.py              Click CLI entry point
  evolve.py           Core loop, result saving, apply logic
  gepa_evolve.py      Optional DSPy GEPA engine
  dspy_adapter.py     DSPy LM adapter backed by the gemini CLI
  cli_runner.py       Non-interactive gemini CLI subprocess wrapper
  dataset.py          Synthetic and golden dataset handling
  mutator.py          Mutation and crossover prompts
  fitness.py          Heuristic and LLM-judge scoring
  constraints.py      Non-empty, size, growth gates
  session_miner.py    Real-session dataset extraction with secret filtering
  json_utils.py       JSON extraction from messy LLM output
  triggers/           watch, cron, hook automation
tests/                Unit tests for parsing, constraints, hooks, datasets, apply
```

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LichAmnesia/gemini-evolve&type=Date)](https://www.star-history.com/#LichAmnesia/gemini-evolve&Date)
