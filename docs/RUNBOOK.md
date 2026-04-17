# Runbook

**Last Updated:** 2026-04-16

## Verify Environment

```bash
./.venv/bin/gemini-evolve --version
gemini --version
```

If `gemini-evolve` is missing, reinstall editable deps:

```bash
./.venv/bin/pip install -e ".[dev]"
```

If you want the GEPA engine:

```bash
./.venv/bin/pip install -e ".[dev,dspy]"
```

## Run A Safe Check

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run
```

Expected outcome:

- non-empty gate printed
- size gate printed
- no writes to the target file

## Run A Small Evolution Pass

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md -g 2 -p 2
```

Inspect the latest artifacts:

```bash
find output -maxdepth 3 -type f | sort
cat output/global/$(ls -t output/global | head -1)/metrics.json
```

## Apply A Result

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --apply
```

Successful apply side effects:

- target file overwritten with evolved content
- backup created next to the target as `GEMINI.md.<UTC timestamp>.bak`

Rollback:

```bash
cp ~/.gemini/GEMINI.md.<timestamp>.bak ~/.gemini/GEMINI.md
```

## GEPA Mode

Run:

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --engine gepa --capture-trace --gepa-budget light
```

Notes:

- requires the `dspy` extra
- only `evolve` exposes `--engine gepa`; `evolve-all` stays on the GA path
- `--capture-trace` re-reads Gemini session files and feeds tool traces into reflection

## Session Watch Mode

```bash
./.venv/bin/gemini-evolve trigger watch --apply
```

Behavior:

- watches `~/.gemini/tmp` by default
- debounces changes
- evolves discovered targets when session files go quiet

## Scheduled Mode

Install:

```bash
./.venv/bin/gemini-evolve trigger cron-install --interval 12 --apply
```

Check:

```bash
./.venv/bin/gemini-evolve trigger cron-status
```

Remove:

```bash
./.venv/bin/gemini-evolve trigger cron-remove
```

Logs:

- `~/.gemini/evolve.log`
- `~/.gemini/evolve-error.log`

## Git Hook Mode

Install in a repo:

```bash
cd /path/to/repo
/Users/lich/ws/gemini-evolve/.venv/bin/gemini-evolve trigger hook-install .
```

Remove:

```bash
/Users/lich/ws/gemini-evolve/.venv/bin/gemini-evolve trigger hook-remove .
```

The managed hook block only reacts to commits that touch `GEMINI.md` or `.gemini/`.

## Common Failures

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| `gemini CLI not found on PATH` | Gemini CLI missing | install/auth `gemini`, then rerun |
| `No instructions targets found` | no `~/.gemini/GEMINI.md` or project `.gemini/GEMINI.md` | create target or set `GEMINI_EVOLVE_PROJECT_PATHS` |
| Empty synthetic/session dataset | CLI failed, no sessions, or filtered sessions | try `--eval-source golden` or inspect `~/.gemini/tmp` |
| Improvement below threshold | result did not clear `min_improvement_pct` | inspect `metrics.json`; rerun with different eval source or config |
| `launchctl` errors | non-macOS environment or launchd issue | use `trigger watch` or remove cron job |
| Hook install fails with `Not a git repository` | wrong working dir | rerun inside a repo root |

## Verification

Repo-local verification command:

```bash
./.venv/bin/pytest -q
```
