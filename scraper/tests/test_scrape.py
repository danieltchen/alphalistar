"""Tests for scrape.py orchestration and helpers."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import scrape
from scrape import SingleStockScraper, _build_parser, is_market_open_day
from fakes import FakeConnection, FakeCursor, make_company, make_filing, make_filings_collection


def _scraper(**kwargs) -> SingleStockScraper:
    defaults = dict(
        ticker="aapl",
        days=5,
        annual_limit=1,
        quarterly_limit=1,
        limit_8k=2,
        limit_10k=1,
        limit_10q=1,
        insider_limit=10,
        skip_market_check=True,
    )
    defaults.update(kwargs)
    return SingleStockScraper(**defaults)


class TestNormalizeFilingList:
    def test_none_returns_empty(self):
        assert SingleStockScraper._normalize_filing_list(None) == []

    def test_single_filing_object(self):
        f = make_filing()
        assert SingleStockScraper._normalize_filing_list(f) == [f]

    def test_list_passthrough(self):
        filings = [make_filing("a"), make_filing("b")]
        assert SingleStockScraper._normalize_filing_list(filings) == filings

    def test_scalar_wrapped(self):
        assert SingleStockScraper._normalize_filing_list(42) == [42]


class TestStockCursor:
    def test_formats_date(self, monkeypatch):
        monkeypatch.setattr(
            scrape.StockDataProcessor,
            "get_latest_processed_date",
            lambda self, tid: date(2024, 3, 15),
        )
        result = SingleStockScraper._stock_cursor({}, 1)
        assert result == {"latest_price_date": "2024-03-15"}

    def test_none_date(self, monkeypatch):
        monkeypatch.setattr(
            scrape.StockDataProcessor,
            "get_latest_processed_date",
            lambda self, tid: None,
        )
        result = SingleStockScraper._stock_cursor({}, 1)
        assert result == {"latest_price_date": None}


class _DateStub:
    """Minimal date stand-in exposing only today() for market-calendar tests."""

    def __init__(self, today_value: date) -> None:
        self._today = today_value

    def today(self) -> date:
        return self._today


class TestMarketOpenDay:
    def test_weekend_returns_false(self, monkeypatch):
        monkeypatch.setattr(scrape, "date", _DateStub(date(2024, 6, 8)))  # Saturday
        assert is_market_open_day() is False

    def test_weekday_returns_true(self, monkeypatch):
        monkeypatch.setattr(scrape, "date", _DateStub(date(2024, 6, 10)))  # Monday
        assert is_market_open_day() is True

    def test_holiday_returns_false(self, monkeypatch):
        monkeypatch.setattr(scrape, "date", _DateStub(date(2024, 7, 4)))  # Independence Day
        assert is_market_open_day() is False


class TestBuildParser:
    def test_defaults(self):
        args = _build_parser().parse_args(["AAPL"])
        assert args.ticker == "AAPL"
        assert args.days == 5
        assert args.annual_limit == 1
        assert args.limit_8k == 2
        assert args.insider_limit == 10
        assert args.skip_market_check is False
        assert args.force_press_releases is False

    def test_flags(self):
        args = _build_parser().parse_args(
            [
                "MSFT",
                "--days",
                "10",
                "--8k",
                "5",
                "--10k",
                "2",
                "--insiders",
                "20",
                "--skip-market-check",
                "--force-press-releases",
            ]
        )
        assert args.days == 10
        assert args.limit_8k == 5
        assert args.limit_10k == 2
        assert args.insider_limit == 20
        assert args.skip_market_check is True
        assert args.force_press_releases is True


class TestPreflightHelpers:
    def test_should_run_stocks_when_not_today(self, monkeypatch):
        monkeypatch.setattr(
            scrape.StockDataProcessor,
            "get_latest_processed_date",
            lambda self, tid: date(2024, 1, 1),
        )
        assert _scraper()._should_run_stocks({}, 1) is True

    def test_should_run_stocks_skip_when_today(self, monkeypatch):
        monkeypatch.setattr(scrape, "date", _DateStub(date(2024, 6, 10)))
        monkeypatch.setattr(
            scrape.StockDataProcessor,
            "get_latest_processed_date",
            lambda self, tid: date(2024, 6, 10),
        )
        assert _scraper()._should_run_stocks({}, 1) is False

    def test_should_run_press_releases_force_flag(self, monkeypatch):
        s = _scraper(force_press_releases=True)
        db = MagicMock()
        assert s._should_run_press_releases(db) is True

    def test_should_run_press_releases_no_accessions(self, monkeypatch):
        monkeypatch.setattr(scrape, "set_identity", lambda x: None)
        monkeypatch.setattr(scrape, "Company", lambda t: make_company())
        s = _scraper()
        db = MagicMock()
        assert s._should_run_press_releases(db) is False

    def test_should_run_press_releases_all_completed(self, monkeypatch):
        monkeypatch.setattr(scrape, "set_identity", lambda x: None)
        f = make_filing("acc-1")
        filings = make_filings_collection([f])
        monkeypatch.setattr(
            scrape,
            "Company",
            lambda t: make_company(filings_map={"8-K": filings, "10-K": make_filings_collection([])}),
        )
        conn = FakeConnection([FakeCursor(fetchone_results=[(1,)])])
        db = MagicMock()
        db.get_db_connection.return_value = conn
        s = _scraper(limit_8k=1, limit_10k=0)
        assert s._should_run_press_releases(db) is False

    def test_should_run_press_releases_partial_run(self, monkeypatch):
        monkeypatch.setattr(scrape, "set_identity", lambda x: None)
        filings = make_filings_collection([make_filing("acc-1"), make_filing("acc-2")])
        monkeypatch.setattr(
            scrape,
            "Company",
            lambda t: make_company(filings_map={"8-K": filings, "10-K": make_filings_collection([])}),
        )
        conn = FakeConnection([FakeCursor(fetchone_results=[(1,)])])
        db = MagicMock()
        db.get_db_connection.return_value = conn
        assert _scraper()._should_run_press_releases(db) is True

    def test_should_run_insiders_no_filings(self, monkeypatch):
        monkeypatch.setattr(scrape, "set_identity", lambda x: None)
        monkeypatch.setattr(scrape, "Company", lambda t: make_company())
        db = MagicMock()
        assert _scraper()._should_run_insiders(db) is False

    def test_should_run_insiders_all_completed(self, monkeypatch):
        monkeypatch.setattr(scrape, "set_identity", lambda x: None)
        f = make_filing("acc-insider")
        filings = make_filings_collection(f)
        monkeypatch.setattr(
            scrape,
            "Company",
            lambda t: make_company(
                filings_map={"3": filings, "4": make_filings_collection([]), "5": make_filings_collection([])}
            ),
        )
        conn = FakeConnection([FakeCursor(fetchone_results=[(1,)])])
        db = MagicMock()
        db.get_db_connection.return_value = conn
        assert _scraper()._should_run_insiders(db) is False

    def test_press_release_cursor_with_row(self):
        conn = FakeConnection(
            [FakeCursor(fetchone_results=[("acc-123", date(2024, 5, 1))])]
        )
        db = MagicMock()
        db.get_db_connection.return_value = conn
        result = _scraper()._press_release_cursor(db, 1)
        assert result["latest_completed_accession"] == "acc-123"
        assert result["latest_completed_filing_date"] == "2024-05-01"

    def test_press_release_cursor_empty(self):
        conn = FakeConnection([FakeCursor(fetchone_results=[None])])
        db = MagicMock()
        db.get_db_connection.return_value = conn
        assert _scraper()._press_release_cursor(db, 1) == {}

    def test_insider_cursor_with_row(self):
        conn = FakeConnection(
            [FakeCursor(fetchone_results=[("acc-456", date(2024, 4, 15))])]
        )
        db = MagicMock()
        db.get_db_connection.return_value = conn
        result = _scraper()._insider_cursor(db, 1)
        assert result["latest_completed_accession"] == "acc-456"

    def test_should_run_financials_new_annual(self, monkeypatch):
        monkeypatch.setattr(scrape, "set_identity", lambda x: None)
        annual = make_filing(filing_date=date(2024, 12, 31))
        monkeypatch.setattr(
            scrape,
            "Company",
            lambda t: make_company(latest_map={"10-K": annual, "10-Q": None}),
        )
        monkeypatch.setattr(
            scrape.LatestFinancialsProcessor,
            "get_latest_periods",
            lambda self, tid: {"annual_period": date(2023, 12, 31), "quarterly_period": None},
        )
        monkeypatch.setattr(
            scrape.LatestFinancialsProcessor,
            "get_filing_date",
            lambda self, f: date(2024, 12, 31),
        )
        assert _scraper()._should_run_financials({}, 1) is True

    def test_should_run_financials_up_to_date(self, monkeypatch):
        monkeypatch.setattr(scrape, "set_identity", lambda x: None)
        annual = make_filing()
        monkeypatch.setattr(
            scrape,
            "Company",
            lambda t: make_company(latest_map={"10-K": annual, "10-Q": None}),
        )
        monkeypatch.setattr(
            scrape.LatestFinancialsProcessor,
            "get_latest_periods",
            lambda self, tid: {"annual_period": date(2024, 12, 31), "quarterly_period": None},
        )
        monkeypatch.setattr(
            scrape.LatestFinancialsProcessor,
            "get_filing_date",
            lambda self, f: date(2024, 12, 31),
        )
        assert _scraper()._should_run_financials({}, 1) is False


class TestSingleStockScraperRun:
    def _patch_db(self, monkeypatch, quote_type="EQUITY"):
        db = MagicMock()
        db.get_ticker_id.return_value = 42
        db.get_quote_type.return_value = quote_type
        db.try_start_process_run.return_value = "lock-token"
        db.mark_process_run_success.return_value = True
        db.mark_process_run_failed.return_value = True
        db.get_db_connection.return_value = FakeConnection()

        class FakeDatabaseConnector:
            @staticmethod
            def get_db_config(**kw):
                return {}

            def __init__(self, cfg):
                self._db = db

            def __getattr__(self, name):
                return getattr(self._db, name)

        monkeypatch.setattr(scrape, "DatabaseConnector", FakeDatabaseConnector)
        return db

    def test_market_closed_early_exit(self, monkeypatch):
        monkeypatch.setattr(scrape, "is_market_open_day", lambda: False)
        called = {"db": False}

        def fake_db(*a, **k):
            called["db"] = True
            return MagicMock()

        monkeypatch.setattr(scrape, "DatabaseConnector", fake_db)
        _scraper(skip_market_check=False).run()
        assert called["db"] is False

    def test_happy_path_all_processors(self, monkeypatch):
        db = self._patch_db(monkeypatch)
        runs = []

        monkeypatch.setattr(scrape, "_scrape_stocks", lambda *a: runs.append("stocks"))
        monkeypatch.setattr(scrape, "_scrape_financials", lambda *a: runs.append("financials"))
        monkeypatch.setattr(scrape, "_scrape_insiders", lambda *a: runs.append("insiders"))

        async def fake_press_releases(*a, **k):
            runs.append("press")

        monkeypatch.setattr(scrape, "_scrape_press_releases", fake_press_releases)
        monkeypatch.setattr(SingleStockScraper, "_should_run_stocks", lambda self, *a: True)
        monkeypatch.setattr(SingleStockScraper, "_should_run_financials", lambda self, *a: True)
        monkeypatch.setattr(SingleStockScraper, "_should_run_press_releases", lambda self, *a: True)
        monkeypatch.setattr(SingleStockScraper, "_should_run_insiders", lambda self, *a: True)
        monkeypatch.setattr(
            scrape.StockDataProcessor,
            "get_latest_processed_date",
            lambda self, tid: date(2024, 1, 1),
        )
        monkeypatch.setattr(
            scrape.LatestFinancialsProcessor,
            "get_latest_periods",
            lambda self, tid: {},
        )

        _scraper().run()
        assert runs == ["stocks", "financials", "press", "insiders"]
        assert db.mark_process_run_success.call_count == 4

    def test_skip_when_should_run_false(self, monkeypatch):
        db = self._patch_db(monkeypatch)
        runs = []
        monkeypatch.setattr(scrape, "_scrape_stocks", lambda *a: runs.append("stocks"))
        monkeypatch.setattr(
            SingleStockScraper,
            "_should_run_stocks",
            lambda self, *a: False,
        )
        monkeypatch.setattr(
            SingleStockScraper,
            "_should_run_financials",
            lambda self, *a: False,
        )
        monkeypatch.setattr(
            SingleStockScraper,
            "_should_run_press_releases",
            lambda self, *a: False,
        )
        monkeypatch.setattr(
            SingleStockScraper,
            "_should_run_insiders",
            lambda self, *a: False,
        )
        _scraper().run()
        assert runs == []
        assert db.try_start_process_run.call_count == 0

    def test_skip_when_lock_not_acquired(self, monkeypatch):
        db = self._patch_db(monkeypatch)
        db.try_start_process_run.return_value = None
        runs = []
        monkeypatch.setattr(scrape, "_scrape_stocks", lambda *a: runs.append("stocks"))
        monkeypatch.setattr(SingleStockScraper, "_should_run_stocks", lambda self, *a: True)
        monkeypatch.setattr(SingleStockScraper, "_should_run_financials", lambda self, *a: False)
        monkeypatch.setattr(SingleStockScraper, "_should_run_press_releases", lambda self, *a: False)
        monkeypatch.setattr(SingleStockScraper, "_should_run_insiders", lambda self, *a: False)
        _scraper().run()
        assert runs == []
        assert db.mark_process_run_success.call_count == 0

    def test_processor_failure_marks_failed(self, monkeypatch):
        db = self._patch_db(monkeypatch)

        def boom(*a, **k):
            raise RuntimeError("scrape failed")

        monkeypatch.setattr(scrape, "_scrape_stocks", boom)
        monkeypatch.setattr(SingleStockScraper, "_should_run_stocks", lambda self, *a: True)
        monkeypatch.setattr(SingleStockScraper, "_should_run_financials", lambda self, *a: False)
        monkeypatch.setattr(SingleStockScraper, "_should_run_press_releases", lambda self, *a: False)
        monkeypatch.setattr(SingleStockScraper, "_should_run_insiders", lambda self, *a: False)
        _scraper().run()
        db.mark_process_run_failed.assert_called_once()
        assert "scrape failed" in db.mark_process_run_failed.call_args[0][3]

    def test_preflight_fail_open(self, monkeypatch):
        db = self._patch_db(monkeypatch)
        runs = []

        def should_fail(self, *a):
            raise ValueError("preflight error")

        monkeypatch.setattr(scrape, "_scrape_stocks", lambda *a: runs.append("stocks"))
        monkeypatch.setattr(SingleStockScraper, "_should_run_stocks", should_fail)
        monkeypatch.setattr(SingleStockScraper, "_should_run_financials", lambda self, *a: False)
        monkeypatch.setattr(SingleStockScraper, "_should_run_press_releases", lambda self, *a: False)
        monkeypatch.setattr(SingleStockScraper, "_should_run_insiders", lambda self, *a: False)
        _scraper().run()
        assert runs == ["stocks"]

    def test_edgar_ineligible_skips_edgar_processors(self, monkeypatch):
        db = self._patch_db(monkeypatch, quote_type="ETF")
        runs = []
        monkeypatch.setattr(scrape, "_scrape_stocks", lambda *a: runs.append("stocks"))
        monkeypatch.setattr(scrape, "_scrape_financials", lambda *a: runs.append("financials"))
        monkeypatch.setattr(scrape, "_scrape_press_releases", lambda *a: runs.append("press"))
        monkeypatch.setattr(scrape, "_scrape_insiders", lambda *a: runs.append("insiders"))

        for meth in (
            "_should_run_stocks",
            "_should_run_financials",
            "_should_run_press_releases",
            "_should_run_insiders",
        ):
            monkeypatch.setattr(SingleStockScraper, meth, lambda self, *a: True)

        _scraper().run()
        assert runs == ["stocks"]
        assert db.get_quote_type.call_count >= 1
