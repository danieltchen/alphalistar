"""Tests for connector_database.py configuration and DB helpers."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from connector_database import DatabaseConnector, is_edgar_eligible
from fakes import FakeConnection, FakeCursor, make_filing


@pytest.fixture
def connector(db_config):
    return DatabaseConnector(db_config)


class TestIsEdgarEligible:
    def test_none_is_eligible(self):
        assert is_edgar_eligible(None) is True

    def test_equity_is_eligible(self):
        assert is_edgar_eligible("EQUITY") is True

    def test_etf_not_eligible(self):
        assert is_edgar_eligible("ETF") is False


class TestCredentialsFromRdsSecret:
    def test_user_key(self):
        result = DatabaseConnector._credentials_from_rds_secret(
            {"user": "admin", "password": "pw"}
        )
        assert result == {"user": "admin", "password": "pw"}

    def test_username_alias(self):
        result = DatabaseConnector._credentials_from_rds_secret(
            {"username": "admin", "password": "pw"}
        )
        assert result["user"] == "admin"

    def test_missing_password_raises(self):
        with pytest.raises(ValueError, match="password"):
            DatabaseConnector._credentials_from_rds_secret({"user": "admin"})


class TestGetDbConfigFromEnv:
    def test_complete_env(self, monkeypatch):
        for key, val in {
            "DB_NAME": "mydb",
            "DB_HOST": "host",
            "DB_USER": "u",
            "DB_PASS": "p",
            "DB_PORT": "5432",
        }.items():
            monkeypatch.setenv(key, val)
        cfg = DatabaseConnector.get_db_config_from_env()
        assert cfg["dbname"] == "mydb"
        assert cfg["port"] == "5432"

    def test_missing_env_raises(self, monkeypatch):
        for key in ("DB_NAME", "DB_HOST", "DB_USER", "DB_PASS", "DB_PORT"):
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(ValueError, match="Missing required environment variables"):
            DatabaseConnector.get_db_config_from_env()


class TestGetDbConfig:
    def test_env_fallback_when_no_secret(self, monkeypatch):
        monkeypatch.delenv("AWS_SECRET_NAME", raising=False)
        monkeypatch.setattr(
            DatabaseConnector,
            "get_db_config_from_env",
            staticmethod(lambda: {"dbname": "envdb"}),
        )
        assert DatabaseConnector.get_db_config()["dbname"] == "envdb"

    def test_secret_failure_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("AWS_SECRET_NAME", "my-secret")
        monkeypatch.setattr(
            DatabaseConnector,
            "get_db_config_from_merged_secrets",
            staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))),
        )
        monkeypatch.setattr(
            DatabaseConnector,
            "get_db_config_from_env",
            staticmethod(lambda: {"dbname": "fallback"}),
        )
        assert DatabaseConnector.get_db_config()["dbname"] == "fallback"


class TestValidateProcessName:
    def test_allowed(self, connector):
        connector._validate_process_name("stocks")

    def test_disallowed_raises(self, connector):
        with pytest.raises(ValueError, match="Unsupported process name"):
            connector._validate_process_name("invalid_process")


class TestGetTickerId:
    def test_empty_ticker_raises(self, connector):
        with pytest.raises(ValueError, match="cannot be empty"):
            connector.get_ticker_id("   ")

    def test_found(self, connector, monkeypatch):
        conn = FakeConnection([FakeCursor(fetchone_results=[(99,)])])
        monkeypatch.setattr(connector, "get_db_connection", lambda: conn)
        assert connector.get_ticker_id("AAPL") == 99

    def test_not_found_raises(self, connector, monkeypatch):
        conn = FakeConnection([FakeCursor(fetchone_results=[None])])
        monkeypatch.setattr(connector, "get_db_connection", lambda: conn)
        with pytest.raises(ValueError, match="Ticker not found"):
            connector.get_ticker_id("NOPE")


class TestInsertFilingRecord:
    def test_string_filing_date(self, connector, monkeypatch):
        conn = FakeConnection([FakeCursor(fetchone_results=[(1,)])])
        monkeypatch.setattr(connector, "get_db_connection", lambda: conn)
        filing = make_filing(filing_date="2024-03-15")
        filing_id = connector.insert_filing_record(conn, 1, "AAPL", filing)
        assert filing_id == 1
        assert conn.committed == 1

    def test_datetime_filing_date(self, connector):
        conn = FakeConnection([FakeCursor(fetchone_results=[(2,)])])
        filing = make_filing(filing_date=datetime(2024, 3, 15, 12, 0))
        filing_id = connector.insert_filing_record(conn, 1, "AAPL", filing)
        assert filing_id == 2

    def test_no_returning_raises(self, connector):
        conn = FakeConnection([FakeCursor(fetchone_results=[None])])
        filing = make_filing()
        with pytest.raises(ValueError, match="no ID returned"):
            connector.insert_filing_record(conn, 1, "AAPL", filing)


class TestExecuteSqlStatements:
    def test_static_schema_skips_create(self, connector, monkeypatch):
        cur = FakeCursor()
        cur.fetchone_results = [("public.price",)]  # table exists
        conn = FakeConnection([cur])
        results = {
            "PRICE": (
                "CREATE TABLE PRICE (...)",
                [("INSERT INTO PRICE VALUES (%s)", (1,))],
            )
        }
        with patch("connector_database.execute_batch") as mock_batch:
            connector.execute_sql_statements(conn, results)
            mock_batch.assert_called_once()
        create_calls = [q for q, _ in cur.executed if "CREATE TABLE" in str(q).upper()]
        assert create_calls == []
        assert conn.committed == 1

    def test_batched_inserts(self, connector):
        cur = FakeCursor()
        cur.fetchone_results = [None]  # table does not exist
        conn = FakeConnection([cur])
        insert_sql = "INSERT INTO foo VALUES (%s)"
        results = {
            "foo": (
                "CREATE TABLE foo (...)",
                [(insert_sql, (1,)), (insert_sql, (2,))],
            )
        }
        with patch("connector_database.execute_batch") as mock_batch:
            connector.execute_sql_statements(conn, results)
            mock_batch.assert_called_once()

    def test_rollback_on_error(self, connector):
        cur = FakeCursor()
        cur.fetchone_results = [None]

        def boom(query, params=None):
            if "CREATE TABLE" in str(query):
                raise RuntimeError("db error")

        cur.execute = boom  # type: ignore[method-assign]
        conn = FakeConnection([cur])
        with pytest.raises(RuntimeError, match="db error"):
            connector.execute_sql_statements(conn, {"t": ("CREATE TABLE t", [])})
        assert conn.rolled_back == 1
