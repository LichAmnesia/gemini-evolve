"""Tests for dataset management."""

import json
from pathlib import Path

from gemini_evolve.dataset import EvalExample, EvalDataset


def test_eval_example_roundtrip():
    ex = EvalExample(
        task_input="test input",
        expected_behavior="expected output",
        source="test",
    )
    d = ex.to_dict()
    ex2 = EvalExample.from_dict(d)
    assert ex2.task_input == ex.task_input
    assert ex2.expected_behavior == ex.expected_behavior
    assert ex2.source == ex.source


def test_dataset_save_load(tmp_path: Path):
    ds = EvalDataset(
        train=[EvalExample("t1", "e1"), EvalExample("t2", "e2")],
        val=[EvalExample("v1", "ev1")],
        holdout=[EvalExample("h1", "eh1")],
    )
    ds.save(tmp_path / "test_ds")
    loaded = EvalDataset.load(tmp_path / "test_ds")
    assert len(loaded.train) == 2
    assert len(loaded.val) == 1
    assert len(loaded.holdout) == 1
    assert loaded.train[0].task_input == "t1"


def test_dataset_save_creates_jsonl(tmp_path: Path):
    ds = EvalDataset(train=[EvalExample("t1", "e1")])
    ds.save(tmp_path / "ds")
    train_file = tmp_path / "ds" / "train.jsonl"
    assert train_file.exists()
    line = train_file.read_text().strip()
    data = json.loads(line)
    assert data["task_input"] == "t1"
