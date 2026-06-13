"""Tests for hydrate.py execution and routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import hydrate


class TestMainRouting:
    def test_incremental_delegates_to_scraper(self, monkeypatch):
        run_called = {}

        class FakeScraper:
            def __init__(self, **kwargs):
                run_called["kwargs"] = kwargs

            def run(self):
                run_called["ran"] = True

        monkeypatch.setattr(hydrate, "SingleStockScraper", FakeScraper)
        monkeypatch.setattr(hydrate, "hydrate_stock", lambda **k: (_ for _ in ()).throw(AssertionError("should not run")))

        hydrate.main(ticker="AAPL", start_date="2020-01-01", mode="incremental", days=7)

        assert run_called["ran"] is True
        assert run_called["kwargs"]["ticker"] == "AAPL"
        assert run_called["kwargs"]["skip_market_check"] is True
        assert run_called["kwargs"]["days"] == 7

    def test_full_equity_runs_all_steps(self, monkeypatch):
        order = []

        monkeypatch.setattr(hydrate, "hydrate_stock", lambda **k: order.append("stock"))
        monkeypatch.setattr(hydrate, "hydrate_financials", lambda **k: order.append("financials"))
        async def fake_press_releases(**k):
            order.append("press")

        monkeypatch.setattr(hydrate, "hydrate_press_releases", fake_press_releases)
        monkeypatch.setattr(hydrate, "hydrate_insiders", lambda **k: order.append("insiders"))
        db = MagicMock()
        db.get_ticker_id.return_value = 1
        db.get_quote_type.return_value = "EQUITY"

        class FakeDatabaseConnector:
            @staticmethod
            def get_db_config():
                return {}

            def __init__(self, cfg):
                self._db = db

            def __getattr__(self, name):
                return getattr(self._db, name)

        monkeypatch.setattr(hydrate, "DatabaseConnector", FakeDatabaseConnector)
        monkeypatch.setattr(hydrate, "is_edgar_eligible", lambda qt: True)

        hydrate.main(ticker="AAPL", start_date="2020-01-01", mode="full")

        assert order == ["stock", "financials", "press", "insiders"]

    def test_full_non_equity_skips_edgar(self, monkeypatch):
        order = []

        monkeypatch.setattr(hydrate, "hydrate_stock", lambda **k: order.append("stock"))
        monkeypatch.setattr(
            hydrate,
            "hydrate_financials",
            lambda **k: order.append("financials"),
        )
        db = MagicMock()
        db.get_ticker_id.return_value = 1
        db.get_quote_type.return_value = "ETF"

        class FakeDatabaseConnector:
            @staticmethod
            def get_db_config():
                return {}

            def __init__(self, cfg):
                self._db = db

            def __getattr__(self, name):
                return getattr(self._db, name)

        monkeypatch.setattr(hydrate, "DatabaseConnector", FakeDatabaseConnector)
        monkeypatch.setattr(hydrate, "is_edgar_eligible", lambda qt: False)

        hydrate.main(ticker="SPY", start_date="2020-01-01", mode="full")

        assert order == ["stock"]

    def test_exception_propagates(self, monkeypatch):
        def boom(**k):
            raise RuntimeError("hydrate boom")

        monkeypatch.setattr(hydrate, "hydrate_stock", boom)
        with pytest.raises(RuntimeError, match="hydrate boom"):
            hydrate.main(ticker="AAPL", start_date="2020-01-01", mode="full")


class TestHydrateWrappers:
    def test_hydrate_stock_success(self, monkeypatch):
        processor = MagicMock()
        monkeypatch.setattr(hydrate.DatabaseConnector, "get_db_config", staticmethod(lambda: {"host": "x"}))
        monkeypatch.setattr(hydrate, "StockDataProcessor", lambda cfg: processor)

        hydrate.hydrate_stock("AAPL", "2020-01-01")
        processor.process_stock.assert_called_once_with(ticker="AAPL", start_date="2020-01-01")

    def test_hydrate_stock_reraises(self, monkeypatch):
        processor = MagicMock()
        processor.process_stock.side_effect = ValueError("fail")
        monkeypatch.setattr(hydrate.DatabaseConnector, "get_db_config", staticmethod(lambda: {}))
        monkeypatch.setattr(hydrate, "StockDataProcessor", lambda cfg: processor)

        with pytest.raises(ValueError, match="fail"):
            hydrate.hydrate_stock("AAPL", "2020-01-01")

    def test_hydrate_financials_success(self, monkeypatch):
        processor = MagicMock()
        monkeypatch.setattr(hydrate.DatabaseConnector, "get_db_config", staticmethod(lambda: {}))
        monkeypatch.setattr(hydrate, "FinancialsProcessor", lambda cfg: processor)

        hydrate.hydrate_financials("AAPL", "2020-01-01", annual_limit=3, quarterly_limit=10)
        processor.process_company.assert_called_once_with(
            ticker="AAPL", annual_limit=3, quarterly_limit=10
        )

    @pytest.mark.asyncio
    async def test_hydrate_press_releases_success(self, monkeypatch):
        processor = MagicMock()
        processor.process_company = AsyncMock()
        monkeypatch.setattr(hydrate, "get_openai_api_key", lambda: "test-key")
        monkeypatch.setattr(hydrate.DatabaseConnector, "get_db_config", staticmethod(lambda: {}))
        monkeypatch.setattr(hydrate, "PressReleaseProcessor", lambda cfg, client: processor)

        await hydrate.hydrate_press_releases("AAPL", "2020-01-01", limit_8k=5)
        processor.process_company.assert_awaited_once()

    def test_hydrate_insiders_success(self, monkeypatch):
        processor = MagicMock()
        monkeypatch.setattr(hydrate.DatabaseConnector, "get_db_config", staticmethod(lambda: {}))
        monkeypatch.setattr(hydrate, "InsiderTransactionsProcessor", lambda cfg: processor)

        hydrate.hydrate_insiders("AAPL", limit_form345=50)
        processor.process_company.assert_called_once_with(ticker="AAPL", limit_form345=50)


class TestLambdaHandler:
    def test_success(self, monkeypatch):
        monkeypatch.setattr(hydrate, "main", lambda **k: None)
        result = hydrate.lambda_handler({"ticker": "AAPL", "start_date": "2020-01-01"}, None)
        assert result["statusCode"] == 200

    def test_failure(self, monkeypatch):
        def boom(**k):
            raise RuntimeError("lambda fail")

        monkeypatch.setattr(hydrate, "main", boom)
        result = hydrate.lambda_handler({}, None)
        assert result["statusCode"] == 500
        assert "lambda fail" in result["body"]

    def test_event_defaults(self, monkeypatch):
        captured = {}

        def capture(**k):
            captured.update(k)

        monkeypatch.setattr(hydrate, "main", capture)
        hydrate.lambda_handler({}, None)
        assert captured["ticker"] == ""
        assert captured["mode"] == "full"
        assert captured["days"] == 5
        assert captured["insider_limit"] == 100
