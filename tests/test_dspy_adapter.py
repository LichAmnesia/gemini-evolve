"""Tests for the DSPy adapter — exercises both Step 1 (LM plumbing) and
Step 2 (session-file trace capture) without actually invoking Gemini.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("dspy")

import dspy  # noqa: E402

from gemini_evolve.cli_runner import CLIResult  # noqa: E402
from gemini_evolve.dspy_adapter import (  # noqa: E402
    CapturedTrace,
    GeminiCLILM,
    _read_session_trace,
    _wrap_as_dspy_response,
    is_dspy_available,
)


def test_dspy_available():
    """Sanity: dspy should be importable since we just skipped otherwise."""
    assert is_dspy_available() is True


def test_wrap_as_dspy_response_emits_markers():
    wrapped = _wrap_as_dspy_response("hello", "response")
    assert "[[ ## response ## ]]" in wrapped
    assert "hello" in wrapped
    assert "[[ ## completed ## ]]" in wrapped


def test_wrap_handles_none():
    wrapped = _wrap_as_dspy_response(None, "response")  # type: ignore[arg-type]
    assert "[[ ## response ## ]]" in wrapped
    # None should become an empty body, not the literal string "None".
    assert "None" not in wrapped


def test_captured_trace_to_text_includes_tool_calls():
    trace = CapturedTrace(
        prompt="fix the bug",
        response="use grep",
        tool_calls=[
            {"name": "grep", "args": {"pattern": "foo"}, "result": "no matches"},
            {"name": "edit", "args": "file.py", "result": "ok"},
        ],
    )
    out = trace.to_text()
    assert "prompt: fix the bug" in out
    assert "step 1" in out
    assert "grep" in out
    assert "step 2" in out
    assert "edit" in out
    assert "response: use grep" in out


def test_captured_trace_empty_tool_calls():
    trace = CapturedTrace(prompt="hi", response="hello", tool_calls=[])
    out = trace.to_text()
    assert "prompt: hi" in out
    assert "response: hello" in out


def _make_session_file(root: Path, session_id: str, payload: dict) -> Path:
    """Create a session-<id>.json mimicking Gemini CLI's layout."""
    chats = root / "tmp" / f"proj-{session_id[:6]}" / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    path = chats / f"session-{session_id}.json"
    path.write_text(json.dumps(payload))
    return path


def test_read_session_trace_extracts_tool_calls(tmp_path):
    session_id = "abcdef123456"
    _make_session_file(
        tmp_path,
        session_id,
        {
            "sessionId": session_id,
            "messages": [
                {"type": "user", "content": [{"text": "hello"}]},
                {
                    "type": "gemini",
                    "content": "calling grep",
                    "toolCalls": [
                        {"name": "grep", "args": {"q": "bug"}, "result": "0 matches"}
                    ],
                },
                # Also support `tool` role messages.
                {"role": "tool", "name": "edit", "input": "x.py", "output": "patched"},
            ],
        },
    )
    calls = _read_session_trace(tmp_path, session_id)
    assert len(calls) == 2
    assert calls[0]["name"] == "grep"
    assert calls[1]["name"] == "edit"
    assert calls[1]["args"] == "x.py"
    assert calls[1]["result"] == "patched"


def test_read_session_trace_returns_empty_when_no_file(tmp_path):
    # Empty home directory → no sessions → empty list, not crash.
    assert _read_session_trace(tmp_path, "no-such-id") == []


def test_read_session_trace_handles_bad_json(tmp_path):
    path = _make_session_file(tmp_path, "xyz789", {"messages": []})
    path.write_text("{not json")
    assert _read_session_trace(tmp_path, "xyz789") == []


def test_read_session_trace_no_session_id_returns_empty(tmp_path):
    _make_session_file(tmp_path, "something", {"messages": []})
    assert _read_session_trace(tmp_path, "") == []


def test_gemini_lm_shells_out(monkeypatch, tmp_path):
    """Core LM contract: __call__ returns DSPy-wrapped text from the CLI."""
    calls: list[dict] = []

    def fake_run(prompt, *, model, timeout_seconds, cwd=None, **kw):
        calls.append({"prompt": prompt, "model": model, "cwd": cwd})
        return CLIResult(
            response="the answer is 42",
            session_id="sess-1",
            exit_code=0,
            input_tokens=10,
            output_tokens=5,
        )

    monkeypatch.setattr("gemini_evolve.dspy_adapter.run_gemini_cli", fake_run)

    lm = GeminiCLILM(
        model="gemini-3-flash-preview",
        gemini_home=tmp_path,
        isolated_cwd=tmp_path,
    )
    out = lm(prompt="what is 6 x 7?")
    assert len(out) == 1
    assert "the answer is 42" in out[0]
    assert "[[ ## response ## ]]" in out[0]
    assert calls[0]["prompt"] == "what is 6 x 7?"
    assert calls[0]["model"] == "gemini-3-flash-preview"
    assert lm.last_result is not None
    assert lm.last_result.session_id == "sess-1"
    assert lm.call_count == 1
    # No trace capture requested → no tool calls.
    assert lm.last_trace is not None
    assert lm.last_trace.tool_calls == []


def test_gemini_lm_capture_trace(monkeypatch, tmp_path):
    """With capture_trace=True, the LM re-reads the session file to pull tool calls."""
    session_id = "trace-sess-99"
    _make_session_file(
        tmp_path,
        session_id,
        {
            "messages": [
                {
                    "type": "gemini",
                    "content": "searching",
                    "toolCalls": [
                        {"name": "grep", "args": {"q": "TODO"}, "result": "found 3"}
                    ],
                }
            ]
        },
    )

    def fake_run(prompt, *, model, timeout_seconds, cwd=None, **kw):
        return CLIResult(response="done", session_id=session_id, exit_code=0)

    monkeypatch.setattr("gemini_evolve.dspy_adapter.run_gemini_cli", fake_run)

    lm = GeminiCLILM(
        model="gemini-3-flash-preview",
        capture_trace=True,
        gemini_home=tmp_path,
        isolated_cwd=tmp_path,
    )
    lm(prompt="look for TODO")
    assert lm.last_trace is not None
    assert len(lm.last_trace.tool_calls) == 1
    assert lm.last_trace.tool_calls[0]["name"] == "grep"
    # And the formatted text contains the trace content.
    assert "grep" in lm.last_trace.to_text()


def test_gemini_lm_flattens_messages(monkeypatch, tmp_path):
    captured: list[str] = []

    def fake_run(prompt, *, model, timeout_seconds, cwd=None, **kw):
        captured.append(prompt)
        return CLIResult(response="ok", exit_code=0)

    monkeypatch.setattr("gemini_evolve.dspy_adapter.run_gemini_cli", fake_run)

    lm = GeminiCLILM(gemini_home=tmp_path, isolated_cwd=tmp_path)
    lm(
        messages=[
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "ping?"},
        ]
    )
    assert captured, "CLI must be called"
    assert "be brief" in captured[0]
    assert "ping?" in captured[0]


def test_gemini_lm_empty_prompt_short_circuits(monkeypatch, tmp_path):
    called = {"n": 0}

    def fake_run(prompt, *, model, timeout_seconds, cwd=None, **kw):
        called["n"] += 1
        return CLIResult(response="x", exit_code=0)

    monkeypatch.setattr("gemini_evolve.dspy_adapter.run_gemini_cli", fake_run)
    lm = GeminiCLILM(gemini_home=tmp_path, isolated_cwd=tmp_path)
    out = lm(prompt="")
    assert called["n"] == 0  # Never shelled out.
    assert "[[ ## response ## ]]" in out[0]


def test_gemini_lm_works_with_predict(monkeypatch, tmp_path):
    """Integration: a dspy.Predict call routed through our LM round-trips correctly."""

    def fake_run(prompt, *, model, timeout_seconds, cwd=None, **kw):
        return CLIResult(response="42", exit_code=0)

    monkeypatch.setattr("gemini_evolve.dspy_adapter.run_gemini_cli", fake_run)

    lm = GeminiCLILM(gemini_home=tmp_path, isolated_cwd=tmp_path)
    dspy.settings.configure(lm=lm)

    sig = dspy.Signature("task -> response", "Answer the task.")
    p = dspy.Predict(sig)
    out = p(task="what is 6*7?")
    assert out.response.strip() == "42"
