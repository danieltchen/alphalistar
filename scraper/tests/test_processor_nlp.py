"""Tests for processor_nlp.py text helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from processor_nlp import NlpProcessor, safe_sent_tokenize


class TestCleanText:
    def test_empty(self):
        assert NlpProcessor._clean_text("") == ""

    def test_collapses_whitespace(self):
        assert NlpProcessor._clean_text("hello\n\nworld") == "hello world"

    def test_tabs_and_spaces(self):
        assert NlpProcessor._clean_text("  a   b  ") == "a b"


class TestSafeSentTokenize:
    def test_simple_sentences(self):
        text = "Hello world. How are you? Fine thanks."
        sentences = safe_sent_tokenize(text)
        assert len(sentences) >= 2

    def test_regex_fallback_on_nltk_failure(self):
        with patch("processor_nlp.nltk.sent_tokenize", side_effect=LookupError("no data")):
            text = "First sentence. Second sentence."
            sentences = safe_sent_tokenize(text)
            assert len(sentences) >= 1

    def test_empty_string(self):
        assert safe_sent_tokenize("") == []


class TestChunkText:
    @pytest.fixture
    def processor(self):
        client = MagicMock()
        with patch.object(NlpProcessor, "_setup_nltk"):
            return NlpProcessor(client)

    def test_single_chunk_short_text(self, processor):
        chunks = processor.chunk_text("Short text.", token_count=1000)
        assert len(chunks) >= 1
        assert "Short" in chunks[0]

    def test_multiple_chunks(self, processor):
        # Build text long enough to exceed small token limit
        text = " ".join(["This is sentence number {}.".format(i) for i in range(50)])
        chunks = processor.chunk_text(text, token_count=50)
        assert len(chunks) >= 2

    def test_empty_text(self, processor):
        chunks = processor.chunk_text("", token_count=100)
        assert chunks == []
