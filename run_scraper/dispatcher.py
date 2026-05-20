"""
dispatcher.py - Lightweight SQS fan-out orchestrator for per-ticker scraping.
"""

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

import boto3

try:
    from .db import get_active_ticker_symbols, get_db_config
except ImportError:
    if __package__:
        raise
    from db import get_active_ticker_symbols, get_db_config  # type: ignore


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_config(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "queue_url": event.get("queue_url") or os.getenv("SCRAPE_QUEUE_URL"),
        "days": int(event.get("days", _env_int("SCRAPE_DAYS", 5))),
        "annual_limit": int(event.get("annual_limit", _env_int("SCRAPE_ANNUAL_LIMIT", 1))),
        "quarterly_limit": int(
            event.get("quarterly_limit", _env_int("SCRAPE_QUARTERLY_LIMIT", 1))
        ),
        "limit_8k": int(event.get("limit_8k", _env_int("SCRAPE_8K_LIMIT", 2))),
        "limit_10k": int(event.get("limit_10k", _env_int("SCRAPE_10K_LIMIT", 1))),
        "limit_10q": int(event.get("limit_10q", _env_int("SCRAPE_10Q_LIMIT", 1))),
        "skip_market_check": bool(
            event.get("skip_market_check", _env_bool("SCRAPE_SKIP_MARKET_CHECK", False))
        ),
        "force_press_releases": bool(
            event.get(
                "force_press_releases",
                _env_bool("SCRAPE_FORCE_PRESS_RELEASES", False),
            )
        ),
        "dry_run": bool(event.get("dry_run", False)),
        "max_tickers": event.get("max_tickers"),
        "tickers": event.get("tickers"),
        "secret_name": event.get("secret_name") or os.getenv("AWS_SECRET_NAME"),
        "region_name": event.get("region_name") or os.getenv("AWS_REGION", "us-east-1"),
    }


def _filter_tickers(symbols: List[str], tickers: Optional[Iterable[str]]) -> List[str]:
    if not tickers:
        return symbols

    requested = {str(t).upper() for t in tickers}
    filtered = [symbol for symbol in symbols if symbol in requested]
    missing = sorted(requested.difference(set(filtered)))
    if missing:
        logger.warning("Requested tickers not found/active: %s", ", ".join(missing))
    return filtered


def _build_message(symbol: str, config: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    return {
        "ticker": symbol,
        "days": config["days"],
        "annual_limit": config["annual_limit"],
        "quarterly_limit": config["quarterly_limit"],
        "limit_8k": config["limit_8k"],
        "limit_10k": config["limit_10k"],
        "limit_10q": config["limit_10q"],
        "skip_market_check": config["skip_market_check"],
        "force_press_releases": config["force_press_releases"],
        "request_id": request_id,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }


def dispatch(event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = event or {}
    config = _resolve_config(payload)
    queue_url = config["queue_url"]
    if not queue_url:
        raise ValueError("SCRAPE_QUEUE_URL must be set via env var or event.queue_url")

    db_config = get_db_config(
        secret_name=config["secret_name"],
        region_name=config["region_name"],
    )
    active_symbols = get_active_ticker_symbols(db_config)
    tickers = _filter_tickers(active_symbols, config["tickers"])

    max_tickers = config["max_tickers"]
    if max_tickers is not None:
        tickers = tickers[: int(max_tickers)]

    request_id = payload.get("request_id") or str(uuid4())
    summary = {
        "request_id": request_id,
        "queue_url": queue_url,
        "total_active_tickers": len(active_symbols),
        "selected_tickers": len(tickers),
        "enqueued_count": 0,
        "dry_run": config["dry_run"],
    }

    if config["dry_run"]:
        logger.info("[dry-run] would enqueue %s ticker(s)", len(tickers))
        return summary

    sqs = boto3.client("sqs", region_name=config["region_name"])
    for symbol in tickers:
        message_body = _build_message(symbol, config, request_id)
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
            MessageAttributes={
                "ticker": {"StringValue": symbol, "DataType": "String"},
                "request_id": {"StringValue": request_id, "DataType": "String"},
            },
        )
        summary["enqueued_count"] += 1

    logger.info("Enqueued %s ticker scrape jobs", summary["enqueued_count"])
    return summary


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        result = dispatch(event)
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as exc:
        logger.exception("Dispatcher failed: %s", exc)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fan out scrape jobs to SQS.")
    parser.add_argument("--queue-url", type=str, default=None)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--annual", type=int, dest="annual_limit", default=None)
    parser.add_argument("--quarterly", type=int, dest="quarterly_limit", default=None)
    parser.add_argument("--8k", type=int, dest="limit_8k", default=None)
    parser.add_argument("--10k", type=int, dest="limit_10k", default=None)
    parser.add_argument("--10q", type=int, dest="limit_10q", default=None)
    parser.add_argument("--skip-market-check", action="store_true", default=False)
    parser.add_argument("--force-press-releases", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--max-tickers", type=int, default=None)
    parser.add_argument("--tickers", nargs="*", default=None)
    args = parser.parse_args()

    event = {
        "queue_url": args.queue_url,
        "days": args.days,
        "annual_limit": args.annual_limit,
        "quarterly_limit": args.quarterly_limit,
        "limit_8k": args.limit_8k,
        "limit_10k": args.limit_10k,
        "limit_10q": args.limit_10q,
        "skip_market_check": args.skip_market_check,
        "force_press_releases": args.force_press_releases,
        "dry_run": args.dry_run,
        "max_tickers": args.max_tickers,
        "tickers": args.tickers,
    }
    cleaned_event = {k: v for k, v in event.items() if v is not None}
    result = dispatch(cleaned_event)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
