# Examples — before / after

> All diffs below are **illustrative examples**, not benchmark numbers. Your mileage will vary with your baseline, eval source, and generation count. The "how to reproduce" blocks are real commands you can run yourself.

The point of this page is to show the *kind* of changes each mutation strategy tends to produce, so you know what to expect before you burn Gemini quota.

---

## Example 1 — vague bullets → sharp directives

**Mutation strategies that typically trigger this shape:** `sharpen_constraints`, `condense`.

Baseline `~/.gemini/GEMINI.md`:

```markdown
# My Gemini Instructions
- try to be concise
- generally avoid long explanations
- if possible, use bullet points
- prefer to keep answers short
```

Evolved:

```markdown
# My Gemini Instructions

## Response Style
- Answer in <=3 sentences by default; use bullets for lists of 3+ items.
- No preamble ("Sure!", "Great question!"). Start with the answer.
- Expand only when the user asks "explain" / "why" / "walk me through".
```

**Why the loop liked this:** the original was all hedges ("try to", "generally", "if possible"). After mutation, each rule is a crisp directive a model can verify per-turn. Holdout eval agrees: model outputs are shorter and more on-task.

**How to reproduce roughly:**

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md --gepa-budget light
diff "$(ls -t output/global | head -1 | xargs -I {} echo output/global/{}/baseline.md)" \
     "$(ls -t output/global | head -1 | xargs -I {} echo output/global/{}/evolved.md)"
```

---

## Example 2 — bloated command → focused command

**Mutation strategies that typically trigger this shape:** `condense`, `restructure`.

Baseline `~/.gemini/commands/review.toml`:

```toml
description = "Review code and give me feedback, be careful to be thorough and check for bugs"
prompt = """
Please carefully review the following code and give me feedback.
Look at the code thoroughly. Check for:
- bugs, issues, problems
- style problems, things that could be more consistent
- performance things
- security things
- anything else you think I should know about
Be thorough but also be concise where you can.
"""
```

Evolved (after the `restructure` + `sharpen_constraints` pass):

```toml
description = "Review code with bug/perf/security focus"
prompt = """
Review the code below in this order:
1. Correctness bugs (wrong behavior, crashes, off-by-one)
2. Security issues (input trust, secrets, injection)
3. Performance hotspots (N+1, hot-loop allocations)
4. Style/consistency — only if they'd trip another reader

For each finding, include: file:line, one-sentence issue, one-sentence fix.
Skip categories with zero findings. No "overall looks good" summary.
"""
```

**Why the loop liked this:** the baseline mixed priority (bug first or style first?) and gave no output format. Evolved version prioritizes explicitly and prescribes a structured finding shape — easier for the judge to score, and easier for you to scan.

**Reproduce:**

```bash
./.venv/bin/gemini-evolve evolve ~/.gemini/commands/review.toml --gepa-budget light
```

---

## Example 3 — session-mined eval beats synthetic

**When you'd use this:** you've used Gemini CLI for a while, so your real workflow is richer than anything the synthetic dataset would generate.

```bash
# use your real messages as the eval set
./.venv/bin/gemini-evolve evolve ~/.gemini/GEMINI.md \
    --eval-source session \
    --gepa-budget light
```

The miner pulls user messages from `~/.gemini/tmp/*/chats/session-*.json`, filters out anything that looks like a secret or credential, and splits them into train/val/holdout the same way synthetic does. The effect: mutations are scored against *your* workflows (refactors, debugging, writing changelogs, whatever), not Gemini's guess at what you probably do.

If your session pool is thin (fewer than ~10 messages post-filter), the mined dataset will be empty and the loop will print a warning. In that case, fall back to synthetic for now.

---

## Example 4 — project-local instructions

Per-project `.gemini/GEMINI.md` files get evolved independently. Discovery scans `~/ws`, `~/projects`, `~/code` by default:

```bash
./.venv/bin/gemini-evolve discover --type instructions
# -> lists every target it would consider, with size
```

To evolve just one project:

```bash
./.venv/bin/gemini-evolve evolve /path/to/project/.gemini/GEMINI.md --gepa-budget light
```

To evolve all of them at once (GEPA engine, auto-apply on pass):

```bash
./.venv/bin/gemini-evolve evolve-all --type instructions --apply
```

Each target gets its own subfolder under `output/` (the folder name is the project directory's basename, or `global` for `~/.gemini/GEMINI.md`).

---

## What to look for in `metrics.json`

After any real run, the latest run folder has a `metrics.json` like the block
below. **The numbers are illustrative, not from a real benchmark** — your own
run will produce different scores depending on baseline, eval source, and
mutation luck.

```json
{
  "target_name": "global",
  "baseline_score": 0.68,
  "evolved_score": 0.74,
  "improvement_pct": 8.8,
  "baseline_size": 421,
  "evolved_size": 498,
  "meets_min_improvement": true,
  "min_improvement_pct": 2.0,
  "constraints_passed": true
}
```

Three fields do 90% of the work:

- `improvement_pct` — holdout score delta. Positive and ≥ `min_improvement_pct` is the bar `--apply` needs.
- `meets_min_improvement` — boolean shortcut for the same check.
- `constraints_passed` — whether size/growth/non-empty all passed.

If all three are good, `--apply` will write back.
