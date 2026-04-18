# Integrations Codemap

**Last Updated:** 2026-04-16
**Entry Points:** `gemini_evolve/cli_runner.py`, `gemini_evolve/dspy_adapter.py`, `gemini_evolve/session_miner.py`, `gemini_evolve/triggers/*.py`

## External Boundaries

| Integration | Where Used | Purpose | Notes |
| --- | --- | --- | --- |
| `gemini` CLI binary | `cli_runner.py`, indirectly throughout the system | Mutation, dataset generation, judging, simulation | Must be on `PATH`; called with `-p`, `-o json`, `--approval-mode plan` (plan already blocks exec, so `--sandbox` is off by default for speed) |
| DSPy / `dspy.GEPA` | `dspy_adapter.py`, `gepa_evolve.py` | Reflective optimizer engine | Part of default install |
| `~/.gemini` home | `config.py`, `evolve.py`, `session_miner.py`, trigger logs | Target discovery, session mining, logs | Override root with `GEMINI_EVOLVE_HOME` |
| `~/.gemini/tmp/*/chats/session-*.json` | `session_miner.py` | Session-source evaluation data | Secret-containing sessions are skipped |
| `launchctl` / launchd | `triggers/cron.py` | Scheduled runs on macOS | Writes to `~/Library/LaunchAgents` |
| Git hook filesystem | `triggers/hook.py` | Post-commit automation | Appends/removes a managed block in `.git/hooks/post-commit` |
| `watchdog` observer | `triggers/watcher.py` | Session watch automation | Recursive watch over Gemini tmp dir |
| Local filesystem outputs | `evolve.py` | Persist run artifacts and backups | Writes `output/...` and backup files near targets |

## Gemini CLI Request Path

```text
Mutator / SyntheticDatasetBuilder / LLMJudge / _simulate_agent / GeminiCLILM
  -> run_gemini_cli()
       -> subprocess.run(["gemini", "-p", prompt, "-o", "json", ...])
       -> tolerate stdout prefix noise
       -> return parsed response + token stats
```

## Failure Modes

| Boundary | Typical Failure | Current Handling |
| --- | --- | --- |
| `gemini` missing | binary not found on `PATH` | returns `CLIResult(... exit_code=127)` or empty eval result |
| `dspy` missing | GEPA requested without extra installed | raises import error from `gepa_evolve._require_dspy()` |
| CLI timeout | slow model/tool run | returns timeout error; skipped in scoring |
| Non-JSON stdout | warnings before JSON | parser scans for first JSON object |
| Bad session file | invalid JSON / missing keys | file ignored |
| Secret leakage risk | credentials in session files | regex filters skip content |
| launchctl load failure | bad plist or OS limitation | subprocess exception bubbles to caller |
| Hook install in non-repo dir | missing `.git/hooks` | raises `FileNotFoundError` |

## Dependency Snapshot

Runtime dependencies from `pyproject.toml`:

- `click>=8.0`
- `rich>=13.0`
- `watchdog>=4.0`

Optional extra:

- `dspy>=2.6`

Dev dependency:

- `pytest>=8.0`

## Related Areas

- [Core Loop](core.md)
- [Triggers](triggers.md)
