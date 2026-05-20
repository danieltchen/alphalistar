"""
scrape_latest_financials.py
This script runs as a CRON job to check for and process new financials from EDGAR.
"""

from typing import Dict, Any, Optional
from datetime import date, datetime
import logging
import pandas as pd
import time

# from edgar import Company, set_identity, MultiFinancials  # type: ignore

# Import from our wrapper instead of directly from edgar
try:
    from .edgar_wrapper import Company, set_identity, MultiFinancials
except ImportError:
    from edgar_wrapper import Company, set_identity, MultiFinancials


try:
    from .connector_database import DatabaseConnector
    from .processor_financials import FinancialsProcessor
except ImportError:
    from connector_database import DatabaseConnector  # type: ignore
    from processor_financials import FinancialsProcessor  # type: ignore


class LatestFinancialsProcessor(FinancialsProcessor):
    """
    Processor for checking and handling latest financials.
    Inherits from FinancialsProcessor to reuse core functionality.
    """

    def __init__(self, db_config: Dict[str, str]):
        """Initialize with database configuration."""
        super().__init__(db_config)
        # Set up logging for this specific processor
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        )
        self.logger = logging.getLogger(__name__)

    def get_latest_date_from_df(self, df: pd.DataFrame) -> date:
        """Extract the latest date from financial statement DataFrame."""
        skip_cols = {
            "concept",
            "index",
            "label",
            "standard_concept",
            "decimals",
            "units",
            "unit",
            "scale",
            "depth",
            "is_abstract",
            "preferred_sign",
        }
        candidate_columns = [
            col for col in df.columns if str(col).strip().lower() not in skip_cols
        ]
        if not candidate_columns:
            raise ValueError("No candidate date columns found in DataFrame")

        valid_dates = []
        allowed_formats = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y")

        # EDGAR frames can include non-date labels like "label" alongside period columns.
        # Parse only explicit date values/formats to avoid pandas format inference warnings.
        for column in candidate_columns:
            if isinstance(column, datetime):
                valid_dates.append(column.date())
                continue
            if isinstance(column, date):
                valid_dates.append(column)
                continue

            raw = str(column).strip()
            for fmt in allowed_formats:
                try:
                    valid_dates.append(datetime.strptime(raw, fmt).date())
                    break
                except ValueError:
                    continue

        if len(valid_dates) == 0:
            raise ValueError(
                f"No parseable date columns found in DataFrame: {[str(c) for c in candidate_columns]}"
            )

        latest_date = max(valid_dates)

        return latest_date

    def get_filing_date(self, filing_or_list: Any) -> Optional[date]:
        """Extract filing date from an EDGAR filing object/list."""
        filing = self._normalize_single_filing(filing_or_list)
        if filing is None or not hasattr(filing, "filing_date"):
            return None

        filing_date = filing.filing_date
        if isinstance(filing_date, date):
            return filing_date

        try:
            return datetime.strptime(str(filing_date), "%Y-%m-%d").date()
        except Exception:
            return None

    def process_new_financials(
        self,
        company: Company,
        ticker_id: int,
        symbol: str,
        latest_periods: Dict[str, Any],
    ) -> None:
        """Process new financial data if available."""
        try:
            with self.get_db_connection() as conn:
                annual_filing = None
                quarterly_filing = None
                try:
                    annual_filing = company.latest("10-K", 1)
                except Exception as exc:
                    self.logger.warning(
                        "[financials] Could not fetch latest 10-K for %s: %s",
                        symbol,
                        exc,
                    )
                try:
                    quarterly_filing = company.latest("10-Q", 1)
                except Exception as exc:
                    self.logger.warning(
                        "[financials] Could not fetch latest 10-Q for %s: %s",
                        symbol,
                        exc,
                    )

                if not annual_filing and not quarterly_filing:
                    self.logger.warning(
                        "[financials] No latest EDGAR filings for %s; skipping",
                        symbol,
                    )
                    return

                # Process new annual filing if available
                if annual_filing:
                    try:
                        annual_filing_date = self.get_filing_date(annual_filing)
                        bs_df, income_stmt_df, cash_flow_df = (
                            self._extract_statement_dataframes(annual_filing)
                        )
                        latest_date = annual_filing_date or self.get_latest_date_from_df(bs_df)

                        if (
                            latest_periods["annual_period"] is None
                            or latest_date > latest_periods["annual_period"]
                        ):
                            self.logger.info(f"Processing new annual data for {symbol}")

                            results = self.process_financial_statements(
                                ticker_id=ticker_id,
                                filing_is=income_stmt_df,
                                filing_bs=bs_df,
                                filing_cs=cash_flow_df,
                                is_annual=True,
                                filing_accession=self._filing_accession(annual_filing),
                            )

                            self.execute_sql_statements(conn, results)

                            latest_periods["annual_period"] = latest_date
                            latest_periods["annual_year"] = latest_date.year

                    except Exception as e:
                        self.logger.error(
                            f"Error processing new annual data for {symbol}: {str(e)}"
                        )
                        raise

                # Process new quarterly filing if available
                if quarterly_filing:
                    try:
                        quarterly_filing_date = self.get_filing_date(quarterly_filing)
                        bs_df, income_stmt_df, cash_flow_df = (
                            self._extract_statement_dataframes(quarterly_filing)
                        )
                        latest_date = (
                            quarterly_filing_date
                            or self.get_latest_date_from_df(bs_df)
                        )
                        latest_quarter = (latest_date.month - 1) // 3 + 1

                        if (
                            latest_periods["quarterly_period"] is None
                            or latest_date > latest_periods["quarterly_period"]
                        ):
                            self.logger.info(
                                f"Processing new quarterly data for {symbol}"
                            )

                            results = self.process_financial_statements(
                                ticker_id=ticker_id,
                                filing_is=income_stmt_df,
                                filing_bs=bs_df,
                                filing_cs=cash_flow_df,
                                is_annual=False,
                                filing_accession=self._filing_accession(quarterly_filing),
                            )

                            self.execute_sql_statements(conn, results)

                            latest_periods["quarterly_period"] = latest_date
                            latest_periods["quarterly_year"] = latest_date.year
                            latest_periods["latest_quarter"] = latest_quarter

                    except Exception as e:
                        self.logger.error(
                            f"Error processing new quarterly data for {symbol}: {str(e)}"
                        )
                        raise

                self.update_ticker_periods(ticker_id, latest_periods)

        except Exception as e:
            self.logger.error(f"Error checking new financials for {symbol}: {str(e)}")
            raise

    def process_all_companies(self) -> None:
        """Process all active companies for new financial data."""
        self.logger.info("Starting financial data check")

        tickers = self.get_tickers()

        for ticker in tickers:
            symbol = ticker["symbol"]
            ticker_id = ticker["id"]

            try:
                self.logger.info(f"Checking {symbol} for new financials")

                latest_periods = self.get_latest_periods(ticker_id)

                identity = f"Alphalistar Limited alphalistai+{symbol}@gmail.com"
                set_identity(identity)
                company = Company(symbol)

                self.process_new_financials(company, ticker_id, symbol, latest_periods)

                self.logger.info(f"Completed check for {symbol}")
                time.sleep(2)  # Rate limiting between companies

            except Exception as e:
                self.logger.error(f"Error processing company {symbol}: {str(e)}")
                continue

        self.logger.info("Completed financial data check")


def main() -> None:
    """Main function to check and process new financial data."""

    try:
        db_config = DatabaseConnector.get_db_config()
        processor = LatestFinancialsProcessor(db_config)
        processor.process_all_companies()

    except Exception as e:
        logging.error(f"Failed to process latest financials: {str(e)}")
        raise


if __name__ == "__main__":
    main()
