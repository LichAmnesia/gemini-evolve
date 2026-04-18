# Contributing

**Last Updated:** 2026-04-16

## Setup

```bash
cd ~/ws/gemini-evolve
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

Prereqs outside the repo:

- `gemini` CLI installed and authenticated
- macOS only for `trigger cron-*`
- `dspy` ships with the default deps; needed for the default `gepa` engine and tests that touch `dspy_adapter.py`

## Repo Layout

| Path | Purpose |
| --- | --- |
| `gemini_evolve/cli.py` | Click CLI commands |
| `gemini_evolve/evolve.py` | Main evolution orchestration |
| `gemini_evolve/gepa_evolve.py` | Default DSPy GEPA evolution path |
| `gemini_evolve/dspy_adapter.py` | DSPy LM adapter backed by `gemini` CLI |
| `gemini_evolve/triggers/` | Watch, cron, hook automation |
| `tests/` | Unit tests |
| `output/` | Local run artifacts |
| `docs/` | Architecture and operator docs |

## Common Dev Commands

```bash
./.venv/bin/python -m gemini_evolve.cli --help
./.venv/bin/python -m gemini_evolve.cli evolve --help
./.venv/bin/pytest -q
```

DSPy and GEPA are installed as part of the default dependency set above.

## Change Rules

- Keep docs aligned with code paths and CLI help text.
- When changing trigger behavior, update [docs/CODEMAPS/triggers.md](CODEMAPS/triggers.md) and [docs/RUNBOOK.md](RUNBOOK.md).
- When changing target discovery, config, or scoring, update [docs/CODEMAPS/core.md](CODEMAPS/core.md) and `README.md`.
- Add or extend tests when behavior changes.

## Test Areas

Current tests cover:

- JSON parsing from Gemini CLI output
- dataset serialization
- scoring math
- constraint gates
- session mining + secret filtering
- hook install/remove
- apply backup behavior
- DSPy adapter behavior
- GEPA smoke coverage

## Packaging Notes

- Console script: `gemini-evolve = gemini_evolve.cli:main`
- Build backend: `setuptools.build_meta`
- Supported Python: `>=3.11`

## Docs To Read First

- [README.md](../README.md)
- [docs/CODEMAPS/INDEX.md](CODEMAPS/INDEX.md)
- [docs/RUNBOOK.md](RUNBOOK.md)
