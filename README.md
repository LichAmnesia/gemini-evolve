# gemini-evolve

Self-evolution system for Gemini CLI — automatically improves system instructions, commands, and skills through LLM-guided mutation and evaluation.

All LLM calls go through `gemini` CLI (`gemini -p "..." -o json`). No direct API calls, no API keys, no SDK. Uses your existing Gemini CLI auth and quota.

## How It Works

```
┌──────────────────────────────────────────────────────────────┐
│                    EVOLUTION LOOP                             │
│                                                              │
│  1. LOAD target (GEMINI.md / command / skill)                │
│  2. GENERATE evaluation dataset (synthetic / session)        │
│  3. VALIDATE baseline constraints                            │
│                                                              │
│  ┌─── For each generation ────────────────────────────────┐  │
│  │  4. MUTATE → N variants via gemini CLI                 │  │
│  │  5. EVALUATE each variant via gemini CLI (real env)    │  │
│  │  6. SELECT best (tournament) + optional crossover      │  │
│  │  7. CONSTRAIN → reject if size/growth exceeded         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  8. EVALUATE winner on holdout set vs baseline               │
│  9. --apply → backup + overwrite original file               │
│     → next gemini session automatically uses new version     │
└──────────────────────────────────────────────────────────────┘
```

---

## Full Setup Guide (Zero to Automated)

### Step 1: Install

```bash
# Clone and install
cd ~/ws/gemini-evolve
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Add to PATH
ln -sf ~/ws/gemini-evolve/.venv/bin/gemini-evolve ~/.local/bin/gemini-evolve

# Verify
gemini-evolve --version
# gemini-evolve, version 0.1.0

# Also verify Gemini CLI is installed and authed
gemini --version
```

### Step 2: Create seed GEMINI.md

gemini-evolve needs a file to evolve. If you don't have `~/.gemini/GEMINI.md` yet:

```bash
cat > ~/.gemini/GEMINI.md << 'EOF'
# Global Gemini CLI Instructions

## Work Style
- 中文交流优先，代码/commit 用英文
- Concise responses, minimal tokens
- Fix root cause, not band-aids

## Code Standards
- Conventional Commits
- Files < 500 LOC; refactor as needed
- Add regression tests for bugs

## Git
- Safe by default: status/diff/log before destructive ops
- Never force push to main/master
EOF
```

### Step 3: Verify targets exist

```bash
gemini-evolve discover --type instructions
#   /Users/you/.gemini/GEMINI.md (0.5KB)
#   /Users/you/ws/project/.gemini/GEMINI.md (1.2KB)

gemini-evolve discover --type commands
gemini-evolve discover --type skills
```

### Step 4: Dry run (validate constraints, no CLI calls)

```bash
gemini-evolve evolve ~/.gemini/GEMINI.md --dry-run
# PASS non_empty
# PASS size_limit: 0.5KB <= 15.0KB
```

### Step 5: First evolution (review only, don't write back)

```bash
# Small run to validate pipeline works
gemini-evolve evolve ~/.gemini/GEMINI.md -g 2 -p 2
```

Review what changed:

```bash
# See the diff
diff output/global/*/baseline.md output/global/*/evolved.md

# See scores
cat output/global/*/metrics.json
```

### Step 6: Evolve and apply

Once you trust the pipeline, use `--apply` to write back:

```bash
gemini-evolve evolve ~/.gemini/GEMINI.md --apply
```

What happens:
1. Runs evolution (5 generations × 4 variants by default)
2. If improved ≥2% AND passes all constraints:
   - Backs up original → `GEMINI.md.20260416_120000.bak`
   - Overwrites `~/.gemini/GEMINI.md` with evolved version
   - **Next `gemini` CLI session automatically uses the new version**
3. If not improved enough: saves to `output/` only, original unchanged

### Step 7: Set up automation

Choose one:

#### Option A: Auto-evolve after every Gemini CLI session

```bash
# Watches ~/.gemini/tmp for new session files
# 60s after last file change → triggers evolution → applies if improved
gemini-evolve trigger watch --apply

# Runs in foreground. To background it:
nohup gemini-evolve trigger watch --apply > ~/.gemini/evolve-watch.log 2>&1 &
```

#### Option B: Scheduled (every N hours)

```bash
# Install launchd job: evolve every 12 hours and auto-apply
gemini-evolve trigger cron-install --interval 12 --apply

# Check status
gemini-evolve trigger cron-status

# Remove
gemini-evolve trigger cron-remove
```

Logs at `~/.gemini/evolve.log` and `~/.gemini/evolve-error.log`.

#### Option C: Git hook (evolve when you change instructions)

```bash
cd ~/ws/my-project
gemini-evolve trigger hook-install .

# Triggers when commits modify GEMINI.md or .gemini/ files
```

### Step 8: Monitor and rollback

```bash
# See evolution history
ls output/global/

# See latest results
cat output/global/$(ls -t output/global/ | head -1)/metrics.json

# List backups
ls ~/.gemini/GEMINI.md.*.bak

# Rollback to a specific backup
cp ~/.gemini/GEMINI.md.20260416_120000.bak ~/.gemini/GEMINI.md
```

---

## What Gets Evolved

| Target | Path | Scope | Command |
|--------|------|-------|---------|
| Global instructions | `~/.gemini/GEMINI.md` | All gemini sessions | `gemini-evolve evolve ~/.gemini/GEMINI.md --apply` |
| Project instructions | `<project>/.gemini/GEMINI.md` | That project only | `gemini-evolve evolve <path> --apply` |
| Custom commands | `~/.gemini/commands/*.toml` | Slash commands | `gemini-evolve evolve <path> --apply` |
| Skills | `~/.gemini/skills/*.md` | Skill definitions | `gemini-evolve evolve <path> --apply` |

Batch evolve all targets of a type:

```bash
gemini-evolve evolve-all --type instructions --apply
gemini-evolve evolve-all --type commands --apply
gemini-evolve evolve-all --type skills --apply
```

---

## CLI Reference

```
gemini-evolve evolve <target> [OPTIONS]

  -g, --generations N       Evolution generations (default: 5)
  -p, --population N        Variants per generation (default: 4)
  --eval-source TYPE        synthetic | session | golden (default: synthetic)
  --eval-dataset PATH       JSONL file for --eval-source golden
  --llm-judge               Use LLM judge scoring (slower, more accurate)
  --apply                   Write back to original file if improved
  --dry-run                 Validate constraints only, no evolution
  -o, --output PATH         Output directory (default: output)

gemini-evolve evolve-all --type TYPE [OPTIONS]
  Same options as evolve, applied to all targets of TYPE.

gemini-evolve discover --type TYPE
  List all discoverable targets.

gemini-evolve trigger watch [OPTIONS]
  --debounce N              Seconds to wait after last file change (default: 60)
  --type TYPE               Target type to evolve (default: instructions)
  --apply                   Auto-apply evolved results

gemini-evolve trigger cron-install [OPTIONS]
  --interval N              Run every N hours (default: 24)
  --type TYPE               Target type to evolve (default: instructions)
  --apply                   Auto-apply evolved results

gemini-evolve trigger cron-status
gemini-evolve trigger cron-remove

gemini-evolve trigger hook-install [REPO]
gemini-evolve trigger hook-remove [REPO]
```

## Evaluation Sources

| Source | Flag | When to use |
|--------|------|-------------|
| Synthetic | `--eval-source synthetic` | Default. Gemini generates test tasks from instructions. |
| Session | `--eval-source session` | Uses your real Gemini CLI history (8000+ sessions). |
| Golden | `--eval-source golden --eval-dataset data.jsonl` | Hand-curated evaluation set. |

## Safety Gates

Before `--apply` writes anything back, all gates must pass:

1. **Size limit**: ≤15KB instructions/skills, ≤5KB commands
2. **Growth limit**: Max +20% size increase over baseline
3. **Non-empty**: Content must not be blank
4. **Min improvement**: ≥2% on holdout set (configurable)
5. **Backup**: Original saved as `<file>.<timestamp>.bak` before overwrite

If any gate fails, results are saved to `output/` only.

## Configuration

Environment variables (optional — defaults are sensible):

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_EVOLVE_POPULATION` | `4` | Variants per generation |
| `GEMINI_EVOLVE_GENERATIONS` | `5` | Number of generations |
| `GEMINI_EVOLVE_OUTPUT` | `output` | Output directory |
| `GEMINI_EVOLVE_PROJECT_PATHS` | `~/ws:~/projects:~/code` | Dirs to scan for project GEMINI.md |

## Architecture

```
gemini_evolve/
├── cli.py              # Click CLI entry point
├── cli_runner.py       # gemini CLI subprocess (gemini -p ... -o json)
├── config.py           # EvolutionConfig dataclass
├── evolve.py           # Core evolution loop (tournament selection)
├── dataset.py          # Eval dataset generation/loading
├── fitness.py          # Scoring: fast heuristic + LLM judge
├── constraints.py      # Size/growth/structure validation
├── mutator.py          # LLM-guided mutation + crossover
├── session_miner.py    # Mine Gemini CLI session history (~/.gemini/tmp/)
├── json_utils.py       # Robust JSON extraction
└── triggers/
    ├── cron.py         # macOS launchd plist
    ├── watcher.py      # File system watcher (watchdog)
    └── hook.py         # Git post-commit hook
```

All LLM calls: `cli_runner.py` → `gemini -p "..." -o json --sandbox --approval-mode plan`

## Performance

- Each evaluation = 1 `gemini -p` call (~10-60s)
- Default run (5 gen × 4 variants × 10 eval examples) ≈ 200 CLI calls
- First run: use `-g 2 -p 2` to validate quickly
- Timeouts (300s) are skipped, not scored as 0

## Development

```bash
.venv/bin/pip install -e ".[dev]"
pytest  # 62 tests
```
