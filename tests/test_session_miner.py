"""Tests for session mining and secret detection."""

import json

from gemini_evolve.session_miner import contains_secret, GeminiSessionMiner


def test_detects_google_api_key():
    assert contains_secret("key=AIzaSyA1234567890123456789012345678901234")


def test_detects_openai_key():
    assert contains_secret("sk-abc123456789012345678901234567890123456789012345")


def test_detects_github_pat():
    assert contains_secret("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")


def test_detects_aws_key():
    assert contains_secret("AKIAIOSFODNN7EXAMPLE")


def test_detects_private_key():
    assert contains_secret("-----BEGIN RSA PRIVATE KEY-----")


def test_detects_anthropic_key():
    assert contains_secret("sk-ant-api03-abcdefghijklmnopqrstuvwxyz")


def test_detects_slack_token():
    assert contains_secret("xoxb-123456789-abcdefghijklmn")


def test_detects_bearer_token():
    assert contains_secret("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")


def test_detects_db_url_with_password():
    assert contains_secret("postgresql://user:secretpass@host:5432/db")


def test_detects_api_key_env():
    assert contains_secret("API_KEY=sk1234567890abcdef")


def test_clean_text_passes():
    assert not contains_secret("Just a normal user message about coding")


def test_detects_password():
    assert contains_secret('password: "mySuperSecret123"')


def test_miner_empty_dir(tmp_path):
    miner = GeminiSessionMiner(gemini_home=tmp_path)
    files = miner.find_session_files()
    assert files == []


def test_miner_no_tmp(tmp_path):
    miner = GeminiSessionMiner(gemini_home=tmp_path)
    examples = miner.extract_examples()
    assert examples == []


def test_miner_finds_session_files(tmp_path):
    """Session files live under tmp/*/chats/session-*.json."""
    chats_dir = tmp_path / "tmp" / "myproject" / "chats"
    chats_dir.mkdir(parents=True)
    session = {
        "sessionId": "test-123",
        "messages": [
            {"type": "user", "content": [{"text": "Help me refactor this function"}]},
            {"type": "gemini", "content": "Sure, let me look at the code."},
        ],
    }
    (chats_dir / "session-2026-04-15T10-00-test123.json").write_text(json.dumps(session))
    miner = GeminiSessionMiner(gemini_home=tmp_path)
    files = miner.find_session_files()
    assert len(files) == 1
    assert "session-2026" in files[0].name


def test_miner_extracts_user_messages(tmp_path):
    """User messages have content as list of {text: ...}."""
    chats_dir = tmp_path / "tmp" / "proj" / "chats"
    chats_dir.mkdir(parents=True)
    session = {
        "sessionId": "test-456",
        "messages": [
            {"type": "user", "content": [{"text": "Help me refactor this function please"}]},
            {"type": "gemini", "content": "I'll analyze the code."},
            {"type": "user", "content": [{"text": "Now add tests for the refactored code"}]},
        ],
    }
    (chats_dir / "session-2026-04-15T10-00-test456.json").write_text(json.dumps(session))
    miner = GeminiSessionMiner(gemini_home=tmp_path)
    examples = miner.extract_examples()
    assert len(examples) == 2
    assert "refactor" in examples[0].task_input
    assert "tests" in examples[1].task_input
    assert examples[0].source == "session"


def test_miner_skips_short_messages(tmp_path):
    """Messages shorter than 10 chars are skipped."""
    chats_dir = tmp_path / "tmp" / "proj" / "chats"
    chats_dir.mkdir(parents=True)
    session = {
        "messages": [
            {"type": "user", "content": [{"text": "hi"}]},
            {"type": "user", "content": [{"text": "This is a real task with enough content"}]},
        ],
    }
    (chats_dir / "session-2026-04-15T10-00-short.json").write_text(json.dumps(session))
    miner = GeminiSessionMiner(gemini_home=tmp_path)
    examples = miner.extract_examples()
    assert len(examples) == 1


def test_miner_skips_secrets(tmp_path):
    """Sessions containing secrets are skipped entirely."""
    chats_dir = tmp_path / "tmp" / "proj" / "chats"
    chats_dir.mkdir(parents=True)
    session = {
        "messages": [
            {"type": "user", "content": [{"text": "Set API_KEY=sk1234567890abcdef in the env"}]},
        ],
    }
    (chats_dir / "session-2026-04-15T10-00-secret.json").write_text(json.dumps(session))
    miner = GeminiSessionMiner(gemini_home=tmp_path)
    examples = miner.extract_examples()
    assert len(examples) == 0


def test_extract_text_string():
    assert GeminiSessionMiner._extract_text("hello") == "hello"


def test_extract_text_list():
    content = [{"text": "part one"}, {"text": "part two"}]
    assert GeminiSessionMiner._extract_text(content) == "part one\npart two"


def test_extract_text_empty():
    assert GeminiSessionMiner._extract_text(None) == ""
    assert GeminiSessionMiner._extract_text([]) == ""
