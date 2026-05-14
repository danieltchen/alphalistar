"""
connector_database.py - Base class for database operations
"""

import os
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
import psycopg2
from psycopg2.extras import DictCursor, execute_batch

# Import AWS libraries for Secrets Manager
import json
import boto3
from botocore.exceptions import ClientError

# Type aliases
Connection = psycopg2.extensions.connection
ProcessingResult = Dict[str, Any]


class DatabaseConnector:
    """Base class for database operations."""
    STATIC_SCHEMA_TABLES = {"PRICE", "SPLIT", "FUNDAMENTALS", "FINANCIAL_FACT"}
    ALLOWED_PROCESS_NAMES = {"stocks", "financials", "press_releases"}

    def __init__(self, db_config: Dict[str, str]):
        """Initialize with database configuration."""
        self.db_config = db_config
        self.logger = logging.getLogger(__name__)

    ### Static Methods for AWS RDS Database Configuration from Secrets Manager ###
    @staticmethod
    def get_secret(secret_name: str, region_name: str = "us-east-1") -> Dict[str, str]:
        """
        Retrieve database credentials from AWS Secrets Manager.

        Args:
            secret_name: Name of the secret in AWS Secrets Manager
            region_name: AWS region where the secret is stored

        Returns:
            Dictionary containing the database credentials

        Raises:
            ClientError: If AWS API call fails
        """
        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region_name)

        try:
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        except ClientError as e:
            # For a list of exceptions thrown, see
            # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
            logging.error(f"Failed to retrieve secret {secret_name}: {e}")
            raise e

        secret_string = get_secret_value_response["SecretString"]

        # Parse the JSON secret
        try:
            secret_dict = json.loads(secret_string)
            assert isinstance(secret_dict, dict), "Secret must be a JSON object"
            return secret_dict
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in secret {secret_name}: {e}")

    @staticmethod
    def get_db_config_from_secrets(
        secret_name: str, region_name: str = "us-east-1"
    ) -> Dict[str, str]:
        """
        Get database configuration from AWS Secrets Manager.

        Args:
            secret_name: Name of the secret in AWS Secrets Manager
            region_name: AWS region where the secret is stored

        Returns:
            Dictionary containing database configuration

        Raises:
            ValueError: If required keys are missing from the secret
        """
        secret_dict = DatabaseConnector.get_secret(secret_name, region_name)

        # Map secret keys to database config keys if needed
        # Adjust these mappings based on how your secret is structured
        required_keys = ["dbInstanceIdentifier", "host", "username", "password", "port"]

        # Check if all required keys are present
        missing_keys = [key for key in required_keys if key not in secret_dict]
        if missing_keys:
            raise ValueError(
                f"Missing required keys in secret: {', '.join(missing_keys)}"
            )

        return {
            "dbname": secret_dict["dbname"],
            "host": secret_dict["host"],
            "user": secret_dict["user"],
            "password": secret_dict["password"],
            "port": secret_dict["port"],
        }

    @staticmethod
    def get_db_config_from_env() -> Dict[str, str]:
        """
        Get database configuration from environment variables (fallback).

        Returns:
            Dictionary containing database configuration

        Raises:
            ValueError: If required environment variables are not set
        """
        required_vars = {
            "dbname": "DB_NAME",
            "host": "DB_HOST",
            "user": "DB_USER",
            "password": "DB_PASS",
            "port": "DB_PORT",
        }

        config: Dict[str, str] = {}
        missing_vars = []

        for config_key, env_var in required_vars.items():
            value = os.getenv(env_var)
            if value is None:
                missing_vars.append(env_var)
            else:
                config[config_key] = value

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        return config

    @staticmethod
    def get_db_config(
        secret_name: Optional[str] = None, region_name: str = "us-east-1"
    ) -> Dict[str, str]:
        """
        Get database configuration, trying AWS Secrets Manager first, then environment variables.

        Args:
            secret_name: Optional name of the secret in AWS Secrets Manager
            region_name: AWS region where the secret is stored

        Returns:
            Dictionary containing database configuration
        """
        # If secret_name is provided, try AWS Secrets Manager first
        if secret_name:
            try:
                logging.info(
                    f"Attempting to retrieve database config from AWS Secrets Manager: {secret_name}"
                )
                return DatabaseConnector.get_db_config_from_secrets(
                    secret_name, region_name
                )
            except Exception as e:
                logging.warning(f"Failed to get config from AWS Secrets Manager: {e}")
                logging.info("Falling back to environment variables")

        # Fallback to environment variables
        return DatabaseConnector.get_db_config_from_env()

    def get_db_connection(self) -> Connection:
        """Create a connection to the PostgreSQL database."""
        return psycopg2.connect(
            dbname=self.db_config["dbname"],
            host=self.db_config["host"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            port=self.db_config["port"],
        )

    def get_ticker_id(self, ticker_name: str) -> int:
        """Fetch ticker id from symbol (or name as fallback) for active tickers."""
        normalized_ticker = ticker_name.strip()
        if not normalized_ticker:
            raise ValueError("Ticker cannot be empty")

        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM TICKER
                    WHERE is_active = TRUE
                      AND (
                        UPPER(symbol) = UPPER(%s)
                        OR UPPER(name) = UPPER(%s)
                      )
                    ORDER BY CASE
                        WHEN UPPER(symbol) = UPPER(%s) THEN 0
                        ELSE 1
                    END
                    LIMIT 1
                    """,
                    (normalized_ticker, normalized_ticker, normalized_ticker),
                )
                result = cur.fetchone()
                if result is None:
                    raise ValueError(f"Ticker not found: {normalized_ticker}")
                return int(result[0])  # Return the ticker ID as an integer

    def get_tickers(self) -> List[Dict[str, Any]]:
        """Fetch all tickers from the database."""
        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    "SELECT id, symbol, cik, name, exchange FROM TICKER WHERE is_active = TRUE"
                )
                return [dict(row) for row in cur.fetchall()]

    def _validate_process_name(self, process_name: str) -> None:
        if process_name not in self.ALLOWED_PROCESS_NAMES:
            raise ValueError(
                f"Unsupported process name '{process_name}'. "
                f"Expected one of {sorted(self.ALLOWED_PROCESS_NAMES)}"
            )

    def get_process_run_state(self, ticker_id: int, process_name: str) -> Optional[Dict[str, Any]]:
        """Fetch process run state for a ticker/process pair."""
        self._validate_process_name(process_name)
        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(
                    """
                    SELECT ticker_id, process_name, status, last_started_at,
                           last_completed_at, last_failed_at, last_success_cursor,
                           attempt_count, last_error, lock_token
                    FROM PROCESS_RUN_STATE
                    WHERE ticker_id = %s AND process_name = %s
                    """,
                    (ticker_id, process_name),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def try_start_process_run(
        self, ticker_id: int, process_name: str, stale_after_minutes: int = 90
    ) -> Optional[str]:
        """
        Attempt to acquire a process run lock.
        Returns a lock token if lock is acquired, else None.
        """
        self._validate_process_name(process_name)
        stale_cutoff = datetime.utcnow() - timedelta(minutes=stale_after_minutes)
        lock_token = str(uuid.uuid4())

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO PROCESS_RUN_STATE (ticker_id, process_name, status)
                    VALUES (%s, %s, 'idle')
                    ON CONFLICT (ticker_id, process_name) DO NOTHING
                    """,
                    (ticker_id, process_name),
                )
                cur.execute(
                    """
                    UPDATE PROCESS_RUN_STATE
                    SET status = 'running',
                        last_started_at = CURRENT_TIMESTAMP,
                        lock_token = %s,
                        last_error = NULL,
                        attempt_count = attempt_count + 1
                    WHERE ticker_id = %s
                      AND process_name = %s
                      AND (
                            status <> 'running'
                            OR last_started_at IS NULL
                            OR last_started_at < %s
                          )
                    RETURNING id
                    """,
                    (lock_token, ticker_id, process_name, stale_cutoff),
                )
                acquired = cur.fetchone() is not None
                conn.commit()
                return lock_token if acquired else None

    def mark_process_run_success(
        self,
        ticker_id: int,
        process_name: str,
        lock_token: str,
        cursor_payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Mark an acquired process run as successful."""
        self._validate_process_name(process_name)
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE PROCESS_RUN_STATE
                    SET status = 'success',
                        last_completed_at = CURRENT_TIMESTAMP,
                        last_success_cursor = %s::jsonb,
                        lock_token = NULL
                    WHERE ticker_id = %s
                      AND process_name = %s
                      AND lock_token = %s::uuid
                    RETURNING id
                    """,
                    (
                        json.dumps(cursor_payload or {}, default=str),
                        ticker_id,
                        process_name,
                        lock_token,
                    ),
                )
                updated = cur.fetchone() is not None
                conn.commit()
                return updated

    def mark_process_run_failed(
        self, ticker_id: int, process_name: str, lock_token: str, error_message: str
    ) -> bool:
        """Mark an acquired process run as failed."""
        self._validate_process_name(process_name)
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE PROCESS_RUN_STATE
                    SET status = 'failed',
                        last_failed_at = CURRENT_TIMESTAMP,
                        last_error = %s,
                        lock_token = NULL
                    WHERE ticker_id = %s
                      AND process_name = %s
                      AND lock_token = %s::uuid
                    RETURNING id
                    """,
                    (error_message[:5000], ticker_id, process_name, lock_token),
                )
                updated = cur.fetchone() is not None
                conn.commit()
                return updated

    def execute_sql_statements(
        self, conn: Connection, results: ProcessingResult
    ) -> None:
        """Execute the SQL statements for creating tables and inserting data."""
        with conn.cursor() as cur:
            try:
                # Avoid indefinite hangs on blocked locks / long-running statements.
                cur.execute("SET LOCAL lock_timeout = '10s'")
                cur.execute("SET LOCAL statement_timeout = '120s'")

                for table_name, (create_sql, inserts) in results.items():
                    table_regclass = f"public.{table_name.lower()}"
                    cur.execute("SELECT to_regclass(%s)", (table_regclass,))
                    table_exists = cur.fetchone()[0] is not None

                    skip_schema_update = (
                        table_exists and table_name.upper() in self.STATIC_SCHEMA_TABLES
                    )

                    if skip_schema_update:
                        self.logger.info(
                            f"Skipping schema update for {table_name} ({len(inserts)} rows pending)"
                        )
                    else:
                        self.logger.info(
                            f"Applying schema update for {table_name} ({len(inserts)} rows pending)"
                        )
                        # Create table if not exists
                        cur.execute(create_sql)

                    # Execute all inserts
                    if not inserts:
                        self.logger.info(f"{table_name}: no rows to insert")
                        continue

                    first_query = inserts[0][0]
                    can_batch = all(query == first_query for query, _ in inserts)

                    if can_batch:
                        self.logger.info(
                            f"{table_name}: starting batched inserts ({len(inserts)} rows)"
                        )
                        execute_batch(
                            cur,
                            first_query,
                            [values for _, values in inserts],
                            page_size=500,
                        )
                    else:
                        for idx, (insert_sql, values) in enumerate(inserts, start=1):
                            if idx == 1:
                                self.logger.info(
                                    f"{table_name}: starting inserts (first row of {len(inserts)})"
                                )
                            cur.execute(insert_sql, values)
                            if idx % 500 == 0:
                                self.logger.info(
                                    f"{table_name}: inserted {idx}/{len(inserts)} rows"
                                )

                    self.logger.info(f"{table_name}: inserted {len(inserts)} rows")

                conn.commit()
                self.logger.info("Database transaction committed successfully")

            except Exception as e:
                conn.rollback()
                self.logger.error(
                    f"Database error with execute_sql_statements: {str(e)}"
                )
                raise

    def insert_filing_record(
        self, conn: Connection, ticker_id: int, symbol: str, filing_info: Any
    ) -> int:
        """Insert a filing record and return its ID."""
        with conn.cursor() as cur:
            query = """
            INSERT INTO FILING (
                tickerId, symbol, type, accessionNo, year,
                filingDate, downloadDate, completed
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """

            filing_date = filing_info.filing_date
            if isinstance(filing_date, str):
                filing_date = datetime.strptime(filing_date, "%Y-%m-%d").date()
            elif isinstance(filing_date, datetime):
                filing_date = filing_date.date()

            values = (
                ticker_id,
                symbol,
                filing_info.form,
                filing_info.accession_no,
                filing_date.year,
                filing_date,
                date.today(),
                False,
            )

            cur.execute(query, values)
            result = cur.fetchone()
            if result is None:
                raise ValueError("Failed to insert filing record - no ID returned")
            filing_id: int = result[0]
            conn.commit()
            return filing_id
