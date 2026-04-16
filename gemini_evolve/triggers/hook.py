"""Git hook trigger — evolve after commits that change instruction files."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

BEGIN_MARKER = "# BEGIN gemini-evolve"
END_MARKER = "# END gemini-evolve"

HOOK_SCRIPT = dedent(f"""\

{BEGIN_MARKER}
# gemini-evolve post-commit hook
# Runs evolution when GEMINI.md or .gemini/ files are modified
changed_files=$(git diff --name-only HEAD~1 HEAD 2>/dev/null)

if echo "$changed_files" | grep -qE '(GEMINI\\.md|\\.gemini/)'; then
    echo "[gemini-evolve] Detected instruction changes, triggering evolution..."
    python3 -m gemini_evolve.cli evolve-all --type instructions &
fi
{END_MARKER}
""")


def install_hook(repo_path: Path) -> Path:
    """Install a post-commit hook that triggers evolution on instruction changes."""
    hooks_dir = repo_path / ".git" / "hooks"
    if not hooks_dir.exists():
        raise FileNotFoundError(f"Not a git repository: {repo_path}")

    hook_path = hooks_dir / "post-commit"

    if hook_path.exists():
        existing = hook_path.read_text()
        if BEGIN_MARKER in existing:
            return hook_path
        # Append to existing hook
        with open(hook_path, "a") as f:
            f.write(HOOK_SCRIPT)
    else:
        hook_path.write_text("#!/bin/bash" + HOOK_SCRIPT)

    hook_path.chmod(0o755)
    return hook_path


def uninstall_hook(repo_path: Path) -> bool:
    """Remove the gemini-evolve hook from a repository."""
    hook_path = repo_path / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        return False

    content = hook_path.read_text()
    if BEGIN_MARKER not in content:
        return False

    # Remove everything between BEGIN and END markers (inclusive)
    begin_idx = content.find(BEGIN_MARKER)
    end_idx = content.find(END_MARKER)
    if end_idx == -1:
        # Malformed: remove from BEGIN to end of file
        remaining = content[:begin_idx]
    else:
        remaining = content[:begin_idx] + content[end_idx + len(END_MARKER):]

    remaining = remaining.rstrip() + "\n" if remaining.strip() else ""

    if remaining and remaining.strip() != "#!/bin/bash":
        hook_path.write_text(remaining)
    else:
        hook_path.unlink()

    return True
