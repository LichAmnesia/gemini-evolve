"""Tests for JSON extraction from LLM responses."""

from gemini_evolve.json_utils import extract_json


def test_raw_json_object():
    assert extract_json('{"key": "value"}') == {"key": "value"}


def test_raw_json_array():
    assert extract_json('[1, 2, 3]') == [1, 2, 3]


def test_code_fence_json():
    text = '```json\n{"key": "value"}\n```'
    assert extract_json(text) == {"key": "value"}


def test_prose_before_code_fence():
    text = 'Here is the score:\n```json\n{"correctness": 0.5}\n```'
    assert extract_json(text) == {"correctness": 0.5}


def test_prose_after_code_fence():
    text = '```json\n[{"a": 1}]\n```\nHere are the examples.'
    assert extract_json(text) == [{"a": 1}]


def test_prose_both_sides():
    text = 'Result:\n```json\n{"x": 42}\n```\nDone!'
    assert extract_json(text) == {"x": 42}


def test_no_json_fence_label():
    text = '```\n{"key": "value"}\n```'
    assert extract_json(text) == {"key": "value"}


def test_embedded_object_no_fences():
    text = 'The answer is {"result": true} end.'
    assert extract_json(text) == {"result": True}


def test_embedded_array_no_fences():
    text = 'Items: [1, 2, 3] done.'
    assert extract_json(text) == [1, 2, 3]


def test_empty_input():
    assert extract_json("") is None
    assert extract_json(None) is None


def test_no_json_at_all():
    assert extract_json("just plain text with no json") is None


def test_invalid_json():
    assert extract_json('{"broken": }') is None
