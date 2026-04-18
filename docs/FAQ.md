# FAQ / Troubleshooting

Stuff that will probably trip you up in the first hour. If the symptom isn't here, check [RUNBOOK.md](RUNBOOK.md) § Common Failures or open an issue.

---

## Install & environment

**Q: `gemini-evolve: command not found` right after install.**
You installed into a venv; either use the full path `./.venv/bin/gemini-evolve` or `source .venv/bin/activate` first. Check with `which gemini-evolve`.

**Q: `ModuleNotFoundError: dspy` or anything DSPy-shaped.**
Reinstall runtime deps into the **same venv** you're running `gemini-evolve` from:
```bash
./.venv/bin/pip install -e .
```
DSPy is a required runtime dep (declared in `pyproject.toml`, not in the `[dev]` extras), so this should never happen on a clean install. The usual root cause is that `pip` and `gemini-evolve` came from different Pythons — e.g. you ran plain `pip install` (system Python) but are executing `./.venv/bin/gemini-evolve`. Always call `pip` with the venv's `./.venv/bin/pip` path, or `source .venv/bin/activate` first. Verify with `./.venv/bin/pip show dspy` — if that prints a version, your venv is fine and something else is shadowing it. If it prints nothing, the venv itself is broken; nuke and rebuild it: `python3 -m venv --clear .venv && ./.venv/bin/pip install -e .`.

**Q: Python 3.10 or older.**
Not supported. `pyproject.toml` pins `requires-python = ">=3.11"`. Install 3.11+ (`brew install python@3.12` on macOS) and recreate the venv.

**Q: Does it work on Windows?**
Not tested. macOS and Linux are the supported targets. `trigger cron-*` is macOS-only regardless.

---

## Gemini CLI side

**Q: `gemini CLI not found on PATH`, but I can run `gemini` in my terminal.**
You're running `gemini-evolve` from a shell that didn't load the same PATH. Check `which gemini` in the exact terminal where you run gemini-evolve. If your `gemini` came from a Node version manager (nvm, fnm, volta), make sure the shell has loaded it.

**Q: Model calls time out.**
Every variant call has a 300s timeout. If Gemini is slow that day, shrink the population/generations (`-p 2 -g 2`) or pass `--gepa-budget light`. Rerun will re-use no cached state — you're not wasting anything.

**Q: Synthetic dataset is empty.**
`gemini` either failed or returned something we couldn't parse. Try `--eval-source session` (uses your real messages) or `--eval-source golden --eval-dataset your.jsonl`.

**Q: Session dataset is empty.**
You either haven't used Gemini CLI much, or all mined messages looked like secrets/credentials and got filtered. Use Gemini CLI for a while, or point to a golden JSONL.

---

## Apply / gates

**Q: `--apply` did nothing, but the Evolution Results table showed +X%.**
Check which gate the console said it failed. The five gates are: non-empty, size cap, growth cap (default 20%), min-improvement % on holdout (default 2%), and "content actually changed." A +X% improvement that's below 2% is still too small to write.

**Q: Can I force-apply a result that's below the threshold?**
On purpose, there's no `--force` flag — that's the whole product. If you really want to, `cp output/<target>/<timestamp>/evolved.md ~/.gemini/GEMINI.md` manually. You own the consequences.

**Q: How do I roll back an apply?**
```bash
ls -t ~/.gemini/GEMINI.md.*.bak | head -5
cp "$(ls -t ~/.gemini/GEMINI.md.*.bak | head -1)" ~/.gemini/GEMINI.md
```

**Q: `Improvement below threshold` — is this a bug?**
No. The holdout set is examples the loop never trained on; if they don't move ≥ `min_improvement_pct`, the gate refuses to write. That's the loop catching overfitting for you.

---

## Eval data

**Q: What's the difference between val and holdout?**
Val drives selection inside the loop (which variant wins generation N). Holdout is held out of the entire loop and only used for the final before/after comparison. Keeping them separate is what lets gemini-evolve detect overfitting.

**Q: What does a golden JSONL look like?**
One JSON object per line, with at minimum `task_input` and `expected_behavior` fields (see `gemini_evolve/dataset.py` for the canonical loader). Pass it with `--eval-source golden --eval-dataset path.jsonl`.

**Q: Session mining privacy?**
Messages that look like secrets or credentials get filtered before they hit the dataset. Data stays on your machine — nothing is uploaded.

---

## Triggers / automation

**Q: `cron-install` on Linux errors out with `launchctl` complaints.**
launchd is macOS-only. Use `trigger watch` (cross-platform) or wire up cron / systemd pointing at `./.venv/bin/gemini-evolve evolve ... --apply`.

**Q: `hook-install` says "Not a git repository".**
Run it from a repo root (`cd /path/to/repo && gemini-evolve trigger hook-install .`).

**Q: Will the git hook fire on every commit?**
No. It only runs when the commit touches `GEMINI.md` or anything under `.gemini/`.

---

## General "is this for me?"

**Q: I only use the Gemini web UI, not the CLI. Does this help?**
No. gemini-evolve is Gemini-CLI-native end to end — it reads your `GEMINI.md` and runs your `gemini` binary. Get the CLI working first.

**Q: Can it optimize prompts that aren't `GEMINI.md`?**
Yes, for the three artifact types listed in the README: `~/.gemini/GEMINI.md`, `~/.gemini/commands/*.toml`, `~/.gemini/skills/**/*.md`, plus per-project `.gemini/GEMINI.md`. Anything else, you'd have to write yourself.

**Q: Can I use it without DSPy / GEPA?**
Yes — `--engine ga` uses the built-in tournament GA and bypasses DSPy code paths. DSPy is still installed (it's a default dep), just not exercised.

**Q: Is there a video demo / asciinema / GIF?**
Not yet. The text before/after diff in the README and the worked examples in [EXAMPLES.md](EXAMPLES.md) are the closest thing. A recorded run is on the backlog — if you want one sooner, opening an issue moves it up.
