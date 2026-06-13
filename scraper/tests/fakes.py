"""Reusable fakes for scraper unit tests."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple


class FakeCursor:
    """Scriptable psycopg2 cursor double with context-manager support."""

    def __init__(
        self,
        fetchone_results: Optional[Sequence[Any]] = None,
        fetchall_results: Optional[Sequence[Any]] = None,
        *,
        cursor_factory: Any = None,
    ) -> None:
        self.fetchone_results: List[Any] = list(fetchone_results or [])
        self.fetchall_results: List[Any] = list(fetchall_results or [])
        self.executed: List[Tuple[Any, Any]] = []
        self._fetchone_idx = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: Any, params: Any = None) -> None:
        self.executed.append((query, params))

    def mogrify(self, query: Any, params: Any = None) -> bytes:
        return str(query).encode()

    def fetchone(self) -> Any:
        if self._fetchone_idx < len(self.fetchone_results):
            result = self.fetchone_results[self._fetchone_idx]
            self._fetchone_idx += 1
            return result
        return None

    def fetchall(self) -> List[Any]:
        return list(self.fetchall_results)


class FakeConnection:
    """Context-manager connection double returning scripted cursors."""

    def __init__(self, cursors: Optional[List[FakeCursor]] = None) -> None:
        self.cursors = cursors or [FakeCursor()]
        self._cursor_idx = 0
        self.committed = 0
        self.rolled_back = 0

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def cursor(self, cursor_factory: Any = None) -> FakeCursor:
        if self._cursor_idx < len(self.cursors):
            cur = self.cursors[self._cursor_idx]
            self._cursor_idx += 1
            return cur
        return FakeCursor()

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


def make_filing(
    accession_no: str = "0001234567-24-000001",
    form: str = "8-K",
    filing_date: Any = None,
) -> Any:
    """Lightweight fake EDGAR filing object."""
    from datetime import date

    class _Filing:
        pass

    f = _Filing()
    f.accession_no = accession_no
    f.form = form
    f.filing_date = filing_date or date(2024, 6, 1)
    return f


def make_filings_collection(latest_result: Any) -> Any:
    """Fake company.get_filings(form=...).latest(n) chain."""

    class _Filings:
        def latest(self, n: int) -> Any:
            return latest_result

    return _Filings()


def make_company(
    *,
    latest_map: Optional[dict[str, Any]] = None,
    filings_map: Optional[dict[str, Any]] = None,
) -> Any:
    """Fake EDGAR Company with scripted latest() and get_filings()."""

    class _Company:
        def latest(self, form: str, n: int) -> Any:
            return (latest_map or {}).get(form)

        def get_filings(self, form: str) -> Any:
            return (filings_map or {}).get(form, make_filings_collection([]))

    return _Company()
