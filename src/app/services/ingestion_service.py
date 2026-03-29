"""
DataIngestionService — Unified entry point for all data sources.

Routes any source_ref to the correct adapter, normalizes the result,
and sends it through the text/structured pipeline into GraphStorage.
"""
import logging
import threading
from typing import Dict, Any, List, Optional

from app.storage.graph_storage import GraphStorage
from app.adapters.base import SourceAdapter, StreamSourceAdapter, IngestionResult
from app.adapters import (
    PdfAdapter, TextAdapter, DocxAdapter, ExcelAdapter, HtmlAdapter,
    CsvAdapter, JsonAdapter, ParquetAdapter, YamlAdapter,
    WebhookAdapter, KafkaStreamAdapter, RestPollingAdapter,
    Neo4jImportAdapter, PostgresAdapter,
)

logger = logging.getLogger(__name__)


def split_text_into_chunks(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks for NER processing."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks


class DataIngestionService:
    """
    Orchestrates data ingestion from any source into GraphStorage.
    
    Responsibilities:
    - Adapter auto-discovery via can_handle()
    - One-shot ingestion for files, structured data, and DB connectors
    - Stream ingestion for Webhook, Kafka, and REST polling
    - Pre-extracted entity/relation injection (graph DB imports)
    """

    def __init__(self, storage: GraphStorage, chunk_size: int = 500, chunk_overlap: int = 50):
        self.storage = storage
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.adapters: List[SourceAdapter] = []
        self._stream_threads: Dict[str, threading.Thread] = {}
        self._register_default_adapters()

    def _register_default_adapters(self):
        """Register built-in adapters in priority order."""
        self.adapters.extend([
            # File adapters
            PdfAdapter(),
            TextAdapter(),
            DocxAdapter(),
            ExcelAdapter(),
            HtmlAdapter(),
            # Structured data adapters
            CsvAdapter(),
            JsonAdapter(),
            ParquetAdapter(),
            YamlAdapter(),
            # DB / Graph adapters
            Neo4jImportAdapter(),
            PostgresAdapter(),
            # Stream adapters
            WebhookAdapter(),
            # REST polling (lowest priority — matches any URL)
            RestPollingAdapter(),
        ])

    def register_adapter(self, adapter: SourceAdapter):
        """Register a custom adapter with highest priority."""
        self.adapters.insert(0, adapter)

    def find_adapter(self, source_ref: str) -> SourceAdapter:
        """Find the first adapter that can handle the given source."""
        for adapter in self.adapters:
            if adapter.can_handle(source_ref):
                return adapter
        raise ValueError(f"No adapter found for source: {source_ref}")

    # ==========================================
    # One-shot ingestion
    # ==========================================

    def ingest(self, graph_id: str, source_ref: str, **kwargs) -> Dict[str, Any]:
        """
        Ingest data from any source into the graph.
        
        Args:
            graph_id:    Target graph ID in storage
            source_ref:  Data source reference:
                         - File path:  "/path/to/file.csv"
                         - DB URI:     "postgresql://host/db"
                         - Neo4j URI:  "bolt://host:7687"
                         - URL:        "https://api.example.com/data"
            **kwargs:    Adapter-specific options (row_limit, query, sheet_name, etc.)
        
        Returns:
            Summary dict with ingestion statistics.
        """
        adapter = self.find_adapter(source_ref)
        logger.info("Ingesting [%s] via %s", source_ref, type(adapter).__name__)

        result: IngestionResult = adapter.ingest(source_ref, **kwargs)

        episode_ids = []

        # 1. If pre-extracted entities/relations exist → inject directly into graph
        if result.entities or result.relations:
            self._inject_pre_extracted(graph_id, result)

        # 2. If text exists → chunk → NER → graph storage
        if result.text:
            chunks = split_text_into_chunks(
                result.text,
                self.chunk_size,
                self.chunk_overlap,
            )
            episode_ids = self.storage.add_text_batch(graph_id, chunks)

        summary = {
            "source": source_ref,
            "adapter": type(adapter).__name__,
            "source_type": result.source_type.value,
            "text_length": len(result.text) if result.text else 0,
            "chunks": len(episode_ids),
            "entities_injected": len(result.entities),
            "relations_injected": len(result.relations),
            "metadata": result.metadata,
        }
        logger.info("Ingestion complete: %s", summary)
        return summary

    def ingest_batch(self, graph_id: str, source_refs: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Ingest multiple sources sequentially."""
        results = []
        for ref in source_refs:
            try:
                result = self.ingest(graph_id, ref, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error("Failed to ingest %s: %s", ref, e)
                results.append({"source": ref, "error": str(e)})
        return results

    # ==========================================
    # Stream ingestion
    # ==========================================

    def start_stream(self, graph_id: str, source_ref: str, **kwargs) -> str:
        """
        Start a background thread to continuously ingest from a stream source.
        
        Returns:
            stream_id for tracking/stopping.
        """
        if source_ref in self._stream_threads:
            return f"Stream already running: {source_ref}"

        adapter = self.find_adapter(source_ref)

        # If it's a StreamSourceAdapter, ensure it's connected
        if isinstance(adapter, StreamSourceAdapter):
            config = kwargs.get('config', {})
            adapter.connect(config)

        def stream_worker():
            try:
                for result in adapter.ingest_stream(source_ref, **kwargs):
                    if result.text:
                        self.storage.add_text(graph_id, result.text)
                    if result.entities or result.relations:
                        self._inject_pre_extracted(graph_id, result)
            except Exception as e:
                logger.error("Stream worker error for %s: %s", source_ref, e)

        thread = threading.Thread(target=stream_worker, daemon=True, name=f"stream-{source_ref}")
        thread.start()
        self._stream_threads[source_ref] = thread
        logger.info("Stream started: %s", source_ref)
        return source_ref

    def stop_stream(self, source_ref: str):
        """Stop a running stream."""
        if source_ref in self._stream_threads:
            adapter = self.find_adapter(source_ref)
            if isinstance(adapter, StreamSourceAdapter):
                adapter.disconnect()
            # Daemon thread will exit when disconnected
            del self._stream_threads[source_ref]
            logger.info("Stream stopped: %s", source_ref)

    def active_streams(self) -> List[str]:
        """Return list of currently active stream source_refs."""
        return [ref for ref, t in self._stream_threads.items() if t.is_alive()]

    # ==========================================
    # Private helpers
    # ==========================================

    def _inject_pre_extracted(self, graph_id: str, result: IngestionResult):
        """
        Inject pre-extracted entities/relations directly into the graph.
        This bypasses NER for structured data sources that already
        provide explicit entity/relation information (e.g., Neo4j imports).
        """
        if result.entities:
            logger.info("Injecting %d pre-extracted entities", len(result.entities))
            # Convert entities to natural-language text for storage
            entity_texts = []
            for entity in result.entities:
                name = entity.get('name', 'Unknown')
                etype = entity.get('type', 'Entity')
                props = entity.get('properties', {})
                prop_str = ", ".join(f"{k}={v}" for k, v in props.items() if k != 'name')
                text = f"{name} is a {etype}"
                if prop_str:
                    text += f" with {prop_str}"
                entity_texts.append(text + ".")
            if entity_texts:
                self.storage.add_text_batch(graph_id, entity_texts)

        if result.relations:
            logger.info("Injecting %d pre-extracted relations", len(result.relations))
            relation_texts = []
            for rel in result.relations:
                src = rel.get('source', 'Unknown')
                tgt = rel.get('target', 'Unknown')
                rtype = rel.get('type', 'RELATES_TO')
                relation_texts.append(f"{src} {rtype} {tgt}.")
            if relation_texts:
                self.storage.add_text_batch(graph_id, relation_texts)
