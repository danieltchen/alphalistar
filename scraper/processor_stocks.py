"""
processor_stocks.py - Class for processing stock price and market data
"""

import os
import tempfile
from typing import Dict, Tuple, Optional, List, Union, TypeAlias
from datetime import date, datetime
from pandas import DataFrame
import yfinance as yf
import logging
import time

try:
    from .connector_database import DatabaseConnector
    from .parser_stock import StockPriceDataParser
except ImportError:
    from connector_database import DatabaseConnector  # type: ignore
    from parser_stock import StockPriceDataParser  # type: ignore

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
        Optional[Dict[str, Union[str, int, float]]],
    ]:
        """
        Fetch stock data for a symbol

        Args:
            symbol: Stock symbol
            start_date: Optional start date for historical data

        Returns:
            Tuple of (price_df, splits_df, fundamentals)
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

            if df.empty:
                self.logger.warning(f"No price data found for {symbol}")
                return None, None, None

            # Clean up the Dataframe
            df = df.dropna()

            # Handle splits
            splits_df = None
            try:
                splits = company.splits
                if splits is not None and not splits.empty:
                    splits_df = splits.to_frame("ratio")
            except Exception as e:
                self.logger.warning(f"Could not fetch splits for {symbol}: {str(e)}")

            # Extract comprehensive fundamentals matching the database schema
            fundamentals = None
            try:
                info = company.info
                if info:
                    fundamentals = {
                        # Basic company info
                        "fullTimeEmployees": company.info.get("fullTimeEmployees", 0),
                        # Valuation metrics
                        "trailingPE": company.info.get("trailingPE", 0.0),
                        "forwardPE": company.info.get("forwardPE", 0.0),
                        "marketCap": company.info.get("marketCap", 0),
                        "enterpriseValue": company.info.get("enterpriseValue", 0),
                        "priceToBook": company.info.get("priceToBook", 0.0),
                        "trailingPegRatio": company.info.get("trailingPegRatio", 0.0),
                        "priceToSalesTrailing12Months": company.info.get(
                            "priceToSalesTrailing12Months", 0.0
                        ),
                        # Dividend metrics
                        "dividendYield": company.info.get("dividendYield", 0.0),
                        "dividendRate": company.info.get("dividendRate", 0.0),
                        "payoutRatio": company.info.get("payoutRatio", 0.0),
                        "fiveYearAvgDividendYield": company.info.get(
                            "fiveYearAvgDividendYield", 0.0
                        ),
                        # Risk and trading metrics
                        "beta": company.info.get("beta", 0.0),
                        "volume": company.info.get("volume", 0),
                        "regularMarketVolume": company.info.get(
                            "regularMarketVolume", 0
                        ),
                        "averageVolume": company.info.get("averageVolume", 0),
                        # Price ranges and averages
                        "fiftyTwoWeekLow": company.info.get("fiftyTwoWeekLow", 0.0),
                        "fiftyTwoWeekHigh": company.info.get("fiftyTwoWeekHigh", 0.0),
                        "fiftyTwoWeekRange": company.info.get("fiftyTwoWeekRange", ""),
                        "fiftyTwoWeekChangePercent": company.info.get(
                            "fiftyTwoWeekChangePercent", 0.0
                        ),
                        "fiftyTwoWeekLowChange": company.info.get(
                            "fiftyTwoWeekLowChange", 0.0
                        ),
                        "fiftyTwoWeekLowChangePercent": company.info.get(
                            "fiftyTwoWeekLowChangePercent", 0.0
                        ),
                        "fiftyTwoWeekHighChange": company.info.get(
                            "fiftyTwoWeekHighChange", 0.0
                        ),
                        "fiftyTwoWeekHighChangePercent": company.info.get(
                            "fiftyTwoWeekHighChangePercent", 0.0
                        ),
                        "fiftyDayAverage": company.info.get("fiftyDayAverage", 0.0),
                        "fiftyDayAverageChange": company.info.get(
                            "fiftyDayAverageChange", 0.0
                        ),
                        "fiftyDayAverageChangePercent": company.info.get(
                            "fiftyDayAverageChangePercent", 0.0
                        ),
                        "twoHundredDayAverage": company.info.get(
                            "twoHundredDayAverage", 0.0
                        ),
                        "twoHundredDayAverageChange": company.info.get(
                            "twoHundredDayAverageChange", 0.0
                        ),
                        "twoHundredDayAverageChangePercent": company.info.get(
                            "twoHundredDayAverageChangePercent", 0.0
                        ),
                        # Share metrics
                        "floatShares": company.info.get("floatShares", 0),
                        "sharesOutstanding": company.info.get("sharesOutstanding", 0),
                        "sharesShort": company.info.get("sharesShort", 0),
                        "bookValue": company.info.get("bookValue", 0.0),
                        # Earnings metrics
                        "trailingEps": company.info.get("trailingEps", 0.0),
                        "forwardEps": company.info.get("forwardEps", 0.0),
                        "epsForward": company.info.get("epsForward", 0.0),
                        "earningsQuarterlyGrowth": company.info.get(
                            "earningsQuarterlyGrowth", 0.0
                        ),
                        "earningsGrowth": company.info.get("earningsGrowth", 0.0),
                        # Enterprise and revenue metrics
                        "enterpriseToRevenue": company.info.get(
                            "enterpriseToRevenue", 0.0
                        ),
                        "enterpriseToEbitda": company.info.get(
                            "enterpriseToEbitda", 0.0
                        ),
                        "totalRevenue": company.info.get("totalRevenue", 0),
                        "revenueGrowth": company.info.get("revenueGrowth", 0.0),
                        "revenuePerShare": company.info.get("revenuePerShare", 0.0),
                        # Cash and debt metrics
                        "totalCash": company.info.get("totalCash", 0),
                        "totalCashPerShare": company.info.get("totalCashPerShare", 0.0),
                        "ebitda": company.info.get("ebitda", 0),
                        "totalDebt": company.info.get("totalDebt", 0),
                        "netIncomeToCommon": company.info.get("netIncomeToCommon", 0),
                        "debtToEquity": company.info.get("debtToEquity", 0.0),
                        # Liquidity ratios
                        "quickRatio": company.info.get("quickRatio", 0.0),
                        "currentRatio": company.info.get("currentRatio", 0.0),
                        # Profitability metrics
                        "returnOnAssets": company.info.get("returnOnAssets", 0.0),
                        "returnOnEquity": company.info.get("returnOnEquity", 0.0),
                        "profitMargins": company.info.get("profitMargins", 0.0),
                        "grossMargins": company.info.get("grossMargins", 0.0),
                        "ebitdaMargins": company.info.get("ebitdaMargins", 0.0),
                        "operatingMargins": company.info.get("operatingMargins", 0.0),
                        "grossProfits": company.info.get("grossProfits", 0),
                        # Cash flow metrics
                        "freeCashflow": company.info.get("freeCashflow", 0),
                        "operatingCashflow": company.info.get("operatingCashflow", 0),
                        # Analyst and target metrics
                        "averageAnalystRating": company.info.get(
                            "averageAnalystRating", ""
                        ),
                        "recommendationMean": company.info.get(
                            "recommendationMean", 0.0
                        ),
                        "recommendationKey": company.info.get("recommendationKey", ""),
                        "numberOfAnalystOpinions": company.info.get(
                            "numberOfAnalystOpinions", 0
                        ),
                        "targetHighPrice": company.info.get("targetHighPrice", 0.0),
                        "targetLowPrice": company.info.get("targetLowPrice", 0.0),
                        "targetMeanPrice": company.info.get("targetMeanPrice", 0.0),
                        "targetMedianPrice": company.info.get("targetMedianPrice", 0.0),
                    }
            except Exception as e:
                self.logger.warning(
                    f"Could not fetch fundamentals for {symbol}: {str(e)}"
                )

            return df, splits_df, fundamentals

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

                    if not df.empty:
                        df = df.dropna()
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
        fundamentals_info: Optional[Dict[str, Union[str, int, float]]] = None,
    ) -> MarketDataResult:
        """Process market data for a given symbol."""
        parser = StockPriceDataParser(symbol=symbol, ticker_id=ticker_id)
        results = {}

        if price_df is not None:
            results["PRICE"] = parser.process_price_data(price_df)

        if split_df is not None:
            results["SPLIT"] = parser.process_split_data(split_df)

        if fundamentals_info is not None:
            results["FUNDAMENTALS"] = parser.process_fundamentals(
                fundamentals_info, date.today()
            )

        return results

    def process_stock(self, ticker: str, start_date: str) -> None:
        """Process historical stock data for a single company."""
        self.logger.info(f"Processing historical stock data for {ticker} starting from {start_date}")
        try:
            price_df, splits, fundamentals = self.fetch_stock_data(
                ticker, start_date=start_date
            )

            if price_df is None:
                self.logger.warning(f"Skipping {ticker} - no price data available")
                return

            results = self.process_market_data(
                symbol=ticker,
                ticker_id=self.get_ticker_id(ticker),
                price_df=price_df,
                split_df=splits,
                fundamentals_info=fundamentals,
            )

            with self.get_db_connection() as conn:
                self.execute_sql_statements(conn, results)

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
                    price_df, splits, fundamentals = self.fetch_stock_data(
                        symbol, start_date=start_date
                    )

                    if price_df is None:
                        self.logger.warning(f"Skipping {symbol} - no data available")
                        continue

                    results = self.process_market_data(
                        symbol=symbol,
                        ticker_id=ticker_id,
                        price_df=price_df,
                        split_df=splits,
                        fundamentals_info=fundamentals,
                    )

                    self.execute_sql_statements(conn, results)
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
                    price_df, splits, fundamentals = self.fetch_stock_data(symbol)

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
                        results = self.process_market_data(
                            symbol=symbol,
                            ticker_id=ticker_id,
                            price_df=price_df,
                            split_df=(
                                splits
                                if splits is not None and not splits.empty
                                else None
                            ),
                            fundamentals_info=fundamentals,
                        )

                        self.execute_sql_statements(conn, results)
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
