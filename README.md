# gemini-evolve

English | [简体中文](README.zh.md)

> **Stop hand-tuning your `GEMINI.md`. Let Gemini tune it for you — with guardrails.**

If you use the [Gemini CLI](https://github.com/google-gemini/gemini-cli), you have a `GEMINI.md` somewhere. Over time it gets messy: vague rules, duplicated advice, things you meant to clean up. `gemini-evolve` runs a tiny genetic loop that **mutates your instructions, grades each variant by actually running Gemini CLI on real tasks, and only writes back when a holdout (unseen) test set says it got better.**

### Before → after (example output, real numbers will vary)

Your baseline `~/.gemini/GEMINI.md`:

```markdown
# My Gemini Instructions
- try to be concise
- generally avoid long explanations
- if possible, use bullet points
- prefer to keep answers short
```

After one `gemini-evolve evolve --apply` run, the `sharpen_constraints` + `condense` mutations typically produce something like:

```markdown
# My Gemini Instructions

## Response Style
- Answer in <=3 sentences by default; use bullets for lists of 3+ items.
- No preamble ("Sure!", "Great question!"). Start with the answer.
- Expand only when the user asks "explain" / "why" / "walk me through".
```

Holdout judge score went up, size cap not exceeded, so `--apply` wrote the new file and kept `GEMINI.md.<timestamp>.bak` as your escape hatch. If the holdout score had *not* improved by at least 2%, the loop would refuse to apply — no sneaky regressions.

### Why you might want this

- You've edited `GEMINI.md` by hand one too many times.
- You suspect it's bloated but don't want to break what works.
- You want *measured* improvements, not vibes.

---

## Prerequisites

| Requirement | How to check | Notes |
| --- | --- | --- |
| Python **3.11+** | `python3 --version` | 3.12 tested too |
| `gemini` CLI installed + logged in | `gemini --version` then `gemini -p "hi" -o json` | Install: [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli). OAuth (`gemini auth login`) or `GEMINI_API_KEY` env var both work. |
| macOS or Linux | — | `trigger cron-*` (launchd) is macOS-only. `trigger watch` and `trigger hook-*` work on both. |
| A `GEMINI.md` to evolve | `ls ~/.gemini/GEMINI.md` | If you don't have one, the Quickstart creates a stub. |

No Gemini SDK or API key handling inside this repo — **every model call shells out to your local `gemini` CLI** (`gemini -p ... -o json`). Whatever auth works for your CLI works here.

---

## 5-minute Quickstart

Full copy-paste session is in [docs/QUICKSTART.md](docs/QUICKSTART.md). Short version:

```bash
# 1. install (pick your own dir; 3.11+ required)
git clone https://github.com/LichAmnesia/gemini-evolve.git
cd gemini-evolve
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"

# 2. verify both CLIs are reachable
./.venv/bin/gemini-evolve --version    # expect: gemini-evolve 0.1.0
gemini --version                        # expect: a version string, not "command not found"

# 3. make sure a target exists
mkdir -p ~/.gemini
test -f ~/.gemini/GEMINI.md || printf '# Gemini Instructions\n- be concise\n- use bullets\n' > ~/.gemini/GEMINI.md

# 4. dry-run — validates gates, writes nothing
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run
# expect: "PASS non_empty", "PASS size", "Dry run — skipping optimization."

# 5. do a tiny real run — takes a few minutes
#    (default engine is GEPA; add --engine ga for the lighter tournament GA)
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --gepa-budget light
# expect: GEPA iterations printing, a final "Evolution Results" table,
#         and a new folder under ./output/<name>/<timestamp>/
```

When the table prints a green `Evolution improved ... by +X%`, inspect `output/<target>/<timestamp>/evolved.md` to decide if you like it. If yes, run again with `--apply`:

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --apply
```

On success, your original is backed up as `GEMINI.md.<UTC timestamp>.bak` next to the new file. Rollback = `cp` the backup back.

---

## Why not just X?

**"Why not just edit `GEMINI.md` by hand?"**
You can, and you should, for the stuff you *know* is wrong. `gemini-evolve` targets the stuff you *don't* know — like which phrasing of a rule actually changes Gemini's behavior. It A/B-tests variants against an eval set, so you get evidence instead of a guess.

**"Why not just ask Gemini: 'fix my GEMINI.md'?"**
That gives you one unvalidated rewrite. `gemini-evolve` generates several variants via distinct mutation strategies (`clarity`, `condense`, `sharpen_constraints`, ...), scores each one by actually running Gemini CLI on eval tasks, runs a holdout (never-seen) comparison against the baseline, and hard-gates the apply on size, growth, and min-improvement. Overfitting and prompt-bloat are caught before they hit your file.

**"How is this different from DSPy / GEPA / promptfoo?"**
- [DSPy](https://github.com/stanfordnlp/dspy) / [GEPA](https://github.com/gepa-ai/gepa) are general prompt-optimization frameworks. We **use GEPA as the default engine** — we're a thin Gemini-CLI-native front-end, not a replacement.
- promptfoo is a prompt-eval harness. It tells you which of *your* prompts wins. `gemini-evolve` actively *generates* candidates and closes the loop back into your `GEMINI.md`.
- Unique bit: everything runs through your local `gemini` CLI — same auth, same tools, same skills, same MCP servers as your real sessions. No separate API key to manage.

**Glossary (first-time terms):**
- **GEPA** = *Generative Evolutionary Prompt Adaptation* — a reflection-driven prompt optimizer, used here as the default engine. Opt out with `--engine ga` for the lighter built-in tournament GA.
- **DSPy** = Stanford's framework for programming with LMs; GEPA lives inside it.
- **Holdout** = a slice of eval examples the loop never trains on, used only for the final before/after score — catches overfitting.
- **Tournament selection** = pick the best of N variants per generation; the survivor is the parent of the next generation.
- **Hard gate** = an apply-blocking rule (non-empty, size cap, growth cap, min improvement %). Fail any → no write-back.

---

## What can it evolve?

| Target | Path pattern | Scope | Size cap |
| --- | --- | --- | --- |
| Global instructions | `~/.gemini/GEMINI.md` | All Gemini CLI sessions | 15KB |
| Project instructions | `<project>/.gemini/GEMINI.md` | One project | 15KB |
| Commands | `~/.gemini/commands/*.toml` | Custom slash commands | 5KB |
| Skills | `~/.gemini/skills/**/*.md` | Skill definitions | 15KB |

Project discovery scans `~/ws`, `~/projects`, `~/code` by default — override with `GEMINI_EVOLVE_PROJECT_PATHS=/path/a:/path/b`.

More concrete before/after examples (commands, skills, session-mined eval): [docs/EXAMPLES.md](docs/EXAMPLES.md).

---

## How the loop works

```text
target file
  -> build eval dataset  (synthetic | session-mined | golden JSONL)
  -> validate baseline gates  (non-empty, size)
  -> for each generation:
       mutate N variants in parallel via gemini CLI
       evaluate each variant in plan/sandbox mode
       tournament-select the best; optional crossover
  -> holdout compare evolved vs baseline  (never-seen examples)
  -> save output/<target>/<timestamp>/{baseline.md, evolved.md, metrics.json}
  -> optionally --apply and keep a .bak
```

Apply hard gates (all must pass, or no write-back):

1. Content is non-empty.
2. Size stays under the per-target cap (above).
3. Growth stays within `max_growth_pct` (default 20%).
4. Holdout improvement ≥ `min_improvement_pct` (default 2%).
5. Evolved content actually differs from baseline.

Real entry points: [gemini_evolve/cli.py](gemini_evolve/cli.py), [evolve.py](gemini_evolve/evolve.py), [gepa_evolve.py](gemini_evolve/gepa_evolve.py), [mutator.py](gemini_evolve/mutator.py), [fitness.py](gemini_evolve/fitness.py).

---

## Evaluation sources

| Source | Flag | Data | When to use |
| --- | --- | --- | --- |
| Synthetic | `--eval-source synthetic` *(default)* | Gemini generates tasks from your current instructions | First run; no eval data yet |
| Session | `--eval-source session` | Real user messages mined from `~/.gemini/tmp/*/chats/session-*.json` | You've used Gemini CLI a while; want your *actual* workflows to drive optimization |
| Golden | `--eval-source golden --eval-dataset data.jsonl` | Your own hand-curated JSONL | You know exactly what "good" looks like |

Session mining skips messages that look like secrets or credentials.

---

## Automation triggers

```bash
# watch sessions live; evolve when a session goes quiet
./.venv/bin/gemini-evolve trigger watch --apply

# macOS launchd (runs every N hours)
./.venv/bin/gemini-evolve trigger cron-install --interval 12 --apply
./.venv/bin/gemini-evolve trigger cron-status
./.venv/bin/gemini-evolve trigger cron-remove

# git post-commit hook — only fires on commits touching GEMINI.md / .gemini/
./.venv/bin/gemini-evolve trigger hook-install .
./.venv/bin/gemini-evolve trigger hook-remove .
```

Heads up: `cron-*` uses launchd so it's **macOS only**. `watch` and `hook-*` work on Linux too.

---

## Troubleshooting / FAQ

Full list in [docs/FAQ.md](docs/FAQ.md). Top hits:

| Symptom | Cause | Fix |
| --- | --- | --- |
| `gemini CLI not found on PATH` | `gemini` not installed or not in the same shell | Install Gemini CLI; `which gemini` must work in the same terminal where you run `gemini-evolve`. |
| `No instructions targets found` | No `~/.gemini/GEMINI.md` and no project `.gemini/GEMINI.md` under `~/ws`, `~/projects`, `~/code` | Create one, or set `GEMINI_EVOLVE_PROJECT_PATHS=/abs/path` and re-run `discover`. |
| Empty synthetic/session dataset | Gemini CLI call failed, no sessions, or sessions were all filtered out | Try `--eval-source golden --eval-dataset your.jsonl`, or run Gemini CLI a few times and retry `session`. |
| `Improvement below threshold` | Evolved version scored < `min_improvement_pct` on holdout | Not a bug — this is the loop refusing to apply a regression. Rerun with more generations / different `--eval-source`. |
| `launchctl` errors on `cron-install` | Not macOS (launchd missing) | Use `trigger watch` (cross-platform) or cron/systemd on your own. |
| `Not a git repository` on `hook-install` | Wrong cwd | `cd` into the repo root first. |

---

## CLI surface

```text
gemini-evolve discover --type instructions|commands|skills
gemini-evolve evolve TARGET [--dry-run] [--apply]
                     [-g GENERATIONS] [-p POPULATION]
                     [--eval-source synthetic|session|golden] [--eval-dataset FILE]
                     [--dataset-size N] [--llm-judge]
                     [--engine ga|gepa]
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

Engine detail:

- `gepa` (default) — DSPy + GEPA reflective loop in `gemini_evolve/gepa_evolve.py`. Uses reflection on captured traces, typically finds better variants per unit of compute.
- `ga` — built-in tournament GA in `gemini_evolve/evolve.py`. Lighter, no DSPy overhead; pass `--engine ga` to use it.
- `evolve-all` also accepts `--engine` and defaults to `gepa`.

Runtime: variant evaluation calls `gemini -p ... -o json --sandbox --approval-mode plan` and parses the first JSON blob from stdout, so MCP warnings don't break scoring.

---

## Configuration

Environment variables read by the code:

| Variable | Default | Used by |
| --- | --- | --- |
| `GEMINI_EVOLVE_HOME` | `~/.gemini` | Base Gemini home for targets and session mining |
| `GEMINI_EVOLVE_MUTATOR_MODEL` | `gemini-3-flash-preview` | Variant generation |
| `GEMINI_EVOLVE_JUDGE_MODEL` | `gemini-3.1-pro-preview` | LLM judge scoring |
| `GEMINI_EVOLVE_POPULATION` | `4` | Population size per generation |
| `GEMINI_EVOLVE_GENERATIONS` | `5` | Number of generations |
| `GEMINI_EVOLVE_OUTPUT` | `output` | Result directory |
| `GEMINI_EVOLVE_PROJECT_PATHS` | `~/ws:~/projects:~/code` | Project search roots for `.gemini/GEMINI.md` |

---

## Development

```bash
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m gemini_evolve.cli --help
./.venv/bin/pytest -q
```

Architecture and module inventory: [docs/CODEMAPS/INDEX.md](docs/CODEMAPS/INDEX.md). Operator guide: [docs/RUNBOOK.md](docs/RUNBOOK.md). Contributing: [docs/CONTRIB.md](docs/CONTRIB.md).

---

## License

MIT — see [LICENSE](LICENSE).

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LichAmnesia/gemini-evolve&type=Date)](https://www.star-history.com/#LichAmnesia/gemini-evolve&Date)
