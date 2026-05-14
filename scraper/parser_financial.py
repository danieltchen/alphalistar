from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from pandas import DataFrame
from pydantic import BaseModel, Field

try:
    from .concept_mapper import (
        infer_standard_concept,
        iter_lookup_keys,
        map_to_line_code,
        normalize_xbrl_name,
    )
except ImportError:
    from concept_mapper import (  # type: ignore
        infer_standard_concept,
        iter_lookup_keys,
        map_to_line_code,
        normalize_xbrl_name,
    )

logger = logging.getLogger(__name__)

# When several XBRL rows map to the same financial_fact grain, prefer the row whose
# normalized local name matches these totals first (avoids picking AOCI vs total equity, etc.).
_MERGE_PREFERRED_LOCAL_NAMES: dict[str, tuple[str, ...]] = {
    "stockholders_equity": ("stockholdersequity",),
    "net_income": ("netincomeloss", "profitloss"),
    "debt_current": (
        "longtermdebtcurrent",
        "longtermdebtandcapitalsecuritycurrent",
        "shorttermborrowings",
    ),
    "cashflow_operating": ("netcashprovidedbyusedinoperatingactivities",),
    "cashflow_investing": ("netcashprovidedbyusedininvestingactivities",),
    "cashflow_financing": ("netcashprovidedbyusedinfinancingactivities",),
}

DataValue = Union[int, date, str, None]
SQLQuery = str
SQLValues = tuple[DataValue, ...]
SQLInsert = Tuple[SQLQuery, SQLValues]
TableResult = Tuple[SQLQuery, List[SQLInsert]]
ProcessingResult = Dict[str, TableResult]

FINANCIAL_FACT_DDL = """
CREATE TABLE IF NOT EXISTS financial_fact (
    id SERIAL PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES ticker(id) ON DELETE CASCADE,
    fiscal_year INTEGER NOT NULL,
    fiscal_period_end DATE NOT NULL,
    period_type VARCHAR(16) NOT NULL
        CHECK (period_type IN ('annual', 'quarterly')),
    quarter INTEGER CHECK (quarter IS NULL OR quarter BETWEEN 1 AND 4),
    line_code TEXT NOT NULL REFERENCES financial_line(line_code) ON DELETE RESTRICT,
    value BIGINT NOT NULL,
    decimals INTEGER,
    unit TEXT,
    scale INTEGER,
    source_concept TEXT NOT NULL,
    source_standard_concept TEXT,
    filing_accession TEXT,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_financial_fact_grain UNIQUE (
        ticker_id,
        fiscal_year,
        fiscal_period_end,
        period_type,
        line_code
    )
);
"""

FINANCIAL_FACT_INSERT = """
INSERT INTO financial_fact (
    ticker_id, fiscal_year, fiscal_period_end, period_type, quarter,
    line_code, value, decimals, unit, scale,
    source_concept, source_standard_concept, filing_accession
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s
)
ON CONFLICT (ticker_id, fiscal_year, fiscal_period_end, period_type, line_code)
DO UPDATE SET
    value = EXCLUDED.value,
    decimals = EXCLUDED.decimals,
    unit = EXCLUDED.unit,
    scale = EXCLUDED.scale,
    source_concept = EXCLUDED.source_concept,
    source_standard_concept = EXCLUDED.source_standard_concept,
    filing_accession = EXCLUDED.filing_accession,
    extracted_at = CURRENT_TIMESTAMP
"""


@dataclass
class _CandidateFact:
    ticker_id: int
    fiscal_year: int
    fiscal_period_end: date
    period_type: str
    quarter: Optional[int]
    line_code: str
    value: int
    decimals: Optional[int]
    unit: Optional[str]
    scale: Optional[int]
    source_concept: str
    source_standard_concept: Optional[str]
    filing_accession: Optional[str]
    anchored: bool = False


class FinancialDataParser(BaseModel):
    income_statement: DataFrame = Field(...)
    balance_sheet: DataFrame = Field(...)
    cashflow: DataFrame = Field(...)
    ticker_id: int = Field(...)
    is_annual: bool = Field(...)
    filing_accession: Optional[str] = Field(default=None)

    class Config:
        arbitrary_types_allowed = True

    @staticmethod
    def _find_column(df: DataFrame, *names: str) -> Optional[str]:
        """Match column ignoring case (edgartools / pandas may vary casing)."""
        lower = {str(c).lower(): c for c in df.columns}
        for n in names:
            hit = lower.get(n.lower())
            if hit is not None:
                return str(hit)
        return None

    def _is_metadata_column(self, col: Any) -> bool:
        col_name = str(col).strip().lower()
        metadata_cols = {
            "concept",
            "label",
            "standard_concept",
            "preferred_sign",
            "decimals",
            "units",
            "unit",
            "scale",
            "depth",
            "is_abstract",
            "index",
        }
        return col_name in metadata_cols

    def _get_period_columns(self, df: DataFrame) -> List[Any]:
        period_columns: List[Any] = []
        for col in df.columns:
            if pd.isna(col) or self._is_metadata_column(col):
                continue
            period_candidate = pd.to_datetime(col, errors="coerce")
            if pd.isna(period_candidate):
                logger.warning("Skipping invalid period date column: %s", col)
                continue
            period_columns.append(col)
        return period_columns

    def _determine_fiscal_period_end(self, period_date: pd.Timestamp) -> date:
        if self.is_annual:
            return date(period_date.year, 12, 31)
        quarter = (period_date.month - 1) // 3 + 1
        quarter_end_month = quarter * 3
        next_month = quarter_end_month + 1 if quarter_end_month < 12 else 1
        next_year = period_date.year if quarter_end_month < 12 else period_date.year + 1
        end_date = pd.Timestamp(f"{next_year}-{next_month}-01") - pd.Timedelta(days=1)
        return end_date.date()

    @staticmethod
    def _row_is_abstract(row: pd.Series, abstract_col: Optional[str]) -> bool:
        if not abstract_col or abstract_col not in row.index:
            return False
        v = row.get(abstract_col)
        if pd.isna(v):
            return False
        return bool(v)

    def _row_has_numeric_for_periods(
        self, row: pd.Series, periods: List[Any]
    ) -> bool:
        for p in periods:
            if self._extract_numeric(row.get(p)) is not None:
                return True
        return False

    @staticmethod
    def _safe_int_optional(val: Any) -> Optional[int]:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            x = int(float(val))
            return x
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_str_optional(val: Any) -> Optional[str]:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        s = str(val).strip()
        return s or None

    def _extract_numeric(self, raw: Any) -> Optional[int]:
        num = pd.to_numeric(raw, errors="coerce")
        if pd.isna(num):
            return None
        try:
            return int(num)
        except (TypeError, ValueError, OverflowError):
            return None

    def _iter_statement_rows(
        self, df: DataFrame, periods: List[Any]
    ) -> List[Tuple[str, Optional[str], pd.Series]]:
        """Return list of (concept, standard_concept, row_series)."""
        rows_out: List[Tuple[str, Optional[str], pd.Series]] = []
        concept_col = self._find_column(df, "concept")
        std_col = self._find_column(df, "standard_concept", "standardconcept")
        abstract_col = self._find_column(df, "is_abstract", "isabstract")

        if concept_col and concept_col in df.columns:
            for _, row in df.iterrows():
                if self._row_is_abstract(row, abstract_col) and not self._row_has_numeric_for_periods(
                    row, periods
                ):
                    continue
                c = row.get(concept_col)
                if c is None or (isinstance(c, float) and pd.isna(c)):
                    continue
                concept_s = str(c).strip()
                if not concept_s:
                    continue
                std: Optional[str] = None
                if std_col and std_col in row.index:
                    sc = row.get(std_col)
                    if sc is not None and not (isinstance(sc, float) and pd.isna(sc)):
                        std_s = str(sc).strip()
                        std = std_s or None
                rows_out.append((concept_s, std, row))
            return rows_out

        for idx in df.index:
            if pd.isna(idx):
                continue
            rows_out.append((str(idx).strip(), None, df.loc[idx]))
        return rows_out

    def _extract_candidates_for_statement(
        self, statement: str, df: DataFrame
    ) -> List[_CandidateFact]:
        periods = self._get_period_columns(df)
        candidates: List[_CandidateFact] = []
        unmapped: set[tuple[str, Optional[str]]] = set()
        dec_col = self._find_column(df, "decimals")
        unit_col = self._find_column(df, "units", "unit")
        scale_col = self._find_column(df, "scale")

        for period in periods:
            period_date = pd.to_datetime(period, errors="coerce")
            if pd.isna(period_date):
                continue
            fiscal_period_end = self._determine_fiscal_period_end(period_date)
            quarter = None if self.is_annual else (period_date.month - 1) // 3 + 1
            fiscal_year = int(period_date.year)
            period_type = "annual" if self.is_annual else "quarterly"

            for concept_s, std_concept, row in self._iter_statement_rows(df, periods):
                explicit_std = self._safe_str_optional(std_concept)
                std_for_map = explicit_std or infer_standard_concept(concept_s)
                line_code = map_to_line_code(
                    concept=concept_s,
                    standard_concept=std_for_map,
                    statement=statement,
                )
                if not line_code:
                    unmapped.add((concept_s, std_concept))
                    continue

                value = self._extract_numeric(row.get(period))
                if value is None:
                    continue

                decimals = self._safe_int_optional(
                    row.get(dec_col) if dec_col else row.get("decimals")
                )
                raw_unit = None
                if unit_col:
                    raw_unit = row.get(unit_col)
                if raw_unit is None:
                    raw_unit = row.get("units") or row.get("unit")
                unit = self._safe_str_optional(raw_unit)
                scale = self._safe_int_optional(
                    row.get(scale_col) if scale_col else row.get("scale")
                )

                anchored = bool(std_for_map and str(std_for_map).strip())

                candidates.append(
                    _CandidateFact(
                        ticker_id=self.ticker_id,
                        fiscal_year=fiscal_year,
                        fiscal_period_end=fiscal_period_end,
                        period_type=period_type,
                        quarter=quarter,
                        line_code=line_code,
                        value=value,
                        decimals=decimals,
                        unit=unit,
                        scale=scale,
                        source_concept=concept_s,
                        source_standard_concept=std_for_map,
                        filing_accession=self.filing_accession,
                        anchored=anchored,
                    )
                )

        if unmapped:
            sample = sorted(unmapped)[:25]
            logger.info(
                "Unmapped %s concepts for statement=%s (showing up to 25): %s",
                len(unmapped),
                statement,
                sample,
            )

        return candidates

    @staticmethod
    def _merge_pick_candidate(group: List[_CandidateFact], line_code: str) -> _CandidateFact:
        """Prefer canonical totals for a line_code, then anchored rows, then stable order."""
        prefs = _MERGE_PREFERRED_LOCAL_NAMES.get(line_code)
        if prefs:
            for pref in prefs:
                for g in group:
                    if pref in iter_lookup_keys(normalize_xbrl_name(g.source_concept)):
                        return g
        anchored = [g for g in group if g.anchored]
        pool = anchored if anchored else group
        pool_sorted = sorted(
            pool,
            key=lambda g: (0 if g.anchored else 1, normalize_xbrl_name(g.source_concept)),
        )
        return pool_sorted[0]

    @classmethod
    def _merge_candidates(cls, candidates: List[_CandidateFact]) -> List[_CandidateFact]:
        """Merge many-to-one on grain; prefer statement totals, then anchored mapping."""
        buckets: Dict[Tuple[Any, ...], List[_CandidateFact]] = defaultdict(list)
        for c in candidates:
            key = (
                c.ticker_id,
                c.fiscal_year,
                c.fiscal_period_end,
                c.period_type,
                c.line_code,
            )
            buckets[key].append(c)

        merged: List[_CandidateFact] = []
        for key, group in buckets.items():
            if len(group) == 1:
                merged.append(group[0])
                continue
            line_code = key[4]
            chosen = cls._merge_pick_candidate(group, line_code)
            vals = {g.value for g in group}
            if len(vals) > 1:
                logger.warning(
                    "Merged duplicate financial_fact grain=%s values=%s chose anchored=%s concept=%s",
                    key,
                    vals,
                    chosen.anchored,
                    chosen.source_concept,
                )
            merged.append(chosen)

        return merged

    def extract_financial_facts(self) -> List[Dict[str, Any]]:
        """Return merged fact rows ready for INSERT."""
        all_c: List[_CandidateFact] = []
        all_c.extend(self._extract_candidates_for_statement("balance", self.balance_sheet))
        all_c.extend(self._extract_candidates_for_statement("income", self.income_statement))
        all_c.extend(self._extract_candidates_for_statement("cashflow", self.cashflow))

        merged = self._merge_candidates(all_c)
        return [
            {
                "ticker_id": m.ticker_id,
                "fiscal_year": m.fiscal_year,
                "fiscal_period_end": m.fiscal_period_end,
                "period_type": m.period_type,
                "quarter": m.quarter,
                "line_code": m.line_code,
                "value": m.value,
                "decimals": m.decimals,
                "unit": m.unit,
                "scale": m.scale,
                "source_concept": m.source_concept,
                "source_standard_concept": m.source_standard_concept,
                "filing_accession": m.filing_accession,
            }
            for m in merged
        ]

    def build_processing_result(self) -> ProcessingResult:
        """Single-table upserts for financial_fact."""
        rows = self.extract_financial_facts()
        inserts: List[SQLInsert] = []
        for r in rows:
            inserts.append(
                (
                    FINANCIAL_FACT_INSERT,
                    (
                        r["ticker_id"],
                        r["fiscal_year"],
                        r["fiscal_period_end"],
                        r["period_type"],
                        r["quarter"],
                        r["line_code"],
                        r["value"],
                        r["decimals"],
                        r["unit"],
                        r["scale"],
                        r["source_concept"],
                        r["source_standard_concept"],
                        r["filing_accession"],
                    ),
                )
            )
        return {"FINANCIAL_FACT": (FINANCIAL_FACT_DDL, inserts)}
