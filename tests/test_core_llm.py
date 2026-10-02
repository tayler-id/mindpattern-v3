"""core.llm.extract_json salvages JSON from bare, fenced, or embedded model output."""

from core.llm import extract_json


class TestExtractJson:
    def test_bare_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert extract_json('Here:\n```json\n{"a": 1}\n```\ndone') == {"a": 1}

    def test_embedded_json(self):
        assert extract_json('The answer is {"a": 1} as requested.') == {"a": 1}

    def test_garbage_returns_none(self):
        assert extract_json("no json here at all") is None
