"""
Adapters package — re-exports for convenient importing.
"""
from .base import SourceAdapter, StreamSourceAdapter, IngestionResult, SourceType

from .file_adapters import (
    PdfAdapter,
    TextAdapter,
    DocxAdapter,
    ExcelAdapter,
    HtmlAdapter,
)
from .structured_adapters import (
    CsvAdapter,
    JsonAdapter,
    ParquetAdapter,
    YamlAdapter,
)
from .stream_adapters import (
    WebhookAdapter,
    KafkaStreamAdapter,
    RestPollingAdapter,
)
from .db_adapters import (
    Neo4jImportAdapter,
    PostgresAdapter,
)

__all__ = [
    # Base
    "SourceAdapter", "StreamSourceAdapter", "IngestionResult", "SourceType",
    # File
    "PdfAdapter", "TextAdapter", "DocxAdapter", "ExcelAdapter", "HtmlAdapter",
    # Structured
    "CsvAdapter", "JsonAdapter", "ParquetAdapter", "YamlAdapter",
    # Stream
    "WebhookAdapter", "KafkaStreamAdapter", "RestPollingAdapter",
    # DB / Graph
    "Neo4jImportAdapter", "PostgresAdapter",
]
