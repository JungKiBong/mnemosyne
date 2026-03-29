"""
DataIngestionService — Unified entry point for all data sources.

Routes any source_ref to the correct adapter, normalizes the result,
and sends it through the text/structured pipeline into GraphStorage.

## 2-Phase Hybrid Pipeline (Understand-Anything inspired)
1. StructuralExtractor: deterministic structure extraction (no LLM)
2. SemanticEnricher:    LLM-based semantic annotation (typed nodes/edges)
3. ContentFingerprint:  incremental delta-only updates

The classic NER pipeline is preserved as a fallback / parallel path.
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
    - 2-Phase hybrid pipeline: structural extraction → semantic enrichment
    - Fingerprint-based incremental updates (delta-only reprocessing)
    """

    def __init__(self, storage: GraphStorage, chunk_size: int = 500, chunk_overlap: int = 50):
        self.storage = storage
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.adapters: List[SourceAdapter] = []
        self._stream_threads: Dict[str, threading.Thread] = {}
        self._register_default_adapters()

        # Lazy-initialized Phase pipeline components
        self._structural_extractor = None
        self._semantic_enricher = None
        self._fingerprint_manager = None

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

    @property
    def structural_extractor(self):
        """Lazy-init Phase 1 structural extractor."""
        if self._structural_extractor is None:
            from app.services.structural_extractor import StructuralExtractor
            self._structural_extractor = StructuralExtractor()
        return self._structural_extractor

    @property
    def semantic_enricher(self):
        """Lazy-init Phase 2 semantic enricher."""
        if self._semantic_enricher is None:
            from app.services.semantic_enricher import SemanticEnricher
            self._semantic_enricher = SemanticEnricher()
        return self._semantic_enricher

    @property
    def fingerprint_manager(self):
        """Lazy-init fingerprint manager for incremental updates."""
        if self._fingerprint_manager is None:
            from app.utils.fingerprint import ContentFingerprint
            self._fingerprint_manager = ContentFingerprint()
        return self._fingerprint_manager

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
    # One-shot ingestion (classic NER pipeline)
    # ==========================================

    def ingest(self, graph_id: str, source_ref: str, **kwargs) -> Dict[str, Any]:
        """
        Ingest data from any source into the graph (classic NER pipeline).
        
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

    # ==========================================
    # 2-Phase Hybrid Pipeline (UA-inspired)
    # ==========================================

    def ingest_with_knowledge_graph(
        self,
        graph_id: str,
        source_ref: str,
        incremental: bool = True,
        enrich: bool = True,
        also_run_ner: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Ingest data using the 2-Phase hybrid pipeline.

        Phase 1: StructuralExtractor — deterministic structure extraction (no LLM)
        Phase 2: SemanticEnricher — LLM-based typed nodes/edges with summaries
        + Fingerprint-based incremental updates

        Args:
            graph_id:     Target graph ID
            source_ref:   Data source reference
            incremental:  If True, only process changed sections (via fingerprint)
            enrich:       If True, run Phase 2 LLM enrichment
            also_run_ner: If True, also run classic NER pipeline in parallel
            **kwargs:     Adapter-specific options

        Returns:
            Summary dict with hybrid pipeline statistics
        """
        adapter = self.find_adapter(source_ref)
        logger.info(
            "Hybrid ingestion [%s] via %s (incremental=%s, enrich=%s)",
            source_ref, type(adapter).__name__, incremental, enrich
        )

        result: IngestionResult = adapter.ingest(source_ref, **kwargs)

        summary = {
            "source": source_ref,
            "adapter": type(adapter).__name__,
            "source_type": result.source_type.value,
            "text_length": len(result.text) if result.text else 0,
            "pipeline": "hybrid_2phase",
            "phase1_sections": 0,
            "phase1_chunks": 0,
            "phase2_nodes": 0,
            "phase2_edges": 0,
            "fingerprint_status": "n/a",
            "ner_chunks": 0,
        }

        if not result.text and not result.entities:
            logger.warning("No text or entities extracted from %s", source_ref)
            return summary

        # ── Phase 1: Structural Extraction ──
        skeleton = self.structural_extractor.extract(
            source_ref=source_ref,
            text=result.text,
        )
        summary["phase1_sections"] = len(skeleton.sections)
        summary["phase1_chunks"] = len(skeleton.structural_chunks)

        # ── Fingerprint / Incremental Check ──
        if incremental and result.text:
            section_fps = {}
            for sec in skeleton.sections:
                section_fps[sec.name] = self.fingerprint_manager.hash_text(
                    sec.content_preview
                )

            diff = self.fingerprint_manager.compare(
                source_ref=source_ref,
                new_global_fp=skeleton.fingerprint,
                new_section_fps=section_fps,
            )
            summary["fingerprint_status"] = diff.summary()

            if diff.is_unchanged:
                logger.info("Source unchanged, skipping: %s", source_ref)
                summary["pipeline"] = "skipped_unchanged"
                return summary

            # Save updated fingerprint
            self.fingerprint_manager.save(
                source_ref=source_ref,
                global_fp=skeleton.fingerprint,
                section_fps=section_fps,
                metadata=skeleton.metadata,
            )

        # ── Phase 2: Semantic Enrichment (LLM) ──
        if enrich:
            try:
                knowledge_graph = self.semantic_enricher.enrich(
                    skeleton=skeleton,
                    graph_id=graph_id,
                )
                summary["phase2_nodes"] = knowledge_graph.node_count
                summary["phase2_edges"] = knowledge_graph.edge_count

                # Inject enriched nodes/edges into Neo4j
                self._inject_knowledge_graph(graph_id, knowledge_graph)

            except Exception as e:
                logger.error(
                    "Phase 2 enrichment failed for %s: %s — continuing with NER only",
                    source_ref, e
                )

        # ── Classic NER (parallel path) ──
        if also_run_ner and result.text:
            # Use structure-aware chunks from Phase 1 instead of naive splitting
            chunks = skeleton.structural_chunks or split_text_into_chunks(
                result.text, self.chunk_size, self.chunk_overlap,
            )
            episode_ids = self.storage.add_text_batch(graph_id, chunks)
            summary["ner_chunks"] = len(episode_ids)

        # Inject pre-extracted entities if any
        if result.entities or result.relations:
            self._inject_pre_extracted(graph_id, result)

        logger.info("Hybrid ingestion complete: %s", summary)
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

    def _inject_knowledge_graph(self, graph_id: str, knowledge_graph) -> None:
        """
        Inject typed knowledge graph (from SemanticEnricher) into Neo4j.

        Unlike _inject_pre_extracted which converts entities to plain text,
        this stores structured nodes with:
        - Extended labels (NodeType-based)
        - Semantic properties (summary, tags, complexity, fingerprint)
        - Typed, weighted edges with descriptions

        Uses MERGE to avoid duplicating nodes on repeated ingestion.
        """
        from neo4j import GraphDatabase
        from ..config import Config

        driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
        )

        try:
            with driver.session() as session:
                # Inject nodes
                for node in knowledge_graph.nodes:
                    props = node.to_neo4j_props()
                    node_label = node.type.value.capitalize()

                    session.run(
                        f"""
                        MERGE (n:Entity {{uuid: $uuid}})
                        SET n:{node_label},
                            n.name = $name,
                            n.node_type = $node_type,
                            n.summary = $summary,
                            n.tags = $tags,
                            n.complexity = $complexity,
                            n.source_path = $source_path,
                            n.fingerprint = $fingerprint,
                            n.metadata = $metadata,
                            n.graph_id = $graph_id
                        """,
                        uuid=props["uuid"],
                        name=props["name"],
                        node_type=props["node_type"],
                        summary=props["summary"],
                        tags=props["tags"],
                        complexity=props["complexity"],
                        source_path=props["source_path"],
                        fingerprint=props["fingerprint"],
                        metadata=props["metadata"],
                        graph_id=graph_id,
                    )

                # Inject edges
                for edge in knowledge_graph.edges:
                    props = edge.to_neo4j_props()

                    session.run(
                        """
                        MATCH (src:Entity {uuid: $source_id})
                        MATCH (tgt:Entity {uuid: $target_id})
                        MERGE (src)-[r:RELATES_TO {edge_type: $edge_type}]->(tgt)
                        SET r.weight = $weight,
                            r.direction = $direction,
                            r.description = $description,
                            r.metadata = $metadata,
                            r.graph_id = $graph_id
                        """,
                        source_id=edge.source_id,
                        target_id=edge.target_id,
                        edge_type=props["edge_type"],
                        weight=props["weight"],
                        direction=props["direction"],
                        description=props["description"],
                        metadata=props["metadata"],
                        graph_id=graph_id,
                    )

                logger.info(
                    "Injected knowledge graph: %d nodes, %d edges into graph_id=%s",
                    knowledge_graph.node_count, knowledge_graph.edge_count, graph_id
                )
        finally:
            driver.close()

