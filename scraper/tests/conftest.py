"""Shared pytest fixtures for scraper module tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SCRAPER_DIR = TESTS_DIR.parent
for path in (str(SCRAPER_DIR), str(TESTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from fakes import FakeConnection  # noqa: E402


@pytest.fixture
def db_config() -> Dict[str, str]:
    return {
        "dbname": "testdb",
        "host": "localhost",
        "user": "test",
        "password": "secret",
        "port": "5432",
    }


@pytest.fixture
def fake_connection() -> FakeConnection:
    return FakeConnection()
