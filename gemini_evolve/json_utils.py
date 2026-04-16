"""Robust JSON extraction from LLM responses."""

from __future__ import annotations

import json
import re

# Match JSON inside code fences, handling prefix/suffix prose
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def extract_json(text: str | None) -> object | None:
    """Extract JSON from LLM response text, handling common output patterns.

    Handles:
    - Raw JSON
    - JSON wrapped in ```json ... ``` code fences
    - Prose before/after code fences
    - Multiple code fences (takes the first valid one)
    """
    if not text:
        return None

    # Try raw parse first
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Try extracting from code fences
    for match in _CODE_FENCE_RE.finditer(text):
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            continue

    # Try finding JSON array or object boundaries
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Find matching end bracket, accounting for nesting
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    return None
