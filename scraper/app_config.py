"""
app_config.py - Runtime configuration from environment variables and/or a single app Secrets Manager JSON blob.

Env vars take precedence over Secrets Manager (local dev). Secret payloads are never logged.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_APP_SECRET_CACHE: Optional[Dict[str, Any]] = None
_APP_SECRET_LOAD_FAILED = False

ENV_APP_SECRET_NAME = "AWS_APP_SECRET_NAME"
ENV_AWS_REGION = "AWS_REGION"
ENV_AWS_DEFAULT_REGION = "AWS_DEFAULT_REGION"


def get_aws_region(default: str = "us-east-1") -> str:
    return (
        os.getenv(ENV_AWS_REGION)
        or os.getenv(ENV_AWS_DEFAULT_REGION)
        or default
    )


def _fetch_app_secret_dict(region_name: str) -> Dict[str, Any]:
    secret_name = os.getenv(ENV_APP_SECRET_NAME)
    if not secret_name:
        raise ValueError(
            f"{ENV_APP_SECRET_NAME} is not set; cannot load configuration from Secrets Manager"
        )

    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        logger.error("Failed to retrieve app secret (id=%s)", secret_name)
        raise RuntimeError(f"Unable to fetch app secret {secret_name}") from exc

    payload = response.get("SecretString")
    if not payload:
        raise ValueError(f"App secret {secret_name} has no SecretString")

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in app secret {secret_name}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"App secret {secret_name} must be a JSON object")

    return parsed


def get_app_secret_dict(region_name: Optional[str] = None) -> Dict[str, Any]:
    """Return the parsed app secret JSON, cached for the lifetime of the process."""
    global _APP_SECRET_CACHE, _APP_SECRET_LOAD_FAILED

    if _APP_SECRET_CACHE is not None:
        return _APP_SECRET_CACHE

    if _APP_SECRET_LOAD_FAILED:
        raise RuntimeError("App secret was already requested and failed to load")

    region = region_name or get_aws_region()
    _APP_SECRET_CACHE = _fetch_app_secret_dict(region)
    return _APP_SECRET_CACHE


def get_env_or_app_secret(
    env_var: str,
    secret_key: Optional[str] = None,
    *,
    region_name: Optional[str] = None,
    required: bool = True,
) -> Optional[str]:
    """
    Resolve a config value: process environment first, then a key from the app secret JSON.

    secret_key defaults to env_var when omitted (e.g. OPENAI_API_KEY in both places).
    """
    value = os.getenv(env_var)
    if value is not None and value != "":
        return value

    key = secret_key if secret_key is not None else env_var
    if not os.getenv(ENV_APP_SECRET_NAME):
        if required:
            raise ValueError(
                f"Missing {env_var} in environment and {ENV_APP_SECRET_NAME} is not set"
            )
        return None

    try:
        secret_dict = get_app_secret_dict(region_name)
    except Exception:
        global _APP_SECRET_LOAD_FAILED
        _APP_SECRET_LOAD_FAILED = True
        raise

    raw = secret_dict.get(key)
    if raw is None or raw == "":
        if required:
            raise ValueError(
                f"Missing {env_var} in environment and key {key!r} in app secret"
            )
        return None

    return str(raw)


def get_openai_api_key(region_name: Optional[str] = None) -> str:
    """OPENAI_API_KEY from environment, else from the app secret."""
    key = get_env_or_app_secret("OPENAI_API_KEY", region_name=region_name, required=True)
    assert key is not None
    return key


def get_db_connection_fields(region_name: Optional[str] = None) -> Dict[str, str]:
    """
    Non-credential DB fields: dbname, host, port from env (DB_NAME, DB_HOST, DB_PORT)
    or app secret (dbname / dbInstanceIdentifier, host, port).
    """
    region = region_name or get_aws_region()

    dbname = os.getenv("DB_NAME")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")

    if dbname and host and port:
        return {"dbname": dbname, "host": host, "port": str(port)}

    if os.getenv(ENV_APP_SECRET_NAME):
        secret_dict = get_app_secret_dict(region)
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

    return {
        "dbname": str(dbname),
        "host": str(host),
        "port": str(port),
    }
