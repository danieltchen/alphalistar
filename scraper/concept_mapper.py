"""
Map XBRL concept / standard_concept strings to canonical financial_line.line_code.
Anchor-first: prefer standard_concept when present; then concept; then YAML overrides.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

try:
    from .financial_gaap_map import GAAP_MAP
except ImportError:
    from financial_gaap_map import GAAP_MAP  # type: ignore

logger = logging.getLogger(__name__)


def normalize_xbrl_name(raw: Optional[str]) -> str:
    """Local-name style key: lowercase alphanumerics only (stable dict lookup)."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    if "}" in s:
        s = s.rsplit("}", 1)[-1]
    elif ":" in s:
        s = s.rsplit(":", 1)[-1]
    return "".join(c.lower() for c in s if c.isalnum())


def infer_standard_concept(concept: Optional[str]) -> Optional[str]:
    """
    When the statement row has no ``standard_concept``, derive a stable anchor label
    from the XBRL concept (local name, original casing).

    Fills ``financial_fact.source_standard_concept`` for facts such as
    ``us-gaap_EarningsPerShareBasic`` where edgartools often leaves standard_concept empty.
    """
    if not concept:
        return None
    s = str(concept).strip()
    if not s:
        return None
    if "}" in s:
        local = s.rsplit("}", 1)[-1].strip()
        return local or None
    if ":" in s:
        local = s.rsplit(":", 1)[-1].strip()
        return local or None
    sl = s.lower()
    for prefix in (
        "us-gaap_",
        "us-gaap:",
        "ifrs-full_",
        "ifrs-full:",
        "ifrs_",
        "ifrs:",
        "dei_",
        "dei:",
        "srt_",
        "srt:",
        "ecd_",
        "ecd:",
    ):
        if sl.startswith(prefix):
            rest = s[len(prefix) :].strip()
            return rest or None
    return None


def _taxonomy_prefixes() -> tuple[str, ...]:
    """Normalized (alnum-only) namespace prefixes seen on EDGAR XBRL concepts."""
    return (
        "usgaap",
        "ifrsfull",
        "ifrs",
        "dei",
        "srt",
        "ecd",
        "currency",
    )


def iter_lookup_keys(norm: str) -> list[str]:
    """
    Yield normalized keys to try against GAAP_MAP / overrides.

    edgartools sometimes emits ``us-gaap_Revenues`` (underscore, no colon). That becomes
    ``usgaaprevenues`` after normalize_xbrl_name, which would never match ``revenues``.
    We therefore also try stripping known taxonomy prefixes.
    """
    if not norm:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def add(k: str) -> None:
        if k and k not in seen:
            seen.add(k)
            out.append(k)

    add(norm)
    for pfx in _taxonomy_prefixes():
        if norm.startswith(pfx) and len(norm) > len(pfx):
            add(norm[len(pfx) :])
    return out


def _load_json_overrides() -> Dict[str, str]:
    path = Path(__file__).resolve().parent / "concept_overrides.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[str, str] = {}
    for row in data.get("overrides") or []:
        concept = row.get("concept")
        line_code = row.get("line_code")
        if not concept or not line_code:
            continue
        out[str(concept).strip()] = str(line_code).strip()
        out[normalize_xbrl_name(str(concept))] = str(line_code).strip()
    return out


_OVERRIDES_CACHE: Optional[Dict[str, str]] = None


def get_overrides() -> Dict[str, str]:
    global _OVERRIDES_CACHE
    if _OVERRIDES_CACHE is None:
        _OVERRIDES_CACHE = _load_json_overrides()
    return _OVERRIDES_CACHE


def map_to_line_code(
    *,
    concept: Optional[str],
    standard_concept: Optional[str],
    statement: str,
) -> Optional[str]:
    """
    Return line_code if mappable, else None (caller skips row).

    statement: 'balance' | 'income' | 'cashflow'
    """
    overrides = get_overrides()

    def try_key(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        raw_s = str(raw).strip()
        if raw_s in overrides:
            return overrides[raw_s]
        norm = normalize_xbrl_name(raw_s)
        if norm in overrides:
            return overrides[norm]
        for key in iter_lookup_keys(norm):
            if key in overrides:
                return overrides[key]
            if key in GAAP_MAP:
                line_code, stmt = GAAP_MAP[key]
                if stmt == statement:
                    return line_code
        return None

    # Anchor-first
    anchor = standard_concept if standard_concept and str(standard_concept).strip() else None
    if anchor:
        hit = try_key(anchor)
        if hit:
            return hit

    if concept and str(concept).strip():
        hit = try_key(concept)
        if hit:
            return hit

    # Issuer extension tags: ``aapl_IntangibleAssetsNetExcludingGoodwillNoncurrent``
    if concept and str(concept).strip():
        raw_s = str(concept).strip()
        if "_" in raw_s:
            prefix, _, rest = raw_s.partition("_")
            pl = prefix.lower().replace("-", "")
            blocked = {"us", "dei", "srt", "ecd", "currency", "na"}
            if (
                2 <= len(prefix) <= 5
                and prefix.replace("-", "").isalnum()
                and pl not in blocked
                and not (pl.startswith("usgaap") or pl.startswith("ifrs"))
                and rest.strip()
            ):
                hit = try_key(rest.strip())
                if hit:
                    return hit

    return None


def reload_overrides() -> None:
    """Tests / hot reload."""
    global _OVERRIDES_CACHE
    _OVERRIDES_CACHE = None
