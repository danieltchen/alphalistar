"""
hydrate.py - Script to perform database hydration of a particular stock and its market data, financials, press releases
"""

import os
from typing import Dict, Any
import logging
import asyncio
from openai import AsyncOpenAI
import socket

# Force IPv4
original_getaddrinfo = socket.getaddrinfo


def getaddrinfo_ipv4(*args, **kwargs):  # type: ignore
    responses = original_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]


socket.getaddrinfo = getaddrinfo_ipv4

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)
logger.info("Forced IPv4 for all network connections")

try:
    from .connector_database import DatabaseConnector
    from .processor_stocks import StockDataProcessor
    from .processor_financials import FinancialsProcessor
    from .scrape import SingleStockScraper
    from .processor_pressreleases import (
        PressReleaseProcessor,
    )  # Use the regular version to SQL
except ImportError:
    from connector_database import DatabaseConnector  # type: ignore
    from processor_stocks import StockDataProcessor  # type: ignore
    from processor_financials import FinancialsProcessor  # type: ignore
    from scrape import SingleStockScraper  # type: ignore
    from processor_pressreleases import PressReleaseProcessor  # type: ignore


def hydrate_stock(ticker: str, start_date: str) -> None:
    """Process historical stock data."""
    logger.info("Starting stock data hydration...")
    try:
        db_config = DatabaseConnector.get_db_config()
        processor = StockDataProcessor(db_config)

        # Process historical data from start_date to present
        processor.process_stock(ticker=ticker, start_date=start_date)
        logger.info(
            f"Stock data hydration completed successfully: {ticker} from {start_date}"
        )
    except Exception as e:
        logger.error(f"Failed to process historical stock data: {str(e)}")
        raise


def hydrate_financials(
    ticker: str, start_date: str, annual_limit: int = 5, quarterly_limit: int = 20
) -> None:
    """Process Edgar financials."""
    logger.info("Starting financials hydration...")
    try:
        db_config = DatabaseConnector.get_db_config()
        processor = FinancialsProcessor(db_config)

        processor.process_company(
            ticker=ticker, annual_limit=annual_limit, quarterly_limit=quarterly_limit
        )
        logger.info(
            f"Financials hydration completed successfully: {ticker} from {start_date}"
        )
    except Exception as e:
        logger.error(f"Failed to process financials: {str(e)}")
        raise


async def hydrate_press_releases(
    ticker: str,
    start_date: str,
    limit_8k: int = 40,
    limit_10k: int = 5,
    limit_10q: int = 5,
) -> None:
    """Process historical press releases."""
    logger.info("Starting press releases hydration for {ticker}...")
    try:
        openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        db_config = DatabaseConnector.get_db_config()

        processor = PressReleaseProcessor(db_config, openai_client)

        await processor.process_company(
            ticker=ticker,
            limit_8k=limit_8k,
            limit_10k=limit_10k,
            limit_10q=limit_10q,
        )

        # # Clean up connections
        # processor.cleanup()

        logger.info(
            f"Press releases hydration completed successfully: {ticker} from {start_date}"
        )
    except Exception as e:
        logger.error(f"Failed to process press releases: {str(e)}")
        raise


def main(
    ticker: str,
    start_date: str,
    annual_limit: int = 5,
    quarterly_limit: int = 20,
    limit_8k: int = 40,
    limit_10k: int = 5,
    limit_10q: int = 5,
    mode: str = "full",
    days: int = 5,
) -> None:
    """
    Main function to run all hydration processes sequentially.
    This is a synchronous function that calls async functions properly.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    try:
        logger.info(
            f"Starting database hydration process ({mode}): {ticker} from {start_date}"
        )

        if mode == "incremental":
            SingleStockScraper(
                ticker=ticker,
                days=days,
                annual_limit=annual_limit,
                quarterly_limit=quarterly_limit,
                limit_8k=limit_8k,
                limit_10k=limit_10k,
                limit_10q=limit_10q,
                # Hydration can be run ad-hoc, so don't block on market calendar.
                skip_market_check=True,
            ).run()
            logger.info(f"Incremental hydration flow finished successfully: {ticker}")
            return

        hydrate_stock(ticker=ticker, start_date=start_date)
        hydrate_financials(
            ticker=ticker,
            start_date=start_date,
            annual_limit=annual_limit,
            quarterly_limit=quarterly_limit,
        )
        asyncio.run(
            hydrate_press_releases(
                ticker=ticker,
                start_date=start_date,
                limit_8k=limit_8k,
                limit_10k=limit_10k,
                limit_10q=limit_10q,
            )
        )

        logger.info(
            f"Complete database hydration process finished successfully: {ticker} from {start_date}"
        )
    except Exception as e:
        logger.error(f"Database hydration process failed: {str(e)}")
        raise


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler function."""
    try:
        main(
            ticker=event.get("ticker", ""),
            start_date=event.get("start_date", ""),
            annual_limit=event.get("annual_limit", 5),
            quarterly_limit=event.get("quarterly_limit", 20),
            limit_8k=event.get("limit_8k", 40),
            limit_10k=event.get("limit_10k", 5),
            limit_10q=event.get("limit_10q", 5),
            mode=event.get("mode", "full"),
            days=event.get("days", 5),
        )
        return {
            "statusCode": 200,
            "body": "Database hydration completed successfully",
        }
    except Exception as e:
        logger.error(f"Lambda execution failed: {str(e)}")
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Hydrate a single stock ticker.")
    p.add_argument("ticker", type=str, help="Stock ticker symbol, e.g. AAPL")
    p.add_argument(
        "--start-date",
        type=str,
        default="2020-01-01",
        help="Historical start date ISO format (default: 2020-01-01)",
    )
    p.add_argument(
        "--annual",
        type=int,
        default=5,
        dest="annual_limit",
        help="Max annual (10-K) filings (default: 5)",
    )
    p.add_argument(
        "--quarterly",
        type=int,
        default=20,
        dest="quarterly_limit",
        help="Max quarterly (10-Q) filings (default: 20)",
    )
    p.add_argument(
        "--8k",
        type=int,
        default=40,
        dest="limit_8k",
        help="Max 8-K filings (default: 40)",
    )
    p.add_argument(
        "--10k",
        type=int,
        default=5,
        dest="limit_10k",
        help="Max 10-K MD&A sections (default: 5)",
    )
    p.add_argument(
        "--10q",
        type=int,
        default=5,
        dest="limit_10q",
        help="Max 10-Q MD&A sections (default: 5)",
    )
    p.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="full",
        help="Run full rehydrate or incremental (default: full)",
    )
    p.add_argument(
        "--days",
        type=int,
        default=5,
        help="Recent day window for incremental stock updates (default: 5)",
    )

    args = p.parse_args()
    main(
        ticker=args.ticker,
        start_date=args.start_date,
        annual_limit=args.annual_limit,
        quarterly_limit=args.quarterly_limit,
        limit_8k=args.limit_8k,
        limit_10k=args.limit_10k,
        limit_10q=args.limit_10q,
        mode=args.mode,
        days=args.days,
    )
