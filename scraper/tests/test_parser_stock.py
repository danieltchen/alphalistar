"""Tests for parser_stock.py pure helpers."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from parser_stock import StockPriceDataParser


@pytest.fixture
def parser():
    return StockPriceDataParser(symbol="AAPL", ticker_id=1)


class TestEpochSecondsToDate:
    def test_none(self):
        assert StockPriceDataParser._epoch_seconds_to_date(None) is None

    def test_invalid(self):
        assert StockPriceDataParser._epoch_seconds_to_date("not-a-number") is None

    def test_zero_or_negative(self):
        assert StockPriceDataParser._epoch_seconds_to_date(0) is None
        assert StockPriceDataParser._epoch_seconds_to_date(-1) is None

    def test_valid_epoch(self):
        # 2020-01-01 00:00:00 UTC
        result = StockPriceDataParser._epoch_seconds_to_date(1577836800)
        assert isinstance(result, date)


class TestBuildTickerProfile:
    def test_none_info(self, parser):
        assert parser.build_ticker_profile(None) is None

    def test_maps_fields(self, parser):
        profile = parser.build_ticker_profile(
            {"shortName": "Apple", "quoteType": "EQUITY", "fundInceptionDate": None}
        )
        assert profile is not None
        assert profile["name"] == "Apple"
        assert profile["quote_type"] == "EQUITY"
        assert profile["fund_inception_date"] is None


class TestConvertToDate:
    def test_date_passthrough(self, parser):
        d = date(2024, 1, 15)
        assert parser._convert_to_date(d) == d

    def test_datetime_subclass_returns_as_is(self, parser):
        # datetime is a date subclass; first branch returns it unchanged
        dt = datetime(2024, 1, 15, 10, 0)
        assert parser._convert_to_date(dt) == dt

    def test_timestamp_subclass_returns_as_is(self, parser):
        ts = pd.Timestamp("2024-01-15")
        assert parser._convert_to_date(ts) == ts

    def test_string_parsed_to_date(self, parser):
        assert parser._convert_to_date("2024-01-15") == date(2024, 1, 15)


class TestProcessPriceData:
    def test_single_row(self, parser):
        df = pd.DataFrame(
            {"Open": [100.0], "High": [110.0], "Low": [90.0], "Close": [105.0], "Volume": [1000]},
            index=[pd.Timestamp("2024-01-15")],
        )
        create_sql, inserts = parser.process_price_data(df)
        assert "CREATE TABLE" in create_sql
        assert len(inserts) == 1
        _, values = inserts[0]
        assert values[0] == 1  # ticker_id
        assert values[2] == 100.0  # open

    def test_empty_dataframe(self, parser):
        df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        _, inserts = parser.process_price_data(df)
        assert inserts == []


class TestProcessSplitData:
    def test_split_row(self, parser):
        df = pd.DataFrame({"ratio": [4.0]}, index=[pd.Timestamp("2024-06-01")])
        _, inserts = parser.process_split_data(df)
        assert len(inserts) == 1
        assert inserts[0][1][2] == 4.0


class TestGetValueOrDefault:
    def test_missing_returns_default(self, parser):
        assert parser._get_value_or_default({}, "missing", 0) == 0

    def test_none_returns_default(self, parser):
        assert parser._get_value_or_default({"k": None}, "k", "x") == "x"

    def test_list_returns_default(self, parser):
        assert parser._get_value_or_default({"k": [1, 2]}, "k", 0) == 0

    def test_scalar_returned(self, parser):
        assert parser._get_value_or_default({"k": 42}, "k", 0) == 42


class TestGetOptionalValue:
    def test_missing(self):
        assert StockPriceDataParser._get_optional_value({}, "x") is None

    def test_dict_rejected(self):
        assert StockPriceDataParser._get_optional_value({"x": {"a": 1}}, "x") is None

    def test_string_returned(self):
        assert StockPriceDataParser._get_optional_value({"x": "hello"}, "x") == "hello"


class TestProcessFundamentals:
    def test_with_fixed_date(self, parser):
        create_sql, inserts = parser.process_fundamentals(
            {"marketCap": 1_000_000}, as_of_date=date(2024, 1, 1)
        )
        assert "FUNDAMENTALS" in create_sql
        assert len(inserts) == 1
        assert inserts[0][1][1] == date(2024, 1, 1)

    def test_empty_info_still_inserts(self, parser):
        _, inserts = parser.process_fundamentals({}, as_of_date=date(2024, 1, 1))
        assert len(inserts) == 1
