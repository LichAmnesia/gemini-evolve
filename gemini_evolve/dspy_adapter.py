"""DSPy LM adapter that routes completions through the Gemini CLI subprocess.

Lets DSPy (and in particular `dspy.GEPA`) drive evolution without needing an
API key — every LM call shells out to `gemini -p` exactly like the rest of
gemini-evolve. The CLI runs in an isolated working directory so candidate
GEMINI.md files discovered on disk don't leak into the evaluation.

Step 2 extension: the adapter can also capture the CLI's trajectory (tool
calls, intermediate tool output) by re-reading the session file written at
`~/.gemini/tmp/*/chats/session-<id>.json` after each invocation, then attaches
the trace to ``self.last_result``. Metrics consume it to build reflective
feedback for GEPA.
"""

from __future__ import annotations

import datetime
import json
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover — dspy is an optional dep
    import dspy
    from dspy.clients.lm import LM as _DSPyLM

    _DSPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    dspy = None  # type: ignore[assignment]
    _DSPyLM = object  # type: ignore[misc,assignment]
    _DSPY_AVAILABLE = False

from .cli_runner import CLIResult, run_gemini_cli


__all__ = [
    "GeminiCLILM",
    "CapturedTrace",
    "format_trace",
    "is_dspy_available",
]


def is_dspy_available() -> bool:
    """Check whether dspy is importable in the current env."""
    return _DSPY_AVAILABLE


@dataclass
class CapturedTrace:
    """A distilled view of one Gemini CLI run — prompt, response, tool calls."""

    prompt: str
    response: str
    tool_calls: list[dict] = None  # type: ignore[assignment]
    duration_seconds: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str = ""

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []

    def to_text(self, max_chars: int = 2000) -> str:
        """Format the trace as a compact human-readable string for a reflector LM."""
        lines = [f"> prompt: {self.prompt[:300]}"]
        if self.error:
            lines.append(f"> error: {self.error}")
        for i, call in enumerate(self.tool_calls, 1):
            name = call.get("name") or call.get("toolName") or "tool"
            args = call.get("args") or call.get("arguments") or ""
            result = call.get("result", "")
            if isinstance(args, (dict, list)):
                args = json.dumps(args)[:200]
            if isinstance(result, (dict, list)):
                result = json.dumps(result)[:200]
            lines.append(f"  step {i} [{name}] args={args} -> {str(result)[:200]}")
        lines.append(f"> response: {self.response[:600]}")
        joined = "\n".join(lines)
        return joined[:max_chars]


def _read_session_trace(gemini_home: Path, session_id: str) -> list[dict]:
    """Re-open the session file the Gemini CLI just wrote and pull tool calls.

    Gemini CLI writes sessions to ~/.gemini/tmp/*/chats/session-<id>.json. We
    read that file and extract any messages of type/role `tool` / `function`
    along with assistant messages that contain `toolCalls`.
    """
    if not session_id:
        return []
    chats_root = gemini_home / "tmp"
    if not chats_root.exists():
        return []
    candidates = list(chats_root.rglob(f"chats/*{session_id}*.json"))
    if not candidates:
        return []
    path = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(path.read_text(errors="replace"))
    except (json.JSONDecodeError, OSError):
        return []

    messages = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(messages, list):
        return []

    calls: list[dict] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        for call in msg.get("toolCalls", []) or []:
            if isinstance(call, dict):
                calls.append(call)
        role = msg.get("type") or msg.get("role")
        if role in ("tool", "function", "tool_use"):
            calls.append(
                {
                    "name": msg.get("name") or msg.get("toolName") or "tool",
                    "args": msg.get("args") or msg.get("input"),
                    "result": msg.get("result") or msg.get("output") or msg.get("content"),
                }
            )
    return calls


def _wrap_as_dspy_response(text: str, field_name: str = "response") -> str:
    """Wrap raw CLI output in DSPy's ChatAdapter markers so Predict can parse it.

    Without the markers DSPy's adapter falls back to JSONAdapter and then
    raises — we'd rather return empty than crash, so we always emit the
    canonical `[[ ## <field> ## ]] ... [[ ## completed ## ]]` envelope.
    """
    safe = text if text is not None else ""
    return f"[[ ## {field_name} ## ]]\n{safe}\n[[ ## completed ## ]]"


class GeminiCLILM(_DSPyLM):  # type: ignore[misc]
    """DSPy LM backed by the `gemini` CLI.

    Unlike the default `dspy.LM` (which calls LiteLLM → provider HTTP), this
    adapter never leaves the local machine: every completion is a subprocess
    invocation of `gemini -p ... -o json` that reuses the user's existing
    Gemini CLI auth.

    Parameters
    ----------
    model:
        The Gemini model name (passed as `-m` to the CLI). Also used as the
        DSPy-visible model id (prefixed with `cli/` so LiteLLM never
        recognizes it — see `forward` which is never reached).
    timeout_seconds:
        Per-call wall clock cap.
    field_name:
        Output field that gemini-evolve signatures use (default `response`).
        The adapter wraps raw CLI output in DSPy's chat markers for this field
        so Predict parses without error.
    capture_trace:
        If True, reads the CLI's session file after each call and stores the
        extracted tool-call trajectory on ``self.last_trace`` so metrics can
        turn it into reflective feedback for GEPA.
    isolated_cwd:
        If provided, runs the CLI from this directory. Defaults to an empty
        temp dir so stray GEMINI.md files in the test repo can't bleed into
        evaluations.
    """

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        *,
        timeout_seconds: int = 300,
        field_name: str = "response",
        capture_trace: bool = False,
        gemini_home: Path | None = None,
        isolated_cwd: Path | None = None,
        no_mcp: bool = False,
        **kwargs: Any,
    ) -> None:
        if not _DSPY_AVAILABLE:
            raise ImportError(
                "dspy is required for GeminiCLILM. Reinstall with: pip install -e '.[dev]'"
            )
        super().__init__(model=f"cli/{model}", cache=False, **kwargs)
        self._cli_model = model
        self.timeout_seconds = timeout_seconds
        self.field_name = field_name
        self.capture_trace = capture_trace
        self.no_mcp = no_mcp
        self.gemini_home = gemini_home or Path.home() / ".gemini"
        self._owns_cwd = isolated_cwd is None
        self._isolated_cwd = isolated_cwd or Path(
            tempfile.mkdtemp(prefix="gemini_evolve_lm_")
        )
        self._lock = threading.Lock()
        self.last_result: CLIResult | None = None
        self.last_trace: CapturedTrace | None = None
        self.call_count = 0

    def __call__(
        self,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        # Flatten DSPy's chat messages into a single prompt string for the CLI.
        if messages:
            text = "\n\n".join(
                f"[{m.get('role', 'user')}]\n{m.get('content', '')}" for m in messages
            )
        else:
            text = prompt or ""
        if not text:
            return [_wrap_as_dspy_response("", self.field_name)]

        started = datetime.datetime.now()
        result = run_gemini_cli(
            prompt=text,
            model=self._cli_model,
            timeout_seconds=self.timeout_seconds,
            cwd=self._isolated_cwd,
            no_mcp=self.no_mcp,
        )
        elapsed = (datetime.datetime.now() - started).total_seconds()

        tool_calls: list[dict] = []
        if self.capture_trace and result.session_id:
            tool_calls = _read_session_trace(self.gemini_home, result.session_id)

        trace = CapturedTrace(
            prompt=text,
            response=result.response,
            tool_calls=tool_calls,
            duration_seconds=elapsed,
            tokens_in=result.input_tokens,
            tokens_out=result.output_tokens,
            error=result.error,
        )

        with self._lock:
            self.last_result = result
            self.last_trace = trace
            self.call_count += 1

        # DSPy history bookkeeping so `inspect_history()` still works.
        try:  # pragma: no cover - defensive against future dspy changes
            from dspy import settings as _settings

            if not _settings.disable_history:
                self.update_history(
                    {
                        "prompt": prompt,
                        "messages": messages,
                        "kwargs": {k: v for k, v in kwargs.items() if not k.startswith("api_")},
                        "response": None,
                        "outputs": [result.response],
                        "usage": {
                            "prompt_tokens": result.input_tokens,
                            "completion_tokens": result.output_tokens,
                        },
                        "cost": None,
                        "timestamp": started.isoformat(),
                        "uuid": str(self.call_count),
                        "model": self.model,
                        "response_model": self.model,
                        "model_type": "chat",
                    }
                )
        except Exception:
            pass

        return [_wrap_as_dspy_response(result.response if result.ok else "", self.field_name)]

    # `forward` is what DSPy's default `__call__` delegates to. We override
    # `__call__` so it's unused, but keep an implementation that raises loudly
    # if some future DSPy path bypasses our override.
    def forward(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        raise RuntimeError(
            "GeminiCLILM.forward was called; this adapter overrides __call__ "
            "and never goes through LiteLLM. File a bug if you see this."
        )


def format_trace(lm: GeminiCLILM | None) -> str:
    """Grab the most recent captured trace from an LM (may be None)."""
    if lm is None or lm.last_trace is None:
        return ""
    return lm.last_trace.to_text()
