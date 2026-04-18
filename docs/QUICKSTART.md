# Quickstart — paste-and-run

This file has exactly one job: **let you go from zero to "I ran it and saw output" in under 5 minutes, by pasting a single block.**

> This walkthrough assumes your target is `~/.gemini/GEMINI.md` (aka the *global* target — that's where the `output/global/...` paths and inspect commands below come from). Evolving a per-project `.gemini/GEMINI.md` works the same way, but the output folder will be the project's basename, so adjust the last `ls` accordingly.
>
> It also assumes your shell's current directory is the cloned `gemini-evolve/` (what step 1 leaves you in). If you prefer, `source .venv/bin/activate` once and drop the `./.venv/bin/` prefix everywhere.

## Prerequisites (check in 30 seconds)

```bash
python3 --version                 # must print 3.11 or higher
gemini --version                  # must print a version, NOT "command not found"
gemini -p "say hi in one word" -o json   # must print a JSON object with a response
                                         # NOTE: real gemini call (~5s, tiny quota hit)
```

If `gemini` isn't there yet: install [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli), then authenticate. There is **no `gemini auth` subcommand** — pick one:

- **First-time / Google account:** run `gemini` with no arguments; it opens an OAuth browser flow and writes credentials to `~/.gemini/oauth_creds.json`.
- **Non-interactive / CI / AI Studio key:** `export GEMINI_API_KEY=<your-key>`.

gemini-evolve only ever shells out to `gemini`, so whichever path works for the CLI works here.

## One-shot install + smoke test

Paste the whole block below. It's idempotent-ish: rerunning is safe.

```bash
# clone + venv + install
git clone https://github.com/LichAmnesia/gemini-evolve.git
cd gemini-evolve
python3 -m venv .venv
./.venv/bin/pip install -e .

# verify
./.venv/bin/gemini-evolve --version
gemini --version

# make sure a target exists (harmless stub if you don't have one yet)
mkdir -p ~/.gemini
test -f ~/.gemini/GEMINI.md || printf '# Gemini Instructions\n- be concise\n- use bullets\n' > ~/.gemini/GEMINI.md

# dry-run — validates constraint gates, writes nothing to the target
# NOTE: with the default --eval-source synthetic, --dry-run still makes ONE real
# gemini call to build the eval dataset. For a truly zero-cost dry-run, pass a
# tiny golden JSONL instead:
#   echo '{"task_input":"hi","expected_behavior":"respond briefly"}' > /tmp/stub.jsonl
#   ./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run \
#       --eval-source golden --eval-dataset /tmp/stub.jsonl
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run

# real small run (GEPA, light budget; usually ~15-30 gemini calls, a few minutes)
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --gepa-budget light

# inspect what it wrote (this line assumes TARGET is ~/.gemini/GEMINI.md)
ls -t output/global | head -1 | xargs -I {} ls "output/global/{}"
```

## What you should see

1. `pip install` ends with `Successfully installed gemini-evolve-0.1.0 ...`
2. `gemini-evolve --version` prints `gemini-evolve, version 0.1.0`.
3. `--dry-run` prints `PASS non_empty`, `PASS size`, then `Dry run — skipping optimization.`
4. The real run prints GEPA iteration lines, finishes with an `Evolution Results` table, and creates:

```
output/global/<UTC timestamp>/
  baseline.md
  evolved.md
  metrics.json
```

5. `cat` the latest `metrics.json` — look for `improvement_pct`, `meets_min_improvement`, `constraints_passed`.

## Apply it (optional)

If you like `evolved.md`:

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --apply
```

Your original moves to `~/.gemini/GEMINI.md.<UTC timestamp>.bak`. Rollback is just `cp` back.

`--apply` will silently refuse to write if any hard gate fails (size cap, growth cap, < 2% holdout improvement, unchanged content). That's the point — you can automate it without eating regressions.

## Next steps

- Full operator guide: [RUNBOOK.md](RUNBOOK.md)
- FAQ / troubleshooting: [FAQ.md](FAQ.md)
- More before/after examples (commands, skills, session-mined eval): [EXAMPLES.md](EXAMPLES.md)
- Why not just ask Gemini directly? See the "Why not just X?" section in the [README](../README.md).
