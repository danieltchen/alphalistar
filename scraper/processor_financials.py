"""
processor_financials.py - Class for processing company financials from 10-K/10-Q filings
"""

from typing import Dict, Tuple, Optional, List, Union, Any
from datetime import date
import psycopg2.extensions
import logging
from pandas import DataFrame
import psycopg2
from psycopg2.extras import DictCursor
import time

try:
    from .edgar_wrapper import Company, set_identity, MultiFinancials  # type: ignore
except ImportError:
    from edgar_wrapper import Company, set_identity, MultiFinancials  # type: ignore


try:
    from .connector_database import DatabaseConnector
    from .parser_financial import FinancialDataParser
except ImportError:
    from connector_database import DatabaseConnector  # type: ignore
    from parser_financial import FinancialDataParser  # type: ignore

DataValue = Union[int, date, str, None]
SQLQuery = str
SQLValues = Tuple[DataValue, ...]
SQLInsert = Tuple[SQLQuery, SQLValues]
TableResult = Tuple[SQLQuery, List[SQLInsert]]
ProcessingResult = Dict[str, TableResult]
Connection = psycopg2.extensions.connection
DBConfig = Dict[str, str]


class FinancialsProcessor(DatabaseConnector):
    def __init__(self, db_config: DBConfig):
        self.db_config: DBConfig = db_config
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _normalize_single_filing(filing_or_list: Any) -> Optional[Any]:
        if filing_or_list is None:
            return None
        if hasattr(filing_or_list, "accession_no"):
            return filing_or_list
        if hasattr(filing_or_list, "__iter__"):
            filing_list = list(filing_or_list)
            return filing_list[0] if filing_list else None
        return filing_or_list

    @staticmethod
    def _filing_accession(filing_or_list: Any) -> Optional[str]:
        filing = FinancialsProcessor._normalize_single_filing(filing_or_list)
        if filing is None:
            return None
        acc = getattr(filing, "accession_no", None)
        return str(acc) if acc else None

    def get_latest_periods(self, ticker_id: int) -> Dict[str, Optional[Union[date, int]]]:
        """Latest annual/quarterly periods from financial_fact."""
        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    """
                    SELECT fiscal_year, fiscal_period_end
                    FROM financial_fact
                    WHERE ticker_id = %s AND period_type = 'annual'
                    ORDER BY fiscal_period_end DESC
                    LIMIT 1
                    """,
                    (ticker_id,),
                )
                annual_result = cur.fetchone()

                cur.execute(
                    """
                    SELECT fiscal_year, fiscal_period_end, quarter
                    FROM financial_fact
                    WHERE ticker_id = %s AND period_type = 'quarterly'
                    ORDER BY fiscal_period_end DESC
                    LIMIT 1
                    """,
                    (ticker_id,),
                )
                quarterly_result = cur.fetchone()

                return {
                    "annual_year": annual_result["fiscal_year"] if annual_result else None,
                    "annual_period": annual_result["fiscal_period_end"] if annual_result else None,
                    "quarterly_year": quarterly_result["fiscal_year"] if quarterly_result else None,
                    "quarterly_period": (
                        quarterly_result["fiscal_period_end"] if quarterly_result else None
                    ),
                    "latest_quarter": quarterly_result["quarter"] if quarterly_result else None,
                }

    def update_ticker_periods(
        self, ticker_id: int, latest_periods: Dict[str, Optional[Union[date, int]]]
    ) -> None:
        """Update ticker latest period pointers from normalized financial period data."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                annual_year = latest_periods.get("annual_year")
                quarterly_year = latest_periods.get("quarterly_year")
                annual_year_str = str(annual_year) if annual_year is not None else None
                quarterly_year_str = (
                    str(quarterly_year) if quarterly_year is not None else None
                )

                cur.execute(
                    """
                    UPDATE TICKER
                    SET latest_annual_period = %s,
                        latest_quarterly_period = %s,
                        latest_annual_year = %s,
                        latest_quarterly_year = %s,
                        latest_quarter = %s
                    WHERE id = %s
                    """,
                    (
                        latest_periods.get("annual_period"),
                        latest_periods.get("quarterly_period"),
                        annual_year_str,
                        quarterly_year_str,
                        latest_periods.get("latest_quarter"),
                        ticker_id,
                    ),
                )
                conn.commit()

    def _extract_statement_dataframes(
        self, filings: Union[List[object], object]
    ) -> Tuple[DataFrame, DataFrame, DataFrame]:
        if hasattr(filings, "accession_no"):
            filings_input = [filings]
        elif isinstance(filings, list):
            filings_input = filings
        else:
            filings_input = list(filings)

        financials = MultiFinancials.extract(filings_input)

        balance_sheet_stmt = financials.balance_sheet()
        income_stmt = financials.income_statement()
        cash_flow_stmt = financials.cashflow_statement()

        if balance_sheet_stmt is None or income_stmt is None or cash_flow_stmt is None:
            raise ValueError("Missing one or more required financial statements")

        return (
            balance_sheet_stmt.to_dataframe(),
            income_stmt.to_dataframe(),
            cash_flow_stmt.to_dataframe(),
        )

    def process_financial_statements(
        self,
        ticker_id: int,
        filing_is: DataFrame,
        filing_bs: DataFrame,
        filing_cs: DataFrame,
        is_annual: bool,
        filing_accession: Optional[str] = None,
    ) -> ProcessingResult:
        parser = FinancialDataParser(
            income_statement=filing_is,
            balance_sheet=filing_bs,
            cashflow=filing_cs,
            ticker_id=ticker_id,
            is_annual=is_annual,
            filing_accession=filing_accession,
        )
        return parser.build_processing_result()

    @staticmethod
    def _filings_to_list(filings: Any, max_count: int) -> List[Any]:
        """Normalize edgartools return shape into a list of filing objects (newest-first cap)."""
        if filings is None:
            return []
        if hasattr(filings, "accession_no"):
            return [filings]
        out: List[Any] = []
        try:
            iterator = iter(filings)
        except TypeError:
            return [filings]
        for i, item in enumerate(iterator):
            if i >= max_count:
                break
            out.append(item)
        return out

    def process_financials(
        self,
        conn: Connection,
        company: Company,
        ticker_id: int,
        symbol: str,
        annual_limit: int,
        quarterly_limit: int,
    ) -> None:
        try:
            annual_filings = company.latest("10-K", annual_limit)
            quarterly_filings = company.latest("10-Q", quarterly_limit)

            for filing in self._filings_to_list(annual_filings, annual_limit):
                try:
                    balance_sheet_df, income_stmt_df, cash_flow_df = (
                        self._extract_statement_dataframes(filing)
                    )

                    results = self.process_financial_statements(
                        ticker_id=ticker_id,
                        filing_is=income_stmt_df,
                        filing_bs=balance_sheet_df,
                        filing_cs=cash_flow_df,
                        is_annual=True,
                        filing_accession=self._filing_accession(filing),
                    )

                    self.execute_sql_statements(conn, results)

                except Exception as e:
                    self.logger.error(
                        "Error processing annual filing %s for %s: %s",
                        self._filing_accession(filing),
                        symbol,
                        str(e),
                    )
                    raise

            for filing in self._filings_to_list(quarterly_filings, quarterly_limit):
                try:
                    balance_sheet_df, income_stmt_df, cash_flow_df = (
                        self._extract_statement_dataframes(filing)
                    )

                    results = self.process_financial_statements(
                        ticker_id=ticker_id,
                        filing_is=income_stmt_df,
                        filing_bs=balance_sheet_df,
                        filing_cs=cash_flow_df,
                        is_annual=False,
                        filing_accession=self._filing_accession(filing),
                    )

                    self.execute_sql_statements(conn, results)

                except Exception as e:
                    self.logger.error(
                        "Error processing quarterly filing %s for %s: %s",
                        self._filing_accession(filing),
                        symbol,
                        str(e),
                    )
                    raise

            self.logger.info(f"Successfully processed all financials for {symbol}")

        except Exception as e:
            self.logger.error(f"Error processing company {symbol}: {str(e)}")
            raise

    def process_company(self, ticker: str, annual_limit: int, quarterly_limit: int) -> None:
        symbol = ticker.upper()
        ticker_id = self.get_ticker_id(symbol)

        with self.get_db_connection() as conn:
            try:
                identity = f"Alphalistar Limited alphalistai+{symbol}@gmail.com"
                set_identity(identity)
                company = Company(symbol)

                self.process_financials(
                    conn,
                    company,
                    ticker_id,
                    symbol,
                    annual_limit,
                    quarterly_limit,
                )
                self.update_ticker_periods(ticker_id, self.get_latest_periods(ticker_id))

            except Exception as e:
                self.logger.error(f"Error processing company {symbol}: {str(e)}")
                raise

    def process_companies(self, annual_limit: int, quarterly_limit: int) -> None:
        tickers = self.get_tickers()
        self.logger.info(f"Found {len(tickers)} tickers to process")

        with self.get_db_connection() as conn:
            for ticker in tickers:
                symbol = ticker["symbol"]
                ticker_id = ticker["id"]
                self.logger.info(f"Processing {symbol}")

                try:
                    identity = f"Alphalistar Limited alphalistai+{symbol}@gmail.com"
                    set_identity(identity)
                    company = Company(symbol)

                    self.process_financials(
                        conn,
                        company,
                        ticker_id,
                        symbol,
                        annual_limit,
                        quarterly_limit,
                    )
                    self.update_ticker_periods(ticker_id, self.get_latest_periods(ticker_id))

                    self.logger.info(f"Completed processing for {symbol}")
                    time.sleep(2)

                except Exception as e:
                    self.logger.error(f"Error processing company {symbol}: {str(e)}")
                    continue

        self.logger.info("Processing completed")
