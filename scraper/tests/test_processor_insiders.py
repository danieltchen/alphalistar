"""Tests for processor_insiders.py coercion and normalization helpers."""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from processor_insiders import InsiderTransactionsProcessor


class TestIsMissing:
    def test_none(self):
        assert InsiderTransactionsProcessor._is_missing(None) is True

    def test_nan(self):
        assert InsiderTransactionsProcessor._is_missing(float("nan")) is True

    def test_zero_not_missing(self):
        assert InsiderTransactionsProcessor._is_missing(0) is False


class TestCleanText:
    def test_whitespace_stripped(self):
        assert InsiderTransactionsProcessor._clean_text("  hello  ") == "hello"

    def test_empty_after_strip(self):
        assert InsiderTransactionsProcessor._clean_text("   ") is None

    def test_none(self):
        assert InsiderTransactionsProcessor._clean_text(None) is None


class TestToDate:
    def test_date_passthrough(self):
        d = date(2024, 3, 15)
        assert InsiderTransactionsProcessor._to_date(d) == d

    def test_datetime(self):
        assert InsiderTransactionsProcessor._to_date(datetime(2024, 3, 15, 10, 0)) == date(
            2024, 3, 15
        )

    def test_iso_string(self):
        assert InsiderTransactionsProcessor._to_date("2024-03-15T12:00:00") == date(2024, 3, 15)

    def test_invalid(self):
        assert InsiderTransactionsProcessor._to_date("not-a-date") is None


class TestToDecimal:
    def test_valid(self):
        assert InsiderTransactionsProcessor._to_decimal("1.5") == Decimal("1.5")

    def test_invalid(self):
        assert InsiderTransactionsProcessor._to_decimal("abc") is None


class TestToInt:
    def test_truncates(self):
        assert InsiderTransactionsProcessor._to_int("1.9") == 1

    def test_none(self):
        assert InsiderTransactionsProcessor._to_int(None) is None


class TestGetFirst:
    def test_dict_hit(self):
        assert InsiderTransactionsProcessor._get_first({"a": 1, "b": 2}, "a", "b") == 1

    def test_object_attr(self):
        class Obj:
            name = "Tim"

        assert InsiderTransactionsProcessor._get_first(Obj(), "name") == "Tim"

    def test_missing(self):
        assert InsiderTransactionsProcessor._get_first({}, "x") is None


class TestAccessionNo:
    def test_accession_no_attr(self):
        class F:
            accession_no = "acc-1"

        assert InsiderTransactionsProcessor._accession_no(F()) == "acc-1"

    def test_accession_number_alias(self):
        class F:
            accession_number = "acc-2"

        assert InsiderTransactionsProcessor._accession_no(F()) == "acc-2"


class TestFormType:
    def test_strips_form_prefix(self):
        class F:
            form = "Form 4"

        assert InsiderTransactionsProcessor._form_type(F(), None) == "4"

    def test_amendment(self):
        class F:
            form = "Form 4/A"

        assert InsiderTransactionsProcessor._form_type(F(), None) == "4/A"


class TestNormalizeFilingList:
    def test_none(self):
        assert InsiderTransactionsProcessor._normalize_filing_list(None) == []

    def test_single_with_accession(self):
        class F:
            accession_no = "x"

        result = InsiderTransactionsProcessor._normalize_filing_list(F())
        assert len(result) == 1


class TestTransactionRowsFromDataframe:
    def test_form3_holding_row(self):
        processor = InsiderTransactionsProcessor({"dbname": "x", "host": "h", "user": "u", "password": "p", "port": "5432"})
        df = pd.DataFrame(
            [
                {
                    "Form": "3",
                    "Security Type": "Common Stock",
                    "Shares": "1000",
                    "Ownership Type": "Direct",
                    "Date": "2024-01-15",
                }
            ]
        )

        class FilingObj:
            def to_dataframe(self):
                return df

        rows = processor._transaction_rows_from_dataframe(FilingObj())
        assert len(rows) == 1
        assert rows[0]["transaction_code"] == "H"
        assert rows[0]["ownership"] == "D"
        assert rows[0]["shares"] == Decimal("1000")

    def test_derivative_security(self):
        processor = InsiderTransactionsProcessor({"dbname": "x", "host": "h", "user": "u", "password": "p", "port": "5432"})
        df = pd.DataFrame(
            [
                {
                    "Form": "4",
                    "Security Type": "Stock Option (derivative)",
                    "Shares": "500",
                    "Underlying Shares": "500",
                    "Date": "2024-02-01",
                }
            ]
        )

        class FilingObj:
            def to_dataframe(self):
                return df

        rows = processor._transaction_rows_from_dataframe(FilingObj())
        assert rows[0]["is_derivative"] is True

    def test_empty_dataframe(self):
        processor = InsiderTransactionsProcessor({"dbname": "x", "host": "h", "user": "u", "password": "p", "port": "5432"})

        class FilingObj:
            def to_dataframe(self):
                return pd.DataFrame()

        assert processor._transaction_rows_from_dataframe(FilingObj()) == []
