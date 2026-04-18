# Runbook

**Last Updated:** 2026-04-18

Operator-facing guide. If you just want to try it once, start with [QUICKSTART.md](QUICKSTART.md) or the README. This page is for "I want to actually operate this thing day to day."

All commands below assume you've already done:

```bash
cd /path/to/gemini-evolve
python3 -m venv .venv
./.venv/bin/pip install -e .
# (contributors: use `pip install -e ".[dev]"` — extras only add pytest)
```

> You can skip `./.venv/bin/` if you `source .venv/bin/activate` first. The examples keep the prefix so they're copy-paste safe from any directory.

---

## 0. Verify Environment

```bash
./.venv/bin/gemini-evolve --version    # expect: "gemini-evolve, version 0.1.0"
gemini --version                        # expect: a version string, NOT "command not found"
gemini -p "hi" -o json                  # expect: a JSON object in stdout
```

If `gemini-evolve` is missing:

```bash
./.venv/bin/pip install -e .
```

The GEPA/DSPy engine ships with the default dependency set — no extras needed. (`[dev]` only adds `pytest` for contributors.)

---

## 1. Run A Safe Check (dry-run)

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run
```

Expected output:

- A line per constraint: `PASS non_empty`, `PASS size`.
- `Dry run — skipping optimization.`
- No changes to the target file, no `output/` folder touched.

> **Heads up:** `--dry-run` skips the evolution loop, but it still builds the eval
> dataset first. With the default `--eval-source synthetic`, that means **one
> real `gemini` call** (~5-10s, small quota hit) to generate tasks. If you want
> a zero-cost dry-run — e.g. on a fresh machine where you just want to verify
> the gates — pass a tiny golden JSONL instead:
>
> ```bash
> echo '{"task_input":"hi","expected_behavior":"respond briefly"}' > /tmp/stub.jsonl
> ./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run \
>     --eval-source golden --eval-dataset /tmp/stub.jsonl
> ```
>
> With that, no `gemini` call happens at all — the JSONL is read straight off disk.

Dry-run is the safest thing you can do before a real evolution pass; just know
that "safest" still means one small Gemini call unless you opt into the golden
stub above.

---

## 2. Run A Small Evolution Pass

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md -g 2 -p 2
```

`-g 2 -p 2` means 2 generations, 2 variants per generation — a cheap smoke test. Defaults are `-g 5 -p 4`.

Inspect artifacts:

```bash
find output -maxdepth 3 -type f | sort
cat "output/global/$(ls -t output/global | head -1)/metrics.json"
```

Every run writes:

- `output/<name>/<UTC timestamp>/baseline.md` — what was there before
- `output/<name>/<UTC timestamp>/evolved.md` — what the loop produced
- `output/<name>/<UTC timestamp>/metrics.json` — scores, size, improvement %, gate results

You can `diff baseline.md evolved.md` to eyeball the change before you trust `--apply`.

---

## 3. Apply A Result

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --apply
```

Successful apply side effects:

- Target file overwritten with evolved content.
- Backup created next to the target: `GEMINI.md.<UTC timestamp>.bak`.
- Console prints `Applied: <path>` with the improvement %.

`--apply` will **refuse to write** if any hard gate fails:

1. Content is non-empty.
2. Size stays under the per-target cap.
3. Growth stays within `max_growth_pct` (default 20%).
4. Holdout improvement ≥ `min_improvement_pct` (default 2%).
5. Evolved content actually differs from baseline.

That's the whole point — you can run `--apply` automatically and never eat a regression.

### Rollback

```bash
# list backups
ls -t ~/.gemini/GEMINI.md.*.bak | head -5

# restore the most recent one
cp "$(ls -t ~/.gemini/GEMINI.md.*.bak | head -1)" ~/.gemini/GEMINI.md
```

---

## 4. Engines

GEPA is the default engine.

Light run (cheap, good default):

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --gepa-budget light
```

Enable trace reflection (GEPA reads Gemini's tool-call traces and reflects on them):

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --capture-trace --gepa-budget light
```

Fall back to the built-in tournament GA (no DSPy overhead):

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --engine ga -g 2 -p 2
```

Notes:

- `dspy` is in the default dependency set. No extra install needed.
- Both `evolve` and `evolve-all` accept `--engine gepa|ga`.
- `--capture-trace` re-reads session files under `~/.gemini/tmp` and feeds Gemini tool traces into GEPA reflection.

---

## 5. Session Watch Mode

```bash
./.venv/bin/gemini-evolve trigger watch --apply
```

Behavior:

- Watches `~/.gemini/tmp` by default.
- Debounces changes (default 60s).
- When session files go quiet, evolves the discovered targets and (if `--apply`) writes back.

Cross-platform: works on macOS and Linux.

Stop it with Ctrl-C.

---

## 6. Scheduled Mode (macOS only)

Install:

```bash
./.venv/bin/gemini-evolve trigger cron-install --interval 12 --apply
```

Check status:

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

On Linux, use `trigger watch` or your own cron / systemd unit pointing at `./.venv/bin/gemini-evolve evolve ... --apply`.

---

## 7. Git Hook Mode

Install in a repo:

```bash
cd /path/to/repo
/path/to/gemini-evolve/.venv/bin/gemini-evolve trigger hook-install .
```

Remove:

```bash
/path/to/gemini-evolve/.venv/bin/gemini-evolve trigger hook-remove .
```

The managed hook block only reacts to commits that touch `GEMINI.md` or `.gemini/`. Other commits are untouched.

---

## 8. Common Failures

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `gemini CLI not found on PATH` | Gemini CLI missing or not in this shell | Install / auth `gemini`; verify `which gemini` in the same terminal |
| `No instructions targets found` | No `~/.gemini/GEMINI.md` and no project `.gemini/GEMINI.md` under scan roots | Create a target, or `export GEMINI_EVOLVE_PROJECT_PATHS=/abs/path` |
| Empty synthetic/session dataset | CLI call failed, no sessions, or all sessions filtered out | Try `--eval-source golden`, or use Gemini CLI a few times and retry |
| `Improvement below threshold` | Evolved version did not clear `min_improvement_pct` on holdout | **Not a bug** — gate worked. Inspect `metrics.json`; rerun with different eval source or more generations |
| `launchctl` errors on `cron-install` | Not macOS (no launchd) | Use `trigger watch` or plain cron/systemd |
| `Not a git repository` on `hook-install` | Wrong cwd | `cd` into the repo root and retry |
| `--apply` silently did nothing | One of the 5 hard gates failed | Check the final console log; the last message states *which* gate blocked write-back |

---

## 9. Verification

Before handing off changes:

```bash
./.venv/bin/pytest -q
```

If you hacked on CLI surface, also smoke-test the actual help:

```bash
./.venv/bin/python -m gemini_evolve.cli --help
./.venv/bin/python -m gemini_evolve.cli evolve --help
```
