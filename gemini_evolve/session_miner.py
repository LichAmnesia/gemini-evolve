"""Mine Gemini CLI session history for real-world evaluation data."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .dataset import EvalExample

# Patterns that indicate secrets — never include these in datasets
SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),  # Google API key
    re.compile(r"ya29\.[0-9A-Za-z_-]+"),  # Google OAuth token
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI key
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"),  # Anthropic key
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub PAT
    re.compile(r"gho_[a-zA-Z0-9]{36}"),  # GitHub OAuth
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
    re.compile(r"xox[bporas]-[a-zA-Z0-9-]+"),  # Slack tokens
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*['\"][^'\"]{20,}['\"]", re.IGNORECASE),
    re.compile(r"[Bb]earer\s+[a-zA-Z0-9_-]{20,}"),  # Bearer tokens
    re.compile(r"[a-z]+://[^:]+:[^@]+@"),  # DB/service URLs with password
    re.compile(r"(?:API_KEY|SECRET_KEY|ACCESS_KEY)\s*=\s*\S{10,}", re.IGNORECASE),
]


def contains_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


class GeminiSessionMiner:
    """Extracts evaluation examples from Gemini CLI session history.

    Gemini CLI stores session data in ~/.gemini/tmp/*/chats/session-*.json
    (not in ~/.gemini/history/ which only contains .project_root pointers).
    """

    def __init__(self, gemini_home: Path | None = None):
        self.gemini_home = gemini_home or Path.home() / ".gemini"

    def find_session_files(self) -> list[Path]:
        """Find all session chat files under ~/.gemini/tmp/*/chats/."""
        sessions_dir = self.gemini_home / "tmp"
        if not sessions_dir.exists():
            return []

        files = list(sessions_dir.rglob("chats/session-*.json"))
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def extract_examples(
        self,
        max_examples: int = 50,
        relevance_filter: str | None = None,
    ) -> list[EvalExample]:
        """Extract task examples from session history."""
        examples = []
        filter_lower = relevance_filter.lower() if relevance_filter else None

        for session_file in self.find_session_files():
            try:
                session_examples = self._parse_session(session_file)
            except (json.JSONDecodeError, KeyError, OSError):
                continue

            for ex in session_examples:
                if filter_lower and (
                    filter_lower not in ex.task_input.lower()
                    and filter_lower not in ex.expected_behavior.lower()
                ):
                    continue
                examples.append(ex)
                if len(examples) >= max_examples:
                    return examples

        return examples

    def _parse_session(self, path: Path) -> list[EvalExample]:
        """Parse a single session file into examples.

        Gemini CLI session format (JSON):
        {
          "sessionId": "...",
          "messages": [
            {"type": "user", "content": [{"text": "..."}]},
            {"type": "gemini", "content": "...", "toolCalls": [...]}
          ]
        }
        """
        text = path.read_text(errors="replace")
        if contains_secret(text):
            return []

        examples = []

        if path.suffix == ".jsonl":
            for line in text.strip().split("\n"):
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if ex := self._message_to_example(msg):
                        examples.append(ex)
                except json.JSONDecodeError:
                    continue
        else:
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    for msg in data:
                        if ex := self._message_to_example(msg):
                            examples.append(ex)
                elif isinstance(data, dict):
                    messages = data.get("messages", data.get("conversation", []))
                    for msg in messages:
                        if ex := self._message_to_example(msg):
                            examples.append(ex)
            except json.JSONDecodeError:
                pass

        return examples

    @staticmethod
    def _extract_text(content) -> str:
        """Extract plain text from Gemini message content.

        Handles both formats:
        - str: "some text" (gemini responses)
        - list: [{"text": "..."}] (user messages)
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
                elif isinstance(part, str):
                    parts.append(part)
            return "\n".join(parts)
        return ""

    def _message_to_example(self, msg: dict) -> EvalExample | None:
        """Convert a user message into an evaluation example."""
        role = msg.get("type", msg.get("role", ""))
        raw_content = msg.get("content", msg.get("text", ""))
        content = self._extract_text(raw_content)

        if role not in ("user", "human"):
            return None
        if not content or len(content) < 10:
            return None
        if contains_secret(content):
            return None

        return EvalExample(
            task_input=content[:2000],
            expected_behavior="Agent should handle this task correctly following the system instructions.",
            source="session",
        )
