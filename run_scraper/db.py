"""
db.py - Minimal database helpers for run_scraper dispatcher.
"""

import json
import os
from typing import Any, Dict, List, Optional

import boto3
import psycopg2
from botocore.exceptions import ClientError
from psycopg2.extras import DictCursor

_APP_SECRET_CACHE: Optional[Dict[str, Any]] = None


def _aws_region(default: str = "us-east-1") -> str:
    return (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or default
    )


def get_secret(secret_name: str, region_name: str = "us-east-1") -> Dict[str, Any]:
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        raise RuntimeError(f"Unable to fetch secret {secret_name}") from exc

    return json.loads(response["SecretString"])


def _get_app_secret_dict(region_name: str) -> Dict[str, Any]:
    global _APP_SECRET_CACHE
    if _APP_SECRET_CACHE is not None:
        return _APP_SECRET_CACHE

    secret_name = os.getenv("AWS_APP_SECRET_NAME")
    if not secret_name:
        raise ValueError(
            "AWS_APP_SECRET_NAME is not set; cannot load connection fields from app secret"
        )

    parsed = get_secret(secret_name, region_name)
    if not isinstance(parsed, dict):
        raise ValueError(f"App secret {secret_name} must be a JSON object")
    _APP_SECRET_CACHE = parsed
    return parsed


def _connection_fields_from_env_or_app(region_name: str) -> Dict[str, str]:
    dbname = os.getenv("DB_NAME")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")

    if dbname and host and port:
        return {"dbname": dbname, "host": host, "port": str(port)}

    if os.getenv("AWS_APP_SECRET_NAME"):
        secret_dict = _get_app_secret_dict(region_name)
        dbname = dbname or secret_dict.get("dbname") or secret_dict.get("dbInstanceIdentifier")
        host = host or secret_dict.get("host")
        port = port or secret_dict.get("port")

    missing = []
    if not dbname:
        missing.append("DB_NAME or app secret dbname/dbInstanceIdentifier")
    if not host:
        missing.append("DB_HOST or app secret host")
    if not port:
        missing.append("DB_PORT or app secret port")
    if missing:
        raise ValueError(f"Missing database connection fields: {', '.join(missing)}")

    return {"dbname": str(dbname), "host": str(host), "port": str(port)}


def _credentials_from_rds_secret(secret_dict: Dict[str, Any]) -> Dict[str, str]:
    user = secret_dict.get("user") or secret_dict.get("username")
    password = secret_dict.get("password")
    missing = []
    if not user:
        missing.append("username or user")
    if not password:
        missing.append("password")
    if missing:
        raise ValueError(f"Missing required keys in RDS secret: {', '.join(missing)}")
    return {"user": str(user), "password": str(password)}


def _secret_to_db_config(secret_dict: Dict[str, Any]) -> Dict[str, str]:
    """Single-secret legacy shape (full connection in one JSON blob)."""
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


def get_db_config_from_merged_secrets(
    credentials_secret_name: str, region_name: str
) -> Dict[str, str]:
    creds_secret = get_secret(credentials_secret_name, region_name)
    credentials = _credentials_from_rds_secret(creds_secret)
    connection = _connection_fields_from_env_or_app(region_name)
    return {
        "dbname": connection["dbname"],
        "host": connection["host"],
        "port": connection["port"],
        "user": credentials["user"],
        "password": credentials["password"],
    }


def get_db_config(secret_name: Optional[str], region_name: str = "us-east-1") -> Dict[str, str]:
    region = region_name or _aws_region()
    credentials_secret = secret_name or os.getenv("AWS_SECRET_NAME")

    if credentials_secret:
        try:
            if os.getenv("AWS_APP_SECRET_NAME") or (
                os.getenv("DB_NAME") and os.getenv("DB_HOST") and os.getenv("DB_PORT")
            ):
                return get_db_config_from_merged_secrets(credentials_secret, region)
            return _secret_to_db_config(get_secret(credentials_secret, region))
        except Exception:
            pass

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
