"""
Structured data adapters: CSV, JSON/JSONL, Parquet, YAML.

Design principle (Air-gap):
  - No pandas dependency for the core ingestion path.
  - CsvAdapter, JsonAdapter, YamlAdapter use stdlib only.
  - ParquetAdapter requires 'pyarrow' (optional, fallback to error).
  - If pandas is installed, CsvAdapter uses it for richer numeric stats.
"""
import csv
import io
import json
import logging
import os
import statistics
from typing import Any, Dict, List, Optional

from .base import IngestionResult, SourceAdapter, SourceType

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _try_float(val: str) -> Optional[float]:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _numeric_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {}
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(sum(values) / len(values), 4),
        "median": round(statistics.median(values), 4),
    }


def _rows_to_text(rows: List[Dict], limit: int) -> List[str]:
    """Convert dicts to natural-language sentences."""
    sentences = []
    for row in rows[:limit]:
        parts = [f"{k} is {v}" for k, v in row.items() if v not in (None, '', 'nan')]
        if parts:
            sentences.append(". ".join(parts) + ".")
    return sentences


# ──────────────────────────────────────────────
# CSV Adapter (stdlib csv, no pandas required)
# ──────────────────────────────────────────────

class CsvAdapter(SourceAdapter):
    """Convert CSV rows to natural-language text for NER extraction.

    Uses stdlib csv module only.
    Provides numeric column statistics without pandas.
    """

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.lower().endswith('.csv')

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        row_limit: int = kwargs.get('row_limit', 500)

        with open(source_ref, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            rows: List[Dict[str, Any]] = []
            for row in reader:
                rows.append(dict(row))

        if not rows:
            return IngestionResult(
                text="Empty CSV file.",
                metadata={"source": source_ref, "format": "csv", "row_count": 0},
                source_type=SourceType.STRUCTURED,
                raw_records=[],
            )

        columns = list(rows[0].keys()) if rows else []
        total_rows = len(rows)

        # Numeric stats (stdlib, no pandas)
        summary_parts = [
            f"Dataset with {total_rows} records and columns: {', '.join(columns)}"
        ]
        for col in columns:
            numeric_vals = [
                v for v in (_try_float(r.get(col, '')) for r in rows) if v is not None
            ]
            if len(numeric_vals) >= 2:
                stats = _numeric_stats(numeric_vals)
                summary_parts.append(
                    f"{col}: min={stats['min']}, max={stats['max']}, "
                    f"mean={stats['mean']}, median={stats['median']}"
                )

        sentences = _rows_to_text(rows, row_limit)
        full_text = "\n".join(summary_parts) + "\n\n" + "\n".join(sentences)

        return IngestionResult(
            text=full_text,
            metadata={
                "source": source_ref,
                "format": "csv",
                "row_count": total_rows,
                "columns": columns,
            },
            source_type=SourceType.STRUCTURED,
            raw_records=rows[:row_limit],
        )


# ──────────────────────────────────────────────
# JSON / JSONL Adapter (stdlib json)
# ──────────────────────────────────────────────

class JsonAdapter(SourceAdapter):
    """Convert JSON/JSONL records to natural-language text."""

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.lower().endswith(('.json', '.jsonl'))

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        with open(source_ref, 'r', encoding='utf-8') as f:
            if source_ref.endswith('.jsonl'):
                records = [json.loads(line) for line in f if line.strip()]
            else:
                data = json.load(f)
                records = data if isinstance(data, list) else [data]

        sentences = [self._record_to_text(r) for r in records]

        return IngestionResult(
            text="\n".join(sentences),
            metadata={
                "source": source_ref,
                "format": "json",
                "record_count": len(records),
            },
            source_type=SourceType.STRUCTURED,
            raw_records=records,
        )

    def _record_to_text(self, record: Dict, prefix: str = "") -> str:
        """Recursively convert a JSON object to a natural-language sentence."""
        parts: List[str] = []
        for key, value in record.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                parts.append(self._record_to_text(value, full_key))
            elif isinstance(value, list):
                items = ", ".join(str(v) for v in value)
                parts.append(f"{full_key} includes {items}")
            else:
                parts.append(f"{full_key} is {value}")
        return ". ".join(parts) + "."


# ──────────────────────────────────────────────
# Parquet Adapter (requires pyarrow — optional)
# ──────────────────────────────────────────────

class ParquetAdapter(SourceAdapter):
    """Read Parquet files via pyarrow and reuse CsvAdapter logic.

    Requires: pip install pyarrow
    """

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.lower().endswith('.parquet')

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        try:
            import pyarrow.parquet as pq  # type: ignore
        except ImportError:
            raise ImportError(
                "ParquetAdapter requires 'pyarrow'. "
                "Install it with: pip install pyarrow"
            )

        table = pq.read_table(source_ref)
        row_limit = kwargs.get('row_limit', 500)

        # Convert to list of dicts via pyarrow (no pandas)
        rows: List[Dict[str, Any]] = table.slice(0, row_limit).to_pydict()
        # to_pydict → {col: [v,...]} — transpose to list of row dicts
        columns = list(rows.keys())
        num_rows = len(next(iter(rows.values()), []))
        row_dicts = [{col: rows[col][i] for col in columns} for i in range(num_rows)]

        csv_adapter = CsvAdapter()
        # Delegate text generation
        sentences = _rows_to_text(row_dicts, row_limit)
        summary = f"Parquet dataset with {num_rows} records and columns: {', '.join(columns)}"
        full_text = summary + "\n\n" + "\n".join(sentences)

        return IngestionResult(
            text=full_text,
            metadata={
                "source": source_ref,
                "format": "parquet",
                "row_count": num_rows,
                "columns": columns,
            },
            source_type=SourceType.STRUCTURED,
            raw_records=row_dicts,
        )


# ──────────────────────────────────────────────
# YAML Adapter (requires pyyaml — optional)
# ──────────────────────────────────────────────

class YamlAdapter(SourceAdapter):
    """Convert YAML files to natural-language text.

    Requires: pip install pyyaml
    """

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.lower().endswith(('.yaml', '.yml'))

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        try:
            import yaml  # type: ignore
        except ImportError:
            raise ImportError("YamlAdapter requires 'pyyaml'. Install: pip install pyyaml")

        with open(source_ref, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        json_adapter = JsonAdapter()
        if isinstance(data, list):
            sentences = [json_adapter._record_to_text(r) for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            sentences = [json_adapter._record_to_text(data)]
        else:
            sentences = [str(data)]

        return IngestionResult(
            text="\n".join(sentences),
            metadata={"source": source_ref, "format": "yaml"},
            source_type=SourceType.STRUCTURED,
        )
