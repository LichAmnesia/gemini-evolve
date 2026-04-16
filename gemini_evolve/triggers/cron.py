"""macOS launchd plist generation for scheduled evolution."""

from __future__ import annotations

import plistlib
import shlex
import subprocess
from pathlib import Path

PLIST_LABEL = "com.gemini-evolve.scheduled"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


def generate_plist(
    interval_hours: int = 24,
    target_type: str = "instructions",
    python_path: str | None = None,
    extra_args: str = "",
    working_directory: Path | None = None,
    apply: bool = False,
) -> bytes:
    """Generate a launchd plist for scheduled evolution.

    Uses plistlib for safe XML generation (no injection risk).
    """
    if python_path is None:
        python_path = _detect_python()

    program_args = [
        python_path, "-m", "gemini_evolve.cli",
        "evolve-all", "--type", target_type,
    ]
    if apply:
        program_args.append("--apply")
    if extra_args:
        program_args.extend(shlex.split(extra_args))

    plist_data = {
        "Label": PLIST_LABEL,
        "ProgramArguments": program_args,
        "StartInterval": interval_hours * 3600,
        "StandardOutPath": str(Path.home() / ".gemini" / "evolve.log"),
        "StandardErrorPath": str(Path.home() / ".gemini" / "evolve-error.log"),
        "WorkingDirectory": str(working_directory or Path.home()),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
    }
    return plistlib.dumps(plist_data)


def install_cron(
    interval_hours: int = 24,
    target_type: str = "instructions",
    python_path: str | None = None,
    apply: bool = False,
) -> Path:
    """Install the launchd plist and load it."""
    plist_content = generate_plist(interval_hours, target_type, python_path, apply=apply)
    plist_path = PLIST_DIR / f"{PLIST_LABEL}.plist"
    PLIST_DIR.mkdir(parents=True, exist_ok=True)

    # Unload existing if present
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
        )

    plist_path.write_bytes(plist_content)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return plist_path


def uninstall_cron() -> bool:
    """Remove the scheduled evolution job."""
    plist_path = PLIST_DIR / f"{PLIST_LABEL}.plist"
    if not plist_path.exists():
        return False
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    plist_path.unlink()
    return True


def status() -> dict:
    """Check if the cron job is installed and running."""
    plist_path = PLIST_DIR / f"{PLIST_LABEL}.plist"
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True,
        text=True,
    )
    return {
        "installed": plist_path.exists(),
        "loaded": result.returncode == 0,
        "plist_path": str(plist_path),
        "output": result.stdout.strip() if result.returncode == 0 else None,
    }


def _detect_python() -> str:
    """Detect the best python to use, preferring the current venv."""
    import sys

    # Prefer the python that has gemini-evolve installed (likely a venv)
    current = sys.executable
    if current and Path(current).exists():
        return current
    for candidate in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]:
        if Path(candidate).exists():
            return candidate
    return "python3"


