"""Tests for Gemini CLI runner."""

from gemini_evolve.cli_runner import _parse_cli_json, CLIResult


def test_parse_clean_json():
    raw = '{"session_id": "abc", "response": "hello"}'
    data = _parse_cli_json(raw)
    assert data["response"] == "hello"


def test_parse_json_with_mcp_warning():
    """Gemini CLI may print MCP warnings before the JSON blob."""
    raw = 'MCP issues detected. Run /mcp list for status.{"session_id": "abc", "response": "4"}'
    data = _parse_cli_json(raw)
    assert data is not None
    assert data["response"] == "4"


def test_parse_no_json():
    assert _parse_cli_json("just plain text") is None
    assert _parse_cli_json("") is None


def test_parse_invalid_json():
    assert _parse_cli_json("{broken") is None


def test_cli_result_ok():
    r = CLIResult(response="hello", exit_code=0)
    assert r.ok

    r2 = CLIResult(response="", exit_code=0)
    assert not r2.ok

    r3 = CLIResult(response="hello", exit_code=1)
    assert not r3.ok
