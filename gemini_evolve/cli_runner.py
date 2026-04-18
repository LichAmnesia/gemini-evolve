"""Run Gemini CLI in non-interactive mode for realistic agent simulation."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CLIResult:
    """Result from a Gemini CLI invocation."""

    response: str
    session_id: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    exit_code: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and bool(self.response)


# Gemini CLI may print warnings (e.g. MCP issues) before the JSON blob.
# We find the first '{' to skip any prefix noise.
def _parse_cli_json(raw: str) -> dict | None:
    idx = raw.find("{")
    if idx < 0:
        return None
    try:
        return json.loads(raw[idx:])
    except json.JSONDecodeError:
        return None


def find_gemini_cli() -> str | None:
    """Locate the gemini CLI binary."""
    return shutil.which("gemini")


def run_gemini_cli(
    prompt: str,
    *,
    timeout_seconds: int = 300,
    model: str | None = None,
    cwd: Path | None = None,
    sandbox: bool = False,
    no_mcp: bool = False,
) -> CLIResult:
    """Execute a single prompt via `gemini -p "..." -o json`.

    This runs the prompt in the full Gemini CLI environment — loading
    GEMINI.md, project context, MCP tools, skills, etc. — which gives
    realistic evaluation of instruction quality.

    Args:
        prompt: The user prompt to send.
        timeout_seconds: Max wall-clock time before killing the process.
        model: Override model (--model flag). None = CLI default.
        cwd: Working directory for the CLI process.
        sandbox: Run in sandbox mode (no file writes). Off by default — we
            always run with ``--approval-mode plan`` which already blocks
            execution, so the sandbox adds 5–20s of startup overhead per
            call without any extra safety. Opt in if you have custom tools
            that can bypass plan mode.
        no_mcp: If True, disables every MCP server for this call by passing
            ``--allowed-mcp-server-names __none__``. Useful when a broken
            MCP server is causing the CLI to bail, or to shave the 10–30s
            MCP bootstrap from each evaluation call.
    """
    gemini = find_gemini_cli()
    if not gemini:
        return CLIResult(response="", error="gemini CLI not found on PATH", exit_code=127)

    cmd = [gemini, "-p", prompt, "-o", "json"]
    if model:
        cmd.extend(["-m", model])
    if sandbox:
        cmd.extend(["--sandbox"])
    if no_mcp:
        cmd.extend(["--allowed-mcp-server-names", "__none__"])
    # Plan mode prevents the CLI from executing tools during evaluation.
    cmd.extend(["--approval-mode", "plan"])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired:
        return CLIResult(
            response="", error=f"Timed out after {timeout_seconds}s", exit_code=-1
        )
    except OSError as e:
        return CLIResult(response="", error=str(e), exit_code=-1)

    if proc.returncode != 0 and not proc.stdout.strip():
        return CLIResult(
            response="",
            error=proc.stderr.strip()[:500] if proc.stderr else f"exit code {proc.returncode}",
            exit_code=proc.returncode,
        )

    data = _parse_cli_json(proc.stdout)
    if data is None:
        # Fallback: treat raw stdout as plain text response
        return CLIResult(
            response=proc.stdout.strip()[:4000],
            exit_code=proc.returncode,
        )

    # Extract token stats from the nested models dict
    models = data.get("stats", {}).get("models", {})
    first_model = next(iter(models), "")
    tokens = models.get(first_model, {}).get("tokens", {})

    return CLIResult(
        response=data.get("response", ""),
        session_id=data.get("session_id", ""),
        model=first_model,
        input_tokens=tokens.get("input", 0),
        output_tokens=tokens.get("candidates", 0),
        exit_code=proc.returncode,
    )
