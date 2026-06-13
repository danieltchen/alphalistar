"""
worker.py - SQS worker entrypoint for per-ticker scraping.
"""

import json
import logging
from typing import Any, Dict, List

from scraper.scrape import SingleStockScraper


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)


def _require(message: Dict[str, Any], field: str) -> Any:
    value = message.get(field)
    if value is None:
        raise ValueError(f"Missing required field: {field}")
    return value


def _process_message(message: Dict[str, Any]) -> None:
    ticker = str(_require(message, "ticker")).upper()
    scraper = SingleStockScraper(
        ticker=ticker,
        days=int(message.get("days", 5)),
        annual_limit=int(message.get("annual_limit", 1)),
        quarterly_limit=int(message.get("quarterly_limit", 1)),
        limit_8k=int(message.get("limit_8k", 2)),
        limit_10k=int(message.get("limit_10k", 1)),
        limit_10q=int(message.get("limit_10q", 1)),
        insider_limit=int(message.get("insider_limit", 10)),
        skip_market_check=bool(message.get("skip_market_check", False)),
        force_press_releases=bool(message.get("force_press_releases", False)),
    )
    scraper.run()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, List[Dict[str, str]]]:
    failures: List[Dict[str, str]] = []
    records = event.get("Records", [])
    logger.info("Received %s SQS record(s)", len(records))

    for record in records:
        message_id = record.get("messageId")
        try:
            body = record.get("body", "{}")
            message = json.loads(body)
            if not isinstance(message, dict):
                raise ValueError("Message body must decode to a JSON object")

            _process_message(message)
            logger.info(
                "Completed ticker scrape for message_id=%s ticker=%s request_id=%s",
                message_id,
                message.get("ticker"),
                message.get("request_id"),
            )
        except Exception as exc:
            logger.exception("Failed processing record message_id=%s: %s", message_id, exc)
            if message_id:
                failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
