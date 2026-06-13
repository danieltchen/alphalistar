"""Tests for parser_financial.py pure helpers."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from parser_financial import FinancialDataParser, _CandidateFact


@pytest.fixture
def annual_parser():
    empty = pd.DataFrame()
    return FinancialDataParser(
        income_statement=empty,
        balance_sheet=empty,
        cashflow=empty,
        ticker_id=1,
        is_annual=True,
    )


@pytest.fixture
def quarterly_parser():
    empty = pd.DataFrame()
    return FinancialDataParser(
        income_statement=empty,
        balance_sheet=empty,
        cashflow=empty,
        ticker_id=1,
        is_annual=False,
    )


class TestFindColumn:
    def test_case_insensitive(self):
        df = pd.DataFrame(columns=["Concept", "Label"])
        assert FinancialDataParser._find_column(df, "concept") == "Concept"

    def test_missing(self):
        df = pd.DataFrame(columns=["foo"])
        assert FinancialDataParser._find_column(df, "concept") is None


class TestMetadataColumn:
    def test_known_metadata(self, annual_parser):
        assert annual_parser._is_metadata_column("decimals") is True
        assert annual_parser._is_metadata_column("  Concept  ") is True

    def test_period_not_metadata(self, annual_parser):
        assert annual_parser._is_metadata_column("2024-12-31") is False


class TestGetPeriodColumns:
    def test_filters_metadata(self, annual_parser):
        df = pd.DataFrame(
            {"concept": ["Assets"], "2024-12-31": [100], "decimals": [0]},
            index=[0],
        )
        periods = annual_parser._get_period_columns(df)
        assert "2024-12-31" in [str(p) for p in periods]
        assert "decimals" not in [str(p) for p in periods]


class TestDetermineFiscalPeriodEnd:
    def test_annual(self, annual_parser):
        ts = pd.Timestamp("2024-06-15")
        assert annual_parser._determine_fiscal_period_end(ts) == date(2024, 12, 31)

    def test_q1_quarterly(self, quarterly_parser):
        ts = pd.Timestamp("2024-02-15")
        assert quarterly_parser._determine_fiscal_period_end(ts) == date(2024, 3, 31)

    def test_q4_quarterly(self, quarterly_parser):
        ts = pd.Timestamp("2024-11-15")
        assert quarterly_parser._determine_fiscal_period_end(ts) == date(2024, 12, 31)


class TestRowIsAbstract:
    def test_no_column(self):
        row = pd.Series({"a": 1})
        assert FinancialDataParser._row_is_abstract(row, None) is False

    def test_true_abstract(self):
        row = pd.Series({"is_abstract": True})
        assert FinancialDataParser._row_is_abstract(row, "is_abstract") is True


class TestSafeConversions:
    def test_safe_int_optional(self):
        assert FinancialDataParser._safe_int_optional(None) is None
        assert FinancialDataParser._safe_int_optional(float("nan")) is None
        assert FinancialDataParser._safe_int_optional("1.9") == 1
        assert FinancialDataParser._safe_int_optional("bad") is None

    def test_safe_str_optional(self):
        assert FinancialDataParser._safe_str_optional("  hello  ") == "hello"
        assert FinancialDataParser._safe_str_optional("   ") is None

    def test_extract_numeric(self, annual_parser):
        assert annual_parser._extract_numeric(1000) == 1000
        assert annual_parser._extract_numeric("1000.0") == 1000
        assert annual_parser._extract_numeric(None) is None
        assert annual_parser._extract_numeric("not-a-number") is None


class TestMergeCandidates:
    def _fact(self, line_code, value, concept, anchored=False):
        return _CandidateFact(
            ticker_id=1,
            fiscal_year=2024,
            fiscal_period_end=date(2024, 12, 31),
            period_type="annual",
            quarter=None,
            line_code=line_code,
            value=value,
            decimals=None,
            unit=None,
            scale=None,
            source_concept=concept,
            source_standard_concept=None,
            filing_accession=None,
            anchored=anchored,
        )

    def test_single_candidate_passthrough(self):
        c = self._fact("revenue", 100, "Revenues")
        assert FinancialDataParser._merge_candidates([c]) == [c]

    def test_merge_prefers_anchored(self):
        a = self._fact("net_income", 100, "OtherIncome", anchored=False)
        b = self._fact("net_income", 200, "NetIncomeLoss", anchored=True)
        merged = FinancialDataParser._merge_candidates([a, b])
        assert len(merged) == 1
        assert merged[0].value == 200


class TestExtractFinancialFacts:
    def test_maps_revenue_row(self):
        df = pd.DataFrame(
            {
                "concept": ["us-gaap:Revenues"],
                "standard_concept": ["Revenues"],
                "2024-12-31": [1_000_000],
            }
        )
        parser = FinancialDataParser(
            income_statement=df,
            balance_sheet=pd.DataFrame(),
            cashflow=pd.DataFrame(),
            ticker_id=1,
            is_annual=True,
            filing_accession="acc-1",
        )
        facts = parser.extract_financial_facts()
        assert len(facts) >= 1
        assert facts[0]["line_code"] == "revenue"
        assert facts[0]["value"] == 1_000_000

    def test_build_processing_result(self):
        df = pd.DataFrame(
            {
                "concept": ["us-gaap:Revenues"],
                "standard_concept": ["Revenues"],
                "2024-12-31": [500],
            }
        )
        parser = FinancialDataParser(
            income_statement=df,
            balance_sheet=pd.DataFrame(),
            cashflow=pd.DataFrame(),
            ticker_id=1,
            is_annual=True,
        )
        result = parser.build_processing_result()
        assert "FINANCIAL_FACT" in result
        ddl, inserts = result["FINANCIAL_FACT"]
        assert "CREATE TABLE" in ddl
        assert len(inserts) >= 1
