"""Tests for concept_mapper.py and financial_gaap_map.py."""

from __future__ import annotations

import concept_mapper
from concept_mapper import (
    infer_standard_concept,
    iter_lookup_keys,
    map_to_line_code,
    normalize_xbrl_name,
    reload_overrides,
)
from financial_gaap_map import GAAP_MAP


class TestNormalizeXbrlName:
    def test_none(self):
        assert normalize_xbrl_name(None) == ""

    def test_namespace_braces(self):
        assert normalize_xbrl_name("{http://fasb.org/us-gaap/2024}Assets") == "assets"

    def test_colon_prefix(self):
        assert normalize_xbrl_name("us-gaap:Revenues") == "revenues"

    def test_underscore_prefix(self):
        assert normalize_xbrl_name("us-gaap_Revenues") == "usgaaprevenues"


class TestInferStandardConcept:
    def test_none(self):
        assert infer_standard_concept(None) is None

    def test_us_gaap_underscore(self):
        assert infer_standard_concept("us-gaap_EarningsPerShareBasic") == "EarningsPerShareBasic"

    def test_colon_prefix(self):
        assert infer_standard_concept("us-gaap:Assets") == "Assets"

    def test_plain_concept(self):
        assert infer_standard_concept("Revenues") is None


class TestIterLookupKeys:
    def test_empty(self):
        assert iter_lookup_keys("") == []

    def test_strips_usgaap_prefix(self):
        keys = iter_lookup_keys("usgaaprevenues")
        assert "revenues" in keys
        assert "usgaaprevenues" in keys


class TestMapToLineCode:
    def setup_method(self):
        reload_overrides()

    def test_standard_concept_match(self):
        assert map_to_line_code(
            concept="us-gaap:Revenues",
            standard_concept="Revenues",
            statement="income",
        ) == "revenue"

    def test_statement_mismatch_returns_none(self):
        assert map_to_line_code(
            concept="us-gaap:Revenues",
            standard_concept="Revenues",
            statement="balance",
        ) is None

    def test_concept_fallback(self):
        assert map_to_line_code(
            concept="us-gaap:NetIncomeLoss",
            standard_concept=None,
            statement="income",
        ) == "net_income"

    def test_override_hit(self, monkeypatch):
        monkeypatch.setattr(
            concept_mapper,
            "get_overrides",
            lambda: {"custommetric": "revenue"},
        )
        assert map_to_line_code(
            concept="custom:CustomMetric",
            standard_concept="CustomMetric",
            statement="income",
        ) == "revenue"

    def test_issuer_extension_tag(self):
        result = map_to_line_code(
            concept="aapl_SomeExtensionTag",
            standard_concept=None,
            statement="income",
        )
        # May be None if extension doesn't map; test doesn't crash
        assert result is None or isinstance(result, str)


class TestGaapMapInvariants:
    def test_all_statements_valid(self):
        valid = {"balance", "income", "cashflow"}
        for key, (line_code, statement) in GAAP_MAP.items():
            assert statement in valid, f"{key} has invalid statement {statement}"
            assert line_code, f"{key} has empty line_code"

    def test_keys_are_normalized(self):
        for key in GAAP_MAP:
            assert key == normalize_xbrl_name(key) or key == "".join(
                c.lower() for c in key if c.isalnum()
            )

    def test_known_mapping(self):
        assert GAAP_MAP["revenues"] == ("revenue", "income")
        assert GAAP_MAP["assets"] == ("total_assets", "balance")
