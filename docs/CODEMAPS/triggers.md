# Trigger Codemap

**Last Updated:** 2026-04-16
**Entry Points:** `gemini_evolve/cli.py`, `gemini_evolve/triggers/*.py`

## Architecture

```text
trigger watch
  -> watchdog Observer
  -> debounce file events in ~/.gemini/tmp
  -> evolve() / evolve-all later

trigger cron-install
  -> generate launchd plist
  -> write ~/Library/LaunchAgents/com.gemini-evolve.scheduled.plist
  -> launchctl load

trigger hook-install
  -> append managed block to .git/hooks/post-commit
  -> on matching commit, run python -m gemini_evolve.cli evolve-all --type instructions &
```

## Key Modules

| Module | Purpose | Key Exports | Dependencies |
| --- | --- | --- | --- |
| `gemini_evolve/triggers/watcher.py` | Watch session files and debounce runs | `SessionCompleteHandler`, `start_watcher`, `run_watcher_blocking` | `watchdog`, `threading`, `time` |
| `gemini_evolve/triggers/cron.py` | Install/remove/check launchd job | `generate_plist`, `install_cron`, `uninstall_cron`, `status` | `plistlib`, `subprocess`, `launchctl` |
| `gemini_evolve/triggers/hook.py` | Install/remove git hook block | `install_hook`, `uninstall_hook` | `pathlib`, shell script text |

## Data Flow

### Watcher

1. CLI `trigger watch` passes debounce/type/apply options.
2. `start_watcher()` watches `~/.gemini/tmp` by default.
3. File create/modify events restart a timer.
4. When quiet, callback discovers targets and runs `evolve()` per target.

### Cron

1. CLI `trigger cron-install` chooses interval and target type.
2. `generate_plist()` builds `ProgramArguments` for `python -m gemini_evolve.cli evolve-all`.
3. `install_cron()` unloads existing plist, writes the new one, then loads it.
4. Logs go to `~/.gemini/evolve.log` and `~/.gemini/evolve-error.log`.

### Hook

1. CLI `trigger hook-install [repo]` finds `.git/hooks/post-commit`.
2. Managed block is appended unless already present.
3. Hook diff-checks `HEAD~1..HEAD` for `GEMINI.md` or `.gemini/`.
4. Matching commits spawn background `python3 -m gemini_evolve.cli evolve-all --type instructions`.

## Operational Notes

- Watch mode is foreground until interrupted.
- Cron is macOS-only in its current implementation.
- Hook install/remove is idempotent across repeated runs.
- Hook removal deletes the file only when the managed block was the only content left.

## Related Areas

- [Core Loop](core.md)
- [Integrations](integrations.md)
- [Runbook](../RUNBOOK.md)
