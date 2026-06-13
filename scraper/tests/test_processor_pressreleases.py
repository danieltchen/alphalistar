"""Tests for processor_pressreleases.py text and section helpers."""

from __future__ import annotations

import pytest

from processor_pressreleases import PressReleaseProcessor


class TestCleanFilingText:
    def test_empty(self):
        assert PressReleaseProcessor.clean_filing_text("") == ""

    def test_strips_html(self):
        result = PressReleaseProcessor.clean_filing_text("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert "Hello" in result
        assert "world" in result

    def test_collapses_whitespace(self):
        result = PressReleaseProcessor.clean_filing_text("  hello   world  ")
        assert result == "hello world"


class TestTextToMarkdown:
    def test_empty(self):
        assert PressReleaseProcessor.text_to_markdown("") == ""

    def test_all_caps_heading(self):
        result = PressReleaseProcessor.text_to_markdown("OVERVIEW\n\nSome text here.")
        assert "## OVERVIEW" in result

    def test_numbered_list(self):
        result = PressReleaseProcessor.text_to_markdown("1. First item\n2. Second item")
        assert "1." in result

    def test_bullet_list(self):
        result = PressReleaseProcessor.text_to_markdown("- Item one\n- Item two")
        assert "- Item one" in result

    def test_pipe_table(self):
        text = "| Col1 | Col2 |\n| a | b |"
        result = PressReleaseProcessor.text_to_markdown(text)
        assert "|" in result
        assert "---" in result


class TestExtractPressReleaseTitle:
    def test_skips_boilerplate(self):
        content = "FOR IMMEDIATE RELEASE\n\nApple announces record quarterly revenue"
        title = PressReleaseProcessor.extract_press_release_title(content)
        assert "Apple" in title

    def test_fallback(self):
        assert PressReleaseProcessor.extract_press_release_title("short") == "Press Release"

    def test_truncates_long_title(self):
        long_line = "A" * 250
        title = PressReleaseProcessor.extract_press_release_title(long_line)
        assert len(title) == 200


class TestNormalizeItemKey:
    def test_item_7a(self):
        assert PressReleaseProcessor._normalize_item_key("Item 7A") == "item7a"


class TestResolveMdnaSections:
    def test_10k_defaults_when_no_items(self):
        processor = PressReleaseProcessor.__new__(PressReleaseProcessor)
        resolved = processor._resolve_mdna_sections(object(), "10-K")
        assert len(resolved) == 2
        assert resolved[0][0] == "Item 7"

    def test_10q_single_section(self):
        processor = PressReleaseProcessor.__new__(PressReleaseProcessor)
        resolved = processor._resolve_mdna_sections(object(), "10-Q")
        assert len(resolved) == 1
        assert resolved[0][0] == "Item 2"

    def test_unknown_form_empty(self):
        processor = PressReleaseProcessor.__new__(PressReleaseProcessor)
        assert processor._resolve_mdna_sections(object(), "8-K") == []


class TestGetSectionContent:
    def test_returns_first_available(self):
        processor = PressReleaseProcessor.__new__(PressReleaseProcessor)

        class Filing:
            def __getitem__(self, key):
                if key == "Item 7":
                    return "MD&A content here"
                raise KeyError(key)

        content = processor._get_section_content(Filing(), ["Item 7", "item_7"])
        assert content == "MD&A content here"

    def test_none_when_missing(self):
        processor = PressReleaseProcessor.__new__(PressReleaseProcessor)

        class Filing:
            def __getitem__(self, key):
                raise KeyError(key)

        assert processor._get_section_content(Filing(), ["Item 7"]) is None


class TestAvailableSectionKeys:
    def test_dict_sections(self):
        class Filing:
            sections = {"Item 7": "content", "Item 7A": "risk"}

        keys = PressReleaseProcessor._available_section_keys(Filing())
        assert "Item 7" in keys

    def test_callable_sections(self):
        class Filing:
            def sections(self):
                return ["Item 7"]

        keys = PressReleaseProcessor._available_section_keys(Filing())
        assert "Item 7" in keys
