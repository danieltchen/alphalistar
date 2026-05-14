"""
db.py - Minimal database helpers for run_scraper dispatcher.
"""

import json
import os
from typing import Dict, List, Optional

import boto3
import psycopg2
from botocore.exceptions import ClientError
from psycopg2.extras import DictCursor


def _secret_to_db_config(secret_dict: Dict[str, str]) -> Dict[str, str]:
    dbname = secret_dict.get("dbname") or secret_dict.get("dbInstanceIdentifier")
    user = secret_dict.get("user") or secret_dict.get("username")
    password = secret_dict.get("password")
    host = secret_dict.get("host")
    port = str(secret_dict.get("port")) if secret_dict.get("port") is not None else None

    values = {
        "dbname": dbname,
        "host": host,
        "user": user,
        "password": password,
        "port": port,
    }
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise ValueError(f"Missing required secret fields: {', '.join(missing)}")

    return values  # type: ignore[return-value]


def get_secret(secret_name: str, region_name: str = "us-east-1") -> Dict[str, str]:
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        raise RuntimeError(f"Unable to fetch secret {secret_name}") from exc

    return json.loads(response["SecretString"])


def get_db_config(secret_name: Optional[str], region_name: str = "us-east-1") -> Dict[str, str]:
    if secret_name:
        return _secret_to_db_config(get_secret(secret_name, region_name))

    required_vars = {
        "dbname": "DB_NAME",
        "host": "DB_HOST",
        "user": "DB_USER",
        "password": "DB_PASS",
        "port": "DB_PORT",
    }
    config: Dict[str, str] = {}
    missing = []
    for key, env_name in required_vars.items():
        value = os.getenv(env_name)
        if value is None:
            missing.append(env_name)
        else:
            config[key] = value
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    return config


def get_active_ticker_symbols(db_config: Dict[str, str]) -> List[str]:
    with psycopg2.connect(
        dbname=db_config["dbname"],
        host=db_config["host"],
        user=db_config["user"],
        password=db_config["password"],
        port=db_config["port"],
    ) as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                """
                SELECT symbol
                FROM TICKER
                WHERE is_active = TRUE
                ORDER BY symbol
                """
            )
            return [str(row["symbol"]).upper() for row in cur.fetchall() if row.get("symbol")]
