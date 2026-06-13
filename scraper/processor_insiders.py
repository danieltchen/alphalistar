"""
processor_insiders.py - Process SEC Forms 3, 4, and 5 insider ownership filings.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

import psycopg2

try:
    from .connector_database import DatabaseConnector, is_edgar_eligible
    from .processor_financials import _safe_company
except ImportError:
    from connector_database import DatabaseConnector, is_edgar_eligible  # type: ignore
    from processor_financials import _safe_company  # type: ignore


logger = logging.getLogger(__name__)


def _rollback_if_open(conn: Any, logger_: logging.Logger) -> None:
    if getattr(conn, "closed", 1):
        return
    try:
        conn.rollback()
    except psycopg2.Error as exc:
        logger_.warning("[insiders] rollback failed after prior error: %s", exc)


class InsiderTransactionsProcessor(DatabaseConnector):
    """Extract and store insider ownership filings into a structured ledger."""

    FORMS = ["3", "4", "5"]

    @staticmethod
    def _is_missing(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        try:
            return bool(value != value)
        except Exception:
            return False

    @classmethod
    def _clean_text(cls, value: Any) -> Optional[str]:
        if cls._is_missing(value):
            return None
        text = str(value).strip()
        return text if text else None

    @classmethod
    def _to_date(cls, value: Any) -> Optional[date]:
        if cls._is_missing(value):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    @classmethod
    def _to_decimal(cls, value: Any) -> Optional[Decimal]:
        if cls._is_missing(value):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def _to_int(cls, value: Any) -> Optional[int]:
        decimal_value = cls._to_decimal(value)
        if decimal_value is None:
            return None
        return int(decimal_value)

    @classmethod
    def _get_first(cls, obj: Any, *names: str) -> Any:
        for name in names:
            if isinstance(obj, dict) and name in obj:
                value = obj[name]
            else:
                value = getattr(obj, name, None)
            if not cls._is_missing(value):
                return value
        return None

    @classmethod
    def _normalize_filing_list(cls, filing_list: Any) -> List[Any]:
        if filing_list is None:
            return []
        if hasattr(filing_list, "accession_no"):
            return [filing_list]
        if isinstance(filing_list, Iterable):
            return list(filing_list)
        return [filing_list]

    @classmethod
    def _accession_no(cls, filing: Any) -> Optional[str]:
        value = cls._get_first(filing, "accession_no", "accession_number", "accessionNo")
        return cls._clean_text(value)

    @classmethod
    def _form_type(cls, filing: Any, filing_obj: Any) -> str:
        value = cls._get_first(filing, "form", "form_type") or cls._get_first(
            filing_obj, "form", "form_type"
        )
        form_type = str(value).replace("Form", "").strip() if value else ""
        return form_type

    @classmethod
    def _primary_owner(cls, filing_obj: Any) -> Optional[Any]:
        owners = getattr(filing_obj, "reporting_owners", None)
        if owners is None:
            return None
        try:
            owner_list = list(owners)
            return owner_list[0] if owner_list else None
        except Exception:
            return None

    def _upsert_insider(self, conn: Any, name: str, cik: Optional[str]) -> int:
        with conn.cursor() as cur:
            if cik:
                cur.execute(
                    """
                    INSERT INTO insider (cik, name)
                    VALUES (%s, %s)
                    ON CONFLICT (cik) DO UPDATE
                    SET name = EXCLUDED.name,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """,
                    (cik, name),
                )
                result = cur.fetchone()
                if result is None:
                    raise ValueError("Failed to upsert insider")
                return int(result[0])

            cur.execute(
                """
                SELECT id
                FROM insider
                WHERE cik IS NULL AND name = %s
                LIMIT 1
                """,
                (name,),
            )
            existing = cur.fetchone()
            if existing:
                return int(existing[0])

            cur.execute(
                "INSERT INTO insider (name) VALUES (%s) RETURNING id",
                (name,),
            )
            result = cur.fetchone()
            if result is None:
                raise ValueError("Failed to insert insider")
            return int(result[0])

    def _upsert_insider_filing(
        self,
        conn: Any,
        ticker_id: int,
        insider_id: int,
        accession_no: str,
        filing: Any,
        filing_obj: Any,
        summary: Any,
        owner: Any,
    ) -> int:
        form_type = self._form_type(filing, filing_obj)
        filing_date = self._to_date(self._get_first(filing, "filing_date"))
        reporting_period = self._to_date(
            self._get_first(summary, "reporting_date")
            or self._get_first(filing_obj, "reporting_period")
        )
        if filing_date is None:
            filing_date = reporting_period or date.today()

        issuer = getattr(filing_obj, "issuer", None)
        issuer_name = self._clean_text(self._get_first(summary, "issuer_name")) or self._clean_text(
            self._get_first(issuer, "name")
        )
        insider_name = self._clean_text(self._get_first(summary, "insider_name")) or self._clean_text(
            self._get_first(filing_obj, "insider_name")
        )
        if not insider_name:
            insider_name = self._clean_text(self._get_first(owner, "name")) or "Unknown Insider"

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO insider_filing (
                    ticker_id, insider_id, accession_no, form_type, is_amendment,
                    filing_date, reporting_period, insider_name, issuer_name, position,
                    is_director, is_officer, is_ten_pct_owner, officer_title,
                    primary_activity, net_change, net_value, remaining_shares,
                    has_10b5_1_plan, completed
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, FALSE
                )
                ON CONFLICT (accession_no) DO UPDATE
                SET ticker_id = EXCLUDED.ticker_id,
                    insider_id = EXCLUDED.insider_id,
                    form_type = EXCLUDED.form_type,
                    is_amendment = EXCLUDED.is_amendment,
                    filing_date = EXCLUDED.filing_date,
                    reporting_period = EXCLUDED.reporting_period,
                    insider_name = EXCLUDED.insider_name,
                    issuer_name = EXCLUDED.issuer_name,
                    position = EXCLUDED.position,
                    is_director = EXCLUDED.is_director,
                    is_officer = EXCLUDED.is_officer,
                    is_ten_pct_owner = EXCLUDED.is_ten_pct_owner,
                    officer_title = EXCLUDED.officer_title,
                    primary_activity = EXCLUDED.primary_activity,
                    net_change = EXCLUDED.net_change,
                    net_value = EXCLUDED.net_value,
                    remaining_shares = EXCLUDED.remaining_shares,
                    has_10b5_1_plan = EXCLUDED.has_10b5_1_plan,
                    extracted_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (
                    ticker_id,
                    insider_id,
                    accession_no,
                    form_type,
                    form_type.endswith("/A"),
                    filing_date,
                    reporting_period,
                    insider_name,
                    issuer_name,
                    self._clean_text(self._get_first(summary, "position"))
                    or self._clean_text(self._get_first(owner, "position")),
                    self._get_first(owner, "is_director"),
                    self._get_first(owner, "is_officer"),
                    self._get_first(owner, "is_ten_pct_owner"),
                    self._clean_text(self._get_first(owner, "officer_title")),
                    self._clean_text(self._get_first(summary, "primary_activity")),
                    self._to_int(self._get_first(summary, "net_change")),
                    self._to_decimal(self._get_first(summary, "net_value")),
                    self._to_int(self._get_first(summary, "remaining_shares")),
                    self._get_first(summary, "has_10b5_1_plan"),
                ),
            )
            result = cur.fetchone()
            if result is None:
                raise ValueError("Failed to upsert insider filing")
            return int(result[0])

    def _ensure_transaction_code(
        self, conn: Any, code: Optional[str], label: Optional[str], description: Optional[str]
    ) -> None:
        if not code:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO insider_transaction_code (code, label, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (code) DO NOTHING
                """,
                (code, label or f"Other ({code})", description or f"Other ({code})"),
            )

    def _transaction_rows_from_table(self, filing_obj: Any, table_name: str, is_derivative: bool) -> List[Dict[str, Any]]:
        table = getattr(filing_obj, table_name, None)
        if table is None:
            return []
        transactions = getattr(table, "transactions", None)
        if transactions is None:
            return []

        rows: List[Dict[str, Any]] = []
        try:
            iterable = list(transactions)
        except Exception:
            return []

        for idx, transaction in enumerate(iterable, start=1):
            rows.append(
                {
                    "line_number": idx,
                    "transaction_date": self._to_date(
                        self._get_first(transaction, "date", "transaction_date")
                    ),
                    "security_title": self._clean_text(
                        self._get_first(transaction, "security", "security_title")
                    ),
                    "transaction_code": self._clean_text(
                        self._get_first(transaction, "transaction_code", "code")
                    ),
                    "transaction_label": self._clean_text(
                        self._get_first(transaction, "transaction_type", "display_name")
                    ),
                    "transaction_description": self._clean_text(
                        self._get_first(transaction, "code_description", "description")
                    ),
                    "acquired_disposed": self._clean_text(
                        self._get_first(transaction, "acquired_disposed", "acquired_disposed_code")
                    ),
                    "shares": self._to_decimal(
                        self._get_first(transaction, "shares", "shares_numeric")
                    ),
                    "price_per_share": self._to_decimal(
                        self._get_first(transaction, "price", "price_per_share", "price_numeric")
                    ),
                    "transaction_value": self._to_decimal(
                        self._get_first(transaction, "value", "value_numeric")
                    ),
                    "ownership": self._clean_text(
                        self._get_first(transaction, "direct_indirect", "ownership")
                    ),
                    "ownership_nature": self._clean_text(
                        self._get_first(transaction, "nature_of_ownership", "ownership_nature")
                    ),
                    "shares_owned_following": self._to_decimal(
                        self._get_first(
                            transaction,
                            "remaining",
                            "shares_owned_following_transaction",
                            "shares_owned_following",
                        )
                    ),
                    "is_derivative": is_derivative,
                    "exercise_price": self._to_decimal(
                        self._get_first(transaction, "exercise_price")
                    ),
                    "expiration_date": self._to_date(
                        self._get_first(transaction, "expiration_date")
                    ),
                    "underlying_security_title": self._clean_text(
                        self._get_first(transaction, "underlying_security", "underlying_security_title")
                    ),
                    "underlying_shares": self._to_decimal(
                        self._get_first(transaction, "underlying_shares")
                    ),
                    "is_10b5_1": self._get_first(transaction, "is_10b5_1_plan"),
                    "footnotes": self._clean_text(
                        self._get_first(transaction, "footnotes", "footnotes_text")
                    ),
                }
            )
        return rows

    def _transaction_rows_from_dataframe(self, filing_obj: Any) -> List[Dict[str, Any]]:
        try:
            df = filing_obj.to_dataframe()
        except Exception:
            return []
        if df is None or getattr(df, "empty", True):
            return []

        rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(df.to_dict("records"), start=1):
            form_label = self._clean_text(row.get("Form")) or ""
            is_form3_holding = "Security Type" in row
            security_type = self._clean_text(row.get("Security Type")) or ""
            is_derivative = "derivative" in security_type.lower()
            shares = self._to_decimal(row.get("Shares"))
            underlying_shares = self._to_decimal(row.get("Underlying Shares"))
            rows.append(
                {
                    "line_number": idx,
                    "transaction_date": self._to_date(row.get("Date")),
                    "security_title": self._clean_text(
                        row.get("Security Title")
                        or row.get("Security")
                        or ("Common Stock" if not is_form3_holding else None)
                        or row.get("Transaction Type")
                    ),
                    "transaction_code": self._clean_text(row.get("Code"))
                    or ("H" if is_form3_holding else None),
                    "transaction_label": self._clean_text(row.get("Transaction Type")),
                    "transaction_description": self._clean_text(row.get("Description")),
                    "acquired_disposed": None,
                    "shares": shares,
                    "price_per_share": self._to_decimal(row.get("Price")),
                    "transaction_value": self._to_decimal(row.get("Value")),
                    "ownership": "D"
                    if row.get("Ownership Type") == "Direct"
                    else "I"
                    if row.get("Ownership Type") == "Indirect"
                    else None,
                    "ownership_nature": self._clean_text(row.get("Ownership Nature")),
                    "shares_owned_following": (
                        underlying_shares if is_form3_holding and is_derivative else shares
                    )
                    if is_form3_holding
                    else self._to_decimal(row.get("Remaining Shares")),
                    "is_derivative": is_derivative,
                    "exercise_price": self._to_decimal(row.get("Exercise Price")),
                    "expiration_date": self._to_date(row.get("Expiration Date")),
                    "underlying_security_title": self._clean_text(row.get("Underlying Security")),
                    "underlying_shares": underlying_shares,
                    "is_10b5_1": None,
                    "footnotes": None,
                    "form_label": form_label,
                }
            )
        return rows

    def _transaction_rows(self, filing_obj: Any) -> List[Dict[str, Any]]:
        # edgartools 5.36 exposes stable normalized DataFrames for Forms 3/4/5.
        # Iterating table transaction holders can block on some ownership objects.
        return self._transaction_rows_from_dataframe(filing_obj)

    def _insert_transactions(
        self,
        conn: Any,
        insider_filing_id: int,
        ticker_id: int,
        insider_id: int,
        rows: List[Dict[str, Any]],
    ) -> None:
        with conn.cursor() as cur:
            for row in rows:
                code = row.get("transaction_code")
                self._ensure_transaction_code(
                    conn,
                    code,
                    row.get("transaction_label"),
                    row.get("transaction_description"),
                )
                cur.execute(
                    """
                    INSERT INTO insider_transaction (
                        insider_filing_id, ticker_id, insider_id, transaction_date,
                        security_title, transaction_code, acquired_disposed, shares,
                        price_per_share, transaction_value, ownership, ownership_nature,
                        shares_owned_following, is_derivative, exercise_price, expiration_date,
                        underlying_security_title, underlying_shares, is_10b5_1, footnotes,
                        line_number
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s
                    )
                    ON CONFLICT (insider_filing_id, is_derivative, line_number)
                    DO UPDATE SET
                        transaction_date = EXCLUDED.transaction_date,
                        security_title = EXCLUDED.security_title,
                        transaction_code = EXCLUDED.transaction_code,
                        acquired_disposed = EXCLUDED.acquired_disposed,
                        shares = EXCLUDED.shares,
                        price_per_share = EXCLUDED.price_per_share,
                        transaction_value = EXCLUDED.transaction_value,
                        ownership = EXCLUDED.ownership,
                        ownership_nature = EXCLUDED.ownership_nature,
                        shares_owned_following = EXCLUDED.shares_owned_following,
                        exercise_price = EXCLUDED.exercise_price,
                        expiration_date = EXCLUDED.expiration_date,
                        underlying_security_title = EXCLUDED.underlying_security_title,
                        underlying_shares = EXCLUDED.underlying_shares,
                        is_10b5_1 = EXCLUDED.is_10b5_1,
                        footnotes = EXCLUDED.footnotes,
                        extracted_at = CURRENT_TIMESTAMP
                    """,
                    (
                        insider_filing_id,
                        ticker_id,
                        insider_id,
                        row.get("transaction_date"),
                        row.get("security_title"),
                        code,
                        row.get("acquired_disposed"),
                        row.get("shares"),
                        row.get("price_per_share"),
                        row.get("transaction_value"),
                        row.get("ownership"),
                        row.get("ownership_nature"),
                        row.get("shares_owned_following"),
                        row.get("is_derivative", False),
                        row.get("exercise_price"),
                        row.get("expiration_date"),
                        row.get("underlying_security_title"),
                        row.get("underlying_shares"),
                        row.get("is_10b5_1"),
                        row.get("footnotes"),
                        row.get("line_number"),
                    ),
                )

    def check_insider_filing_completed(self, conn: Any, accession_no: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM insider_filing
                    WHERE accession_no = %s AND completed = TRUE
                )
                """,
                (accession_no,),
            )
            result = cur.fetchone()
            return bool(result[0]) if result else False

    def process_filing(self, conn: Any, filing: Any, ticker_id: int, symbol: str) -> bool:
        accession_no = self._accession_no(filing)
        if not accession_no:
            self.logger.warning("[insiders] skipping filing without accession for %s", symbol)
            return False
        if self.check_insider_filing_completed(conn, accession_no):
            self.logger.info("[insiders] filing %s already completed; skipping", accession_no)
            return False
        # Close the read-only transaction opened by the completed-check before the
        # SEC fetch/parse below, so the connection is not left idle-in-transaction
        # while edgartools performs network I/O.
        conn.commit()

        filing_obj = filing.obj()
        summary = filing_obj.get_ownership_summary()
        owner = self._primary_owner(filing_obj)
        insider_name = self._clean_text(self._get_first(summary, "insider_name")) or self._clean_text(
            self._get_first(filing_obj, "insider_name")
        )
        if not insider_name:
            insider_name = self._clean_text(self._get_first(owner, "name")) or "Unknown Insider"
        insider_id = self._upsert_insider(
            conn,
            insider_name,
            self._clean_text(self._get_first(owner, "cik")),
        )
        insider_filing_id = self._upsert_insider_filing(
            conn,
            ticker_id,
            insider_id,
            accession_no,
            filing,
            filing_obj,
            summary,
            owner,
        )
        rows = self._transaction_rows(filing_obj)
        self._insert_transactions(conn, insider_filing_id, ticker_id, insider_id, rows)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE insider_filing SET completed = TRUE WHERE id = %s",
                (insider_filing_id,),
            )
        self.logger.info(
            "[insiders] processed %s %s for %s (%s row(s))",
            self._form_type(filing, filing_obj),
            accession_no,
            symbol,
            len(rows),
        )
        return True

    def process_company(self, ticker: str, limit_form345: int = 100) -> None:
        symbol = ticker.upper()
        ticker_id = self.get_ticker_id(symbol)
        company = _safe_company(symbol)
        if company is None:
            self.logger.warning("[insiders] EDGAR could not resolve %s; skipping", symbol)
            return

        with self.get_db_connection() as conn:
            processed_count = 0
            try:
                for form_type in self.FORMS:
                    filings = company.get_filings(form=form_type)
                    filing_list = self._normalize_filing_list(filings.latest(limit_form345))
                    self.logger.info(
                        "[insiders] retrieved %s Form %s filing(s) for %s",
                        len(filing_list),
                        form_type,
                        symbol,
                    )
                    for filing in filing_list:
                        try:
                            if self.process_filing(conn, filing, ticker_id, symbol):
                                processed_count += 1
                            conn.commit()
                            time.sleep(1)
                        except psycopg2.Error:
                            _rollback_if_open(conn, self.logger)
                            raise
                        except Exception as exc:
                            _rollback_if_open(conn, self.logger)
                            self.logger.error(
                                "[insiders] error processing filing %s for %s: %s",
                                self._accession_no(filing),
                                symbol,
                                exc,
                            )
                            continue
                self.logger.info(
                    "[insiders] completed %s with %s processed filing(s)",
                    symbol,
                    processed_count,
                )
            except Exception:
                _rollback_if_open(conn, self.logger)
                raise

    def process_companies(self, limit_form345: int = 100) -> None:
        tickers = self.get_tickers()
        self.logger.info("[insiders] found %s tickers to process", len(tickers))
        for ticker in tickers:
            if not is_edgar_eligible(ticker.get("quote_type")):
                self.logger.info(
                    "[insiders] %s quote_type=%s; skipping EDGAR",
                    ticker["symbol"],
                    ticker.get("quote_type"),
                )
                continue
            try:
                self.process_company(ticker["symbol"], limit_form345=limit_form345)
            except Exception as exc:
                self.logger.error(
                    "[insiders] error processing company %s: %s",
                    ticker["symbol"],
                    exc,
                )
                continue
