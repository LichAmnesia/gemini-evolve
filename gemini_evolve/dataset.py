"""Evaluation dataset generation and management."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from .cli_runner import run_gemini_cli
from .json_utils import extract_json


@dataclass
class EvalExample:
    task_input: str
    expected_behavior: str
    source: str = "synthetic"

    def to_dict(self) -> dict:
        return {
            "task_input": self.task_input,
            "expected_behavior": self.expected_behavior,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> EvalExample:
        return cls(
            task_input=d["task_input"],
            expected_behavior=d["expected_behavior"],
            source=d.get("source", "unknown"),
        )


@dataclass
class EvalDataset:
    train: list[EvalExample] = field(default_factory=list)
    val: list[EvalExample] = field(default_factory=list)
    holdout: list[EvalExample] = field(default_factory=list)

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        for split_name, examples in [
            ("train", self.train),
            ("val", self.val),
            ("holdout", self.holdout),
        ]:
            path = directory / f"{split_name}.jsonl"
            with open(path, "w") as f:
                for ex in examples:
                    f.write(json.dumps(ex.to_dict()) + "\n")

    @classmethod
    def load(cls, directory: Path) -> EvalDataset:
        ds = cls()
        for split_name in ("train", "val", "holdout"):
            path = directory / f"{split_name}.jsonl"
            if path.exists():
                examples = []
                for line in path.read_text().strip().split("\n"):
                    if line:
                        examples.append(EvalExample.from_dict(json.loads(line)))
                setattr(ds, split_name, examples)
        return ds


DATASET_GEN_PROMPT = """\
You are generating evaluation tasks for AI agent instructions.

Given these system instructions, generate {count} diverse test scenarios.
Each scenario has:
- task_input: A realistic user request that these instructions should handle
- expected_behavior: What a good agent response would include (rubric, not exact output)

Cover edge cases, typical usage, and boundary conditions.

Instructions to evaluate:
---
{instructions}
---

Respond with ONLY a JSON array:
[{{"task_input": "...", "expected_behavior": "..."}}, ...]
"""


class SyntheticDatasetBuilder:
    """Generates evaluation datasets using Gemini CLI."""

    def __init__(self, model: str | None = None):
        self.model = model

    def generate(
        self,
        instructions: str,
        count: int = 10,
        train_ratio: float = 0.5,
        val_ratio: float = 0.25,
    ) -> EvalDataset:
        prompt = DATASET_GEN_PROMPT.format(count=count, instructions=instructions)
        result = run_gemini_cli(
            prompt=prompt,
            model=self.model,
            timeout_seconds=120,
        )
        if not result.ok:
            return EvalDataset()

        examples = self._parse_examples(result.response)
        random.shuffle(examples)
        return self._split(examples, train_ratio, val_ratio)

    def _parse_examples(self, text: str) -> list[EvalExample]:
        data = extract_json(text)
        if data is None or not isinstance(data, list):
            return []
        examples = []
        for item in data:
            if isinstance(item, dict) and "task_input" in item and "expected_behavior" in item:
                examples.append(
                    EvalExample(
                        task_input=item["task_input"],
                        expected_behavior=item["expected_behavior"],
                        source="synthetic",
                    )
                )
        return examples

    def _split(
        self,
        examples: list[EvalExample],
        train_ratio: float,
        val_ratio: float,
    ) -> EvalDataset:
        n = len(examples)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)
        return EvalDataset(
            train=examples[:train_end],
            val=examples[train_end:val_end],
            holdout=examples[val_end:],
        )


class GoldenDatasetLoader:
    """Loads hand-curated evaluation datasets from JSONL files."""

    @staticmethod
    def load(
        path: Path,
        train_ratio: float = 0.5,
        val_ratio: float = 0.25,
    ) -> EvalDataset:
        examples = []
        for line in path.read_text().strip().split("\n"):
            if line:
                examples.append(EvalExample.from_dict(json.loads(line)))
        random.shuffle(examples)
        n = len(examples)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)
        return EvalDataset(
            train=examples[:train_end],
            val=examples[train_end:val_end],
            holdout=examples[val_end:],
        )
