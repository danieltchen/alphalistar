"""
scrape.py - Single-stock incremental scraper with configurable limits.

Usage:
    python scrape.py AAPL
    python scrape.py AAPL --days 10 --annual 2 --quarterly 5 --8k 3 --10k 1
    python scrape.py AAPL --skip-market-check
"""

import argparse
import asyncio
import logging
import os
import socket
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

# Force IPv4
_original_getaddrinfo = socket.getaddrinfo


def _getaddrinfo_ipv4(*args, **kwargs):  # type: ignore
    return [r for r in _original_getaddrinfo(*args, **kwargs) if r[0] == socket.AF_INET]


socket.getaddrinfo = _getaddrinfo_ipv4

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from .app_config import get_openai_api_key
    from .connector_database import DatabaseConnector, is_edgar_eligible
    from .processor_stocks import StockDataProcessor
    from .processor_pressreleases import PressReleaseProcessor
    from .scrape_latest_financials import LatestFinancialsProcessor
    from .processor_financials import _safe_company
    from .edgar_wrapper import Company, set_identity # type: ignore
except ImportError:
    from app_config import get_openai_api_key  # type: ignore
    from connector_database import DatabaseConnector, is_edgar_eligible  # type: ignore
    from processor_stocks import StockDataProcessor  # type: ignore
    from processor_pressreleases import PressReleaseProcessor  # type: ignore
    from scrape_latest_financials import LatestFinancialsProcessor  # type: ignore
    from processor_financials import _safe_company  # type: ignore
    from edgar_wrapper import Company, set_identity  # type: ignore


# ---------------------------------------------------------------------------
# Market calendar helper (shared with scrape_all.py)
# ---------------------------------------------------------------------------

def is_market_open_day() -> bool:
    from pandas.tseries.holiday import USFederalHolidayCalendar

    today = date.today()
    if today.weekday() >= 5:
        logger.info(f"Today ({today}) is a weekend — skipping.")
        return False

    cal = USFederalHolidayCalendar()
    
    holidays = cal.holidays(start=today, end=today)  # type: ignore
    if len(holidays) > 0:
        logger.info(f"Today ({today}) is a US Federal Holiday. Skipping scraping.")
        return False

    return True


# ---------------------------------------------------------------------------
# Per-processor scrape helpers
# ---------------------------------------------------------------------------

def _scrape_stocks(ticker: str, days: int, db_config: dict) -> None:  # type: ignore[type-arg]
    """Fetch the last *days* of price data for *ticker* and upsert new rows."""
    logger.info(f"[stocks] scraping last {days} day(s) for {ticker}")
    processor = StockDataProcessor(db_config)
    start_date = (date.today() - timedelta(days=days)).isoformat()
    processor.process_stock(ticker=ticker, start_date=start_date)
    logger.info(f"[stocks] done for {ticker}")


def _scrape_financials(
    ticker: str,
    annual_limit: int,
    quarterly_limit: int,
    db_config: dict,  # type: ignore[type-arg]
) -> None:
    """Check for new 10-K / 10-Q filings and process if newer than DB."""
    logger.info(
        f"[financials] checking {ticker} — annual_limit={annual_limit}, "
        f"quarterly_limit={quarterly_limit}"
    )
    processor = LatestFinancialsProcessor(db_config)
    ticker_id = processor.get_ticker_id(ticker)
    latest_periods = processor.get_latest_periods(ticker_id)

    company = _safe_company(ticker)
    if company is None:
        logger.warning("[financials] EDGAR could not resolve %s; skipping", ticker)
        return

    processor.process_new_financials(company, ticker_id, ticker, latest_periods)
    logger.info(f"[financials] done for {ticker}")


async def _scrape_press_releases(
    ticker: str,
    limit_8k: int,
    limit_10k: int,
    limit_10q: int,
    db_config: dict,  # type: ignore[type-arg]
) -> None:
    """Fetch and process the latest 8-K / 10-K MD&A filings for *ticker*."""
    logger.info(
        f"[press releases] scraping {ticker} — 8-K limit={limit_8k}, "
        f"10-K limit={limit_10k}, 10-Q limit={limit_10q}"
    )
    openai_client = AsyncOpenAI(api_key=get_openai_api_key())
    processor = PressReleaseProcessor(db_config, openai_client)
    await processor.process_company(
        ticker=ticker, limit_8k=limit_8k, limit_10k=limit_10k, limit_10q=limit_10q
    )
    logger.info(f"[press releases] done for {ticker}")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class SingleStockScraper:
    """Orchestrates incremental scraping for a single ticker symbol."""

    def __init__(
        self,
        ticker: str,
        days: int,
        annual_limit: int,
        quarterly_limit: int,
        limit_8k: int,
        limit_10k: int,
        limit_10q: int,
        skip_market_check: bool = False,
        force_press_releases: bool = False,
    ) -> None:
        self._ticker = ticker.upper()
        self._days = days
        self._annual_limit = annual_limit
        self._quarterly_limit = quarterly_limit
        self._limit_8k = limit_8k
        self._limit_10k = limit_10k
        self._limit_10q = limit_10q
        self._skip_market_check = skip_market_check
        self._force_press_releases = force_press_releases

    @staticmethod
    def _normalize_filing_list(filing_list: Any) -> List[Any]:
        """Normalize EDGAR filing responses to a list."""
        if filing_list is None:
            return []
        if hasattr(filing_list, "__iter__"):
            return list(filing_list)
        return [filing_list]

    def _should_run_stocks(self, db_config: Dict[str, str], ticker_id: int) -> bool:
        processor = StockDataProcessor(db_config)
        latest_price_date = processor.get_latest_processed_date(ticker_id)
        if latest_price_date == date.today():
            logger.info("[stocks] up to date (latest price date is today), skipping")
            return False
        return True

    def _should_run_financials(self, db_config: Dict[str, str], ticker_id: int) -> bool:
        processor = LatestFinancialsProcessor(db_config)
        latest_periods = processor.get_latest_periods(ticker_id)

        identity = f"Alphalistar Limited alphalistai+{self._ticker}@gmail.com"
        set_identity(identity)
        company = Company(self._ticker)

        annual_filing = company.latest("10-K", 1)
        if annual_filing:
            latest_annual = processor.get_filing_date(annual_filing)
            if latest_annual is None:
                bs_df, _, _ = processor._extract_statement_dataframes(annual_filing)
                latest_annual = processor.get_latest_date_from_df(bs_df)
            if (
                latest_periods.get("annual_period") is None
                or latest_annual > latest_periods["annual_period"]
            ):
                return True

        quarterly_filing = company.latest("10-Q", 1)
        if quarterly_filing:
            latest_quarterly = processor.get_filing_date(quarterly_filing)
            if latest_quarterly is None:
                bs_df, _, _ = processor._extract_statement_dataframes(quarterly_filing)
                latest_quarterly = processor.get_latest_date_from_df(bs_df)
            if (
                latest_periods.get("quarterly_period") is None
                or latest_quarterly > latest_periods["quarterly_period"]
            ):
                return True

        logger.info("[financials] no new annual/quarterly period found, skipping")
        return False

    def _should_run_press_releases(self, db: DatabaseConnector) -> bool:
        if self._force_press_releases:
            logger.info("[press releases] force flag enabled; bypassing preflight skip")
            return True

        identity = f"Alphalistar Limited alphalistai+{self._ticker}@gmail.com"
        set_identity(identity)
        company = Company(self._ticker)

        filings: List[Any] = []
        filings.extend(
            self._normalize_filing_list(
                company.get_filings(form="8-K").latest(self._limit_8k)
            )
        )
        filings.extend(
            self._normalize_filing_list(
                company.get_filings(form="10-K").latest(self._limit_10k)
            )
        )
        accessions = [
            filing.accession_no
            for filing in filings
            if hasattr(filing, "accession_no") and filing.accession_no
        ]
        if not accessions:
            logger.info("[press releases] no candidate filings found, skipping")
            return False

        with db.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM FILING
                    WHERE accessionNo = ANY(%s)
                      AND completed = TRUE
                    """,
                    (accessions,),
                )
                completed_count = int(cur.fetchone()[0])

        if completed_count == len(accessions):
            logger.info("[press releases] latest candidate filings already completed, skipping")
            return False
        return True

    def _press_release_cursor(self, db: DatabaseConnector, ticker_id: int) -> Dict[str, Any]:
        with db.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT accessionNo, filingDate
                    FROM FILING
                    WHERE tickerId = %s
                      AND completed = TRUE
                      AND type IN ('8-K', '10-K')
                    ORDER BY filingDate DESC
                    LIMIT 1
                    """,
                    (ticker_id,),
                )
                result = cur.fetchone()
                if result is None:
                    return {}
                return {
                    "latest_completed_accession": result[0],
                    "latest_completed_filing_date": result[1].isoformat(),
                }

    def run(self) -> None:
        if not self._skip_market_check and not is_market_open_day():
            logger.info("Market closed today — exiting without scraping.")
            return

        db_config = DatabaseConnector.get_db_config()
        db = DatabaseConnector(db_config)
        ticker_id = db.get_ticker_id(self._ticker)
        counters: Dict[str, int] = {
            "skipped_no_new_data": 0,
            "skipped_locked": 0,
            "processed_count": 0,
            "failed_count": 0,
        }

        logger.info(f"=== Starting scrape for {self._ticker} ===")

        quote_type: Optional[str] = None

        process_specs = [
            (
                "stocks",
                lambda: self._should_run_stocks(db_config, ticker_id),
                lambda: _scrape_stocks(self._ticker, self._days, db_config),
                lambda: self._stock_cursor(db_config, ticker_id),
            ),
            (
                "financials",
                lambda: self._should_run_financials(db_config, ticker_id),
                lambda: _scrape_financials(
                    self._ticker, self._annual_limit, self._quarterly_limit, db_config
                ),
                lambda: LatestFinancialsProcessor(db_config).get_latest_periods(ticker_id),
            ),
            (
                "press_releases",
                lambda: self._should_run_press_releases(db),
                lambda: asyncio.run(
                    _scrape_press_releases(
                        self._ticker,
                        self._limit_8k,
                        self._limit_10k,
                        self._limit_10q,
                        db_config,
                    )
                ),
                lambda: self._press_release_cursor(db, ticker_id),
            ),
        ]

        for process_name, should_run_fn, run_fn, cursor_fn in process_specs:
            if process_name in {"financials", "press_releases"} and not is_edgar_eligible(
                quote_type
            ):
                logger.info(
                    f"[{process_name}] skipped for {self._ticker}: "
                    f"quote_type={quote_type} (non-EQUITY)"
                )
                counters["skipped_no_new_data"] += 1
                continue

            try:
                should_run = should_run_fn()
            except Exception as e:
                logger.warning(
                    f"[{process_name}] preflight check failed ({e}); failing open and attempting run"
                )
                should_run = True

            if not should_run:
                counters["skipped_no_new_data"] += 1
                if process_name == "stocks":
                    quote_type = db.get_quote_type(ticker_id)
                continue

            lock_token = db.try_start_process_run(ticker_id, process_name)
            if lock_token is None:
                logger.info(f"[{process_name}] another run is in progress; skipping")
                counters["skipped_locked"] += 1
                if process_name == "stocks":
                    quote_type = db.get_quote_type(ticker_id)
                continue

            try:
                run_fn()
                db.mark_process_run_success(
                    ticker_id, process_name, lock_token, cursor_fn()
                )
                counters["processed_count"] += 1
            except Exception as e:
                counters["failed_count"] += 1
                db.mark_process_run_failed(ticker_id, process_name, lock_token, str(e))
                logger.error(f"[{process_name}] failed for {self._ticker}: {e}")

            if process_name == "stocks":
                quote_type = db.get_quote_type(ticker_id)

        logger.info(
            "Run counters for %s: processed=%s skipped_no_new_data=%s skipped_locked=%s failed=%s",
            self._ticker,
            counters["processed_count"],
            counters["skipped_no_new_data"],
            counters["skipped_locked"],
            counters["failed_count"],
        )
        logger.info(f"=== Scrape complete for {self._ticker} ===")

    @staticmethod
    def _stock_cursor(db_config: Dict[str, str], ticker_id: int) -> Dict[str, Any]:
        latest_price_date = StockDataProcessor(db_config).get_latest_processed_date(ticker_id)
        return {
            "latest_price_date": (
                latest_price_date.isoformat() if latest_price_date is not None else None
            )
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Incremental scraper for a single stock ticker."
    )
    p.add_argument("ticker", type=str, help="Stock ticker symbol, e.g. AAPL")
    p.add_argument(
        "--days",
        type=int,
        default=5,
        help="Number of recent calendar days of price data to fetch (default: 5)",
    )
    p.add_argument(
        "--annual",
        type=int,
        default=1,
        dest="annual_limit",
        help="Max annual (10-K) filings to check (default: 1)",
    )
    p.add_argument(
        "--quarterly",
        type=int,
        default=1,
        dest="quarterly_limit",
        help="Max quarterly (10-Q) filings to check (default: 1)",
    )
    p.add_argument(
        "--8k",
        type=int,
        default=2,
        dest="limit_8k",
        help="Max 8-K press release filings to process (default: 2)",
    )
    p.add_argument(
        "--10k",
        type=int,
        default=1,
        dest="limit_10k",
        help="Max 10-K MD&A sections to process (default: 1)",
    )
    p.add_argument(
        "--10q",
        type=int,
        default=1,
        dest="limit_10q",
        help="Max 10-Q MD&A sections to process (default: 1)",
    )
    p.add_argument(
        "--skip-market-check",
        action="store_true",
        default=False,
        help="Run even on weekends / holidays",
    )
    p.add_argument(
        "--force-press-releases",
        action="store_true",
        default=False,
        help="Always run press release/10-K processor even if preflight says up-to-date",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()
    scraper = SingleStockScraper(
        ticker=args.ticker,
        days=args.days,
        annual_limit=args.annual_limit,
        quarterly_limit=args.quarterly_limit,
        limit_8k=args.limit_8k,
        limit_10k=args.limit_10k,
        limit_10q=args.limit_10q,
        skip_market_check=args.skip_market_check,
        force_press_releases=args.force_press_releases,
    )
    scraper.run()


if __name__ == "__main__":
    main()
