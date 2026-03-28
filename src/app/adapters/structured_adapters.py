"""
Structured data adapters: CSV, JSON/JSONL, Parquet, YAML.
"""
import os
import logging
from typing import List, Dict, Any

from .base import SourceAdapter, IngestionResult, SourceType

logger = logging.getLogger(__name__)


class CsvAdapter(SourceAdapter):
    """Convert CSV rows to natural-language text for NER extraction."""

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.lower().endswith('.csv')

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        import pandas as pd

        df = pd.read_csv(source_ref)
        row_limit = kwargs.get('row_limit', 500)

        schema_desc = f"Dataset with {len(df)} records and columns: {', '.join(df.columns)}"

        # Numeric column summary
        summary_parts = [schema_desc]
        for col in df.select_dtypes(include='number').columns:
            summary_parts.append(
                f"{col}: min={df[col].min()}, max={df[col].max()}, "
                f"mean={df[col].mean():.2f}, median={df[col].median():.2f}"
            )

        # Row → natural language
        sentences: List[str] = []
        for _, row in df.head(row_limit).iterrows():
            parts = []
            for col, val in row.items():
                if pd.notna(val):
                    # Smart conversion: skip pure IDs, summarize numbers contextually
                    parts.append(f"{col} is {val}")
            sentences.append(". ".join(parts) + ".")

        full_text = "\n".join(summary_parts) + "\n\n" + "\n".join(sentences)

        return IngestionResult(
            text=full_text,
            metadata={
                "source": source_ref,
                "format": "csv",
                "row_count": len(df),
                "columns": list(df.columns),
            },
            source_type=SourceType.STRUCTURED,
            raw_records=df.head(row_limit).to_dict('records'),
        )


class JsonAdapter(SourceAdapter):
    """Convert JSON/JSONL records to natural-language text."""

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.lower().endswith(('.json', '.jsonl'))

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        import json

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


class ParquetAdapter(SourceAdapter):
    """Read Parquet files via pandas and reuse CsvAdapter logic."""

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.lower().endswith('.parquet')

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        import pandas as pd
        import tempfile

        df = pd.read_parquet(source_ref)

        # Write to temp CSV and delegate to CsvAdapter
        tmp = tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w')
        df.to_csv(tmp.name, index=False)
        tmp.close()

        csv_adapter = CsvAdapter()
        result = csv_adapter.ingest(tmp.name, **kwargs)
        os.unlink(tmp.name)

        # Override metadata source
        result.metadata["source"] = source_ref
        result.metadata["format"] = "parquet"
        return result


class YamlAdapter(SourceAdapter):
    """Convert YAML files to natural-language text."""

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.lower().endswith(('.yaml', '.yml'))

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        import yaml

        with open(source_ref, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if isinstance(data, list):
            json_adapter = JsonAdapter()
            sentences = [json_adapter._record_to_text(r) for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            json_adapter = JsonAdapter()
            sentences = [json_adapter._record_to_text(data)]
        else:
            sentences = [str(data)]

        return IngestionResult(
            text="\n".join(sentences),
            metadata={"source": source_ref, "format": "yaml"},
            source_type=SourceType.STRUCTURED,
        )
