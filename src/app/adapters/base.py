"""
Data Ingestion - Base interfaces and data models.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Iterator
from enum import Enum


class SourceType(Enum):
    FILE = "file"
    STRUCTURED = "structured"
    STREAM = "stream"
    GRAPH = "graph"
    API = "api"


@dataclass
class IngestionResult:
    """Normalized result returned by all adapters."""
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)
    source_type: SourceType = SourceType.FILE
    raw_records: List[Dict] = field(default_factory=list)


class SourceAdapter(ABC):
    """Base interface for all data source adapters."""

    @abstractmethod
    def can_handle(self, source_ref: str) -> bool:
        """Return True if this adapter can process the given source reference."""

    @abstractmethod
    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        """Read data from source and return a normalized IngestionResult."""

    def ingest_stream(self, source_ref: str, **kwargs) -> Iterator[IngestionResult]:
        """For streaming sources: yield IngestionResults continuously."""
        raise NotImplementedError("This adapter does not support streaming")


class StreamSourceAdapter(SourceAdapter):
    """Specialized interface for stream data sources."""

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> None:
        """Connect to the stream source."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the stream source."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if connected."""
