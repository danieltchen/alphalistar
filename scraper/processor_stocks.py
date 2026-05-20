"""
processor_stocks.py - Class for processing stock price and market data
"""

import os
import tempfile
from typing import Dict, Tuple, Optional, List, Union, TypeAlias, Any
from datetime import date, datetime
from pandas import DataFrame
import yfinance as yf
import logging
import time

try:
    from .connector_database import DatabaseConnector, Connection
    from .parser_stock import StockPriceDataParser, CompanyInfo
except ImportError:
    from connector_database import DatabaseConnector, Connection  # type: ignore
    from parser_stock import StockPriceDataParser, CompanyInfo  # type: ignore

SQLValue = Union[str, int, float, date, datetime, None]
SQLParams = Tuple[SQLValue, ...]  # This uses ... to indicate variable length tuple

# Define type aliases for parser results
ParserValue = Union[str, int, float, date, datetime]  # No None
ParserParams = Tuple[ParserValue, ...]
ParserStatement = Tuple[str, ParserParams]
ParserStatementsGroup = Tuple[str, List[ParserStatement]]
MarketDataResult: TypeAlias = Dict[str, ParserStatementsGroup]


class StockDataProcessor(DatabaseConnector):
    """Processor for extracting and storing stock market data."""

    def __init__(self, db_config: Dict[str, str]):
        """Initialize with database configuration."""
        super().__init__(db_config)

        # Configure logging
        self.logger = logging.getLogger(__name__)

    def fetch_stock_data(self, symbol: str, start_date: Optional[str] = None) -> Tuple[
        Optional[DataFrame],
        Optional[DataFrame],
        Optional[CompanyInfo],
    ]:
        """
        Fetch stock data for a symbol

        Args:
            symbol: Stock symbol
            start_date: Optional start date for historical data

        Returns:
            Tuple of (price_df, splits_df, company_info) where company_info is
            the raw yfinance Ticker.info dict (or None if unavailable).
        """
        try:
            # Configure cache location to Lambda's temp directory
            temp_dir = tempfile.gettempdir()

            # Configure yfinance cache location
            yf.set_tz_cache_location(temp_dir)

            # Sleep to avoid rate limiting issues
            time.sleep(1)

            # # Initialize ticker
            company = yf.Ticker(symbol)

            # Get price data
            if start_date:
                df = yf.download(
                    symbol,
                    start=start_date,
                    progress=False,
                    threads=False,
                    ignore_tz=True,
                )
            else:
                # For latest data, get last 5 days to ensure we have the most recent
                df = yf.download(
                    symbol, period="5d", progress=False, threads=False, ignore_tz=True
                )

            if df is not None and df.empty:
                self.logger.warning(f"No price data found for {symbol}")
                return None, None, None

            # Clean up the Dataframe
            df = df.dropna() # type: ignore

            # Handle splits
            splits_df = None
            try:
                splits = company.splits
                if splits is not None and not splits.empty:
                    splits_df = splits.to_frame("ratio")
            except Exception as e:
                self.logger.warning(f"Could not fetch splits for {symbol}: {str(e)}")

            company_info: Optional[CompanyInfo] = None
            try:
                company_info = company.info
            except Exception as e:
                self.logger.warning(
                    f"Could not fetch company info for {symbol}: {str(e)}"
                )

            return df, splits_df, company_info

        except Exception as e:
            self.logger.error(f"Error fetching data for {symbol}: {str(e)}")

            # Add a retry mechanism for common issues
            if "too many requests" in str(e).lower() or "rate limit" in str(e).lower():
                self.logger.info(
                    f"Rate limit detected for {symbol}, waiting 10 seconds..."
                )
                time.sleep(10)

                # Simple retry - let yfinance handle everything
                try:
                    if start_date:
                        df = yf.download(
                            symbol, start=start_date, progress=False, threads=False
                        )
                    else:
                        df = yf.download(
                            symbol, period="5d", progress=False, threads=False
                        )

                    if df is not None and not df.empty:
                        df = df.dropna() # type: ignore
                        return df, None, None

                except Exception as retry_e:
                    self.logger.error(f"Retry also failed for {symbol}: {str(retry_e)}")

            return None, None, None

    def get_latest_processed_date(self, ticker_id: int) -> Optional[date]:
        """Get the most recent date for which we have price data."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT date
                    FROM PRICE
                    WHERE tickerId = %s
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    (ticker_id,),
                )
                result = cur.fetchone()
                return result[0] if result else None

    def process_market_data(
        self,
        symbol: str,
        ticker_id: int,
        price_df: Optional[DataFrame] = None,
        split_df: Optional[DataFrame] = None,
        company_info: Optional[CompanyInfo] = None,
    ) -> Tuple[MarketDataResult, Optional[Dict[str, Any]]]:
        """
        Process market data for a given symbol.

        Returns SQL statement groups and an optional ticker profile dict
        derived from yfinance company.info via StockPriceDataParser.
        """
        parser = StockPriceDataParser(symbol=symbol, ticker_id=ticker_id)
        results: MarketDataResult = {}

        if price_df is not None:
            results["PRICE"] = parser.process_price_data(price_df)

        if split_df is not None:
            results["SPLIT"] = parser.process_split_data(split_df)

        if company_info:
            results["FUNDAMENTALS"] = parser.process_fundamentals(
                company_info, date.today()
            )

        profile = parser.build_ticker_profile(company_info)
        return results, profile

    def _persist_market_data(
        self,
        conn: Connection,
        symbol: str,
        ticker_id: int,
        price_df: Optional[DataFrame],
        split_df: Optional[DataFrame],
        company_info: Optional[CompanyInfo],
    ) -> None:
        """Execute market-data SQL and update ticker profile in one transaction."""
        results, profile = self.process_market_data(
            symbol=symbol,
            ticker_id=ticker_id,
            price_df=price_df,
            split_df=split_df,
            company_info=company_info,
        )
        if profile:
            self.update_ticker_profile(conn, ticker_id, profile)
        self.execute_sql_statements(conn, results)

    def process_stock(self, ticker: str, start_date: str) -> None:
        """Process historical stock data for a single company."""
        self.logger.info(f"Processing historical stock data for {ticker} starting from {start_date}")
        try:
            price_df, splits, company_info = self.fetch_stock_data(
                ticker, start_date=start_date
            )

            if price_df is None:
                self.logger.warning(f"Skipping {ticker} - no price data available")
                return

            ticker_id = self.get_ticker_id(ticker)
            with self.get_db_connection() as conn:
                self._persist_market_data(
                    conn, ticker, ticker_id, price_df, splits, company_info
                )

            self.logger.info(f"Successfully processed historical stock data for {ticker} from {start_date} to present")

        except Exception as e:
            self.logger.error(f"Error processing historical stock data for {ticker}: {str(e)}")
            raise

    def process_stocks(self, start_date: str) -> None:
        """Process historical stock data for all companies."""
        tickers = self.get_tickers()
        self.logger.info(f"Found {len(tickers)} tickers to process for historical data")

        with self.get_db_connection() as conn:
            for ticker in tickers:
                symbol = ticker["symbol"]
                ticker_id = ticker["id"]
                self.logger.info(f"Processing historical data for {symbol}")

                try:
                    price_df, splits, company_info = self.fetch_stock_data(
                        symbol, start_date=start_date
                    )

                    if price_df is None:
                        self.logger.warning(f"Skipping {symbol} - no data available")
                        continue

                    self._persist_market_data(
                        conn, symbol, ticker_id, price_df, splits, company_info
                    )
                    self.logger.info(
                        f"Successfully processed historical data for {symbol}"
                    )
                    time.sleep(1)

                except Exception as e:
                    self.logger.error(
                        f"Error processing historical data for {symbol}: {str(e)}"
                    )
                    continue

        self.logger.info("Historical stock data processing completed")

    def process_latest_data(self) -> None:
        """Process latest stock data for active companies."""
        tickers = self.get_tickers()
        self.logger.info(f"Found {len(tickers)} active tickers to update")

        with self.get_db_connection() as conn:
            for ticker in tickers:
                symbol = ticker["symbol"]
                ticker_id = ticker["id"]
                self.logger.info(f"Processing latest data for {symbol}")

                try:
                    # Get latest data
                    price_df, splits, company_info = self.fetch_stock_data(symbol)

                    if price_df is None:
                        self.logger.warning(f"Skipping {symbol} - no data available")
                        continue

                    # Get last processed date
                    last_date = self.get_latest_processed_date(ticker_id)

                    if last_date:
                        # Filter for only new data
                        price_df = price_df[price_df.index.date > last_date]  # type: ignore

                        if splits is not None:
                            splits = splits[splits.index.date > last_date]  # type: ignore

                    if not price_df.empty:
                        self._persist_market_data(
                            conn,
                            symbol,
                            ticker_id,
                            price_df,
                            (
                                splits
                                if splits is not None and not splits.empty
                                else None
                            ),
                            company_info,
                        )
                        self.logger.info(
                            f"Successfully processed latest data for {symbol}"
                        )
                    else:
                        self.logger.info(f"No new data to process for {symbol}")

                    time.sleep(1)

                except Exception as e:
                    self.logger.error(
                        f"Error processing latest data for {symbol}: {str(e)}"
                    )
                    continue

        self.logger.info("Latest stock data processing completed")
