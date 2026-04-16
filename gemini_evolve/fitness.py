"""Fitness scoring for evolved artifacts using Gemini CLI as judge."""

from __future__ import annotations

from dataclasses import dataclass

from .cli_runner import run_gemini_cli
from .json_utils import extract_json


@dataclass
class FitnessScore:
    correctness: float = 0.0
    procedure_following: float = 0.0
    conciseness: float = 0.0
    feedback: str = ""

    @property
    def composite(self) -> float:
        return (
            0.50 * self.correctness
            + 0.30 * self.procedure_following
            + 0.20 * self.conciseness
        )


JUDGE_PROMPT = """\
You are an expert evaluator of AI agent instructions.

Given:
- **Instructions**: The system instructions being evaluated
- **Task**: A user task the agent should handle
- **Expected behavior**: What good performance looks like
- **Agent output**: What the agent actually produced

Score each dimension 0.0-1.0:
1. **correctness**: Did the output match expected behavior?
2. **procedure_following**: Did the agent follow the instructions' procedure?
3. **conciseness**: Was the output appropriately concise (not verbose)?

Respond with ONLY valid JSON:
{"correctness": 0.0, "procedure_following": 0.0, "conciseness": 0.0, "feedback": "..."}
"""


class LLMJudge:
    """Uses Gemini CLI to evaluate instruction quality on task examples."""

    def __init__(self, model: str | None = None):
        self.model = model

    def score(
        self,
        instructions: str,
        task_input: str,
        expected_behavior: str,
        agent_output: str,
    ) -> FitnessScore:
        user_msg = (
            f"## Instructions\n{instructions}\n\n"
            f"## Task\n{task_input}\n\n"
            f"## Expected Behavior\n{expected_behavior}\n\n"
            f"## Agent Output\n{agent_output}"
        )
        prompt = JUDGE_PROMPT + "\n\n" + user_msg
        result = run_gemini_cli(
            prompt=prompt,
            model=self.model,
            timeout_seconds=300,
        )
        if not result.ok:
            return FitnessScore(feedback=f"CLI error: {result.error}")
        return self._parse_response(result.response)

    def _parse_response(self, text: str) -> FitnessScore:
        data = extract_json(text)
        if data is None or not isinstance(data, dict):
            return FitnessScore(feedback=f"Parse error: {text[:200]}")
        try:
            return FitnessScore(
                correctness=float(data.get("correctness", 0)),
                procedure_following=float(data.get("procedure_following", 0)),
                conciseness=float(data.get("conciseness", 0)),
                feedback=str(data.get("feedback", "")),
            )
        except (ValueError, TypeError):
            return FitnessScore(feedback=f"Parse error: {text[:200]}")


def fast_heuristic_score(expected: str, actual: str) -> float:
    """Fast keyword-overlap scoring for optimization speed."""
    if not expected or not actual:
        return 0.0
    expected_words = set(expected.lower().split())
    actual_words = set(actual.lower().split())
    if not expected_words:
        return 0.5
    overlap = len(expected_words & actual_words) / len(expected_words)
    return 0.3 + 0.7 * overlap
