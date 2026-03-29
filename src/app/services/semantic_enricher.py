"""
Semantic Enricher — Phase 2 of 2-Phase Hybrid Extraction.

Takes a StructuralSkeleton (Phase 1 output) and enriches it with LLM-generated
semantic information: summaries, tags, edge types, and complexity ratings.

Unlike directly feeding raw documents to the LLM, the enricher sends compact
structural metadata that fits well within the context window and eliminates
hallucination risk for structural facts (headings, metadata, relationships
are already deterministically extracted).

Usage:
    enricher = SemanticEnricher()
    graph = enricher.enrich(skeleton)
    # graph.nodes → enriched GraphNode list
    # graph.edges → semantically typed GraphEdge list
"""

import json
import logging
from typing import List, Optional

from ..models.knowledge_types import (
    NodeType, EdgeType, GraphNode, GraphEdge, KnowledgeGraph,
    EDGE_WEIGHTS,
)
from .structural_extractor import StructuralSkeleton
from ..utils.llm_client import LLMClient
from ..utils.context_window_manager import ContextWindowManager

logger = logging.getLogger("mirofish.semantic_enricher")


# LLM prompt for semantic enrichment
ENRICHMENT_PROMPT = """You are a knowledge graph enrichment agent.
Given a structural skeleton of a document (sections, metadata, and text chunks),
produce a JSON object that classifies and connects the knowledge within.

IMPORTANT:
- Return ONLY valid JSON, no markdown, no explanations.
- Use ONLY the edge types listed below.

## Available Node Types
document, section, entity, concept, event, data_source, metric, decision, task, agent

## Available Edge Types (with default weights)
contains (1.0), references (0.8), follows (0.8),
causes (0.9), supports (0.7), contradicts (0.7),
precedes (0.6), concurrent_with (0.6),
related_to (0.5), similar_to (0.6), elaborates (0.7),
created_by (0.8), decided_by (0.7), assigned_to (0.7),
sourced_from (0.6), validates (0.8)

## Input: Structural Skeleton
{skeleton_json}

## Expected Output Format
{{
  "nodes": [
    {{
      "id": "unique_id",
      "type": "one_of_node_types",
      "name": "display name",
      "summary": "1-2 sentence description",
      "tags": ["tag1", "tag2"],
      "complexity": "simple|moderate|complex"
    }}
  ],
  "edges": [
    {{
      "source_id": "source_node_id",
      "target_id": "target_node_id",
      "type": "one_of_edge_types",
      "weight": 0.7,
      "description": "brief relationship description"
    }}
  ],
  "graph_summary": "1-2 sentence summary of the entire knowledge"
}}

Extract at most {max_nodes} nodes and {max_edges} edges.
Focus on the most important entities, concepts, and relationships.
Output ONLY the JSON object."""


class SemanticEnricher:
    """
    Phase 2 of 2-Phase Hybrid Extraction.

    Takes structural skeletons and enriches them with LLM-generated
    semantic annotations: summaries, classifications, edge types.
    """

    # Limits per enrichment request
    MAX_NODES_PER_REQUEST = 30
    MAX_EDGES_PER_REQUEST = 50

    # Token budget for enrichment within context window
    ENRICHMENT_TOKEN_BUDGET = 8000

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client
        self._ctx_manager = ContextWindowManager()

    @property
    def llm(self) -> LLMClient:
        """Lazy-initialize LLM client."""
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    def enrich(
        self,
        skeleton: StructuralSkeleton,
        graph_id: str = "default",
        max_nodes: int = 30,
        max_edges: int = 50,
    ) -> KnowledgeGraph:
        """
        Enrich a structural skeleton with semantic annotations.

        Args:
            skeleton: Phase 1 output to enrich
            graph_id: ID for the resulting knowledge graph
            max_nodes: Maximum nodes to extract
            max_edges: Maximum edges to extract

        Returns:
            KnowledgeGraph with typed nodes and weighted edges
        """
        logger.info(
            "Semantic enrichment: %s (%d sections, %d chunks)",
            skeleton.source_ref,
            len(skeleton.sections),
            len(skeleton.structural_chunks)
        )

        # Build compact skeleton representation for the LLM
        skeleton_json = self._build_compact_skeleton(skeleton)

        # Check token budget
        estimated_tokens = self._ctx_manager.estimate_tokens(skeleton_json)
        if estimated_tokens > self.ENRICHMENT_TOKEN_BUDGET:
            logger.warning(
                "Skeleton too large (%d tokens), truncating to fit %d budget",
                estimated_tokens, self.ENRICHMENT_TOKEN_BUDGET
            )
            skeleton_json = skeleton_json[:self.ENRICHMENT_TOKEN_BUDGET * 2]

        # Call LLM for enrichment
        prompt = ENRICHMENT_PROMPT.format(
            skeleton_json=skeleton_json,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

        try:
            result = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "You are a knowledge graph construction agent. Output ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
        except Exception as e:
            logger.error("LLM enrichment failed: %s — falling back to structural-only graph", e)
            return self._fallback_structural_graph(skeleton, graph_id)

        # Parse LLM output into typed graph objects
        return self._parse_llm_output(result, skeleton, graph_id)

    def enrich_batch(
        self,
        skeletons: List[StructuralSkeleton],
        graph_id: str = "default",
    ) -> KnowledgeGraph:
        """
        Enrich multiple skeletons and merge into a single graph.
        Useful for multi-file or multi-source ingestion.
        """
        merged = KnowledgeGraph(graph_id=graph_id)
        for skeleton in skeletons:
            sub_graph = self.enrich(skeleton, graph_id)
            merged.nodes.extend(sub_graph.nodes)
            merged.edges.extend(sub_graph.edges)

        # Deduplicate nodes by ID
        seen_ids = set()
        unique_nodes = []
        for node in merged.nodes:
            if node.id not in seen_ids:
                seen_ids.add(node.id)
                unique_nodes.append(node)
        merged.nodes = unique_nodes

        logger.info(
            "Batch enrichment: %d sources → %d nodes, %d edges",
            len(skeletons), merged.node_count, merged.edge_count
        )
        return merged

    # ──────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────

    def _build_compact_skeleton(self, skeleton: StructuralSkeleton) -> str:
        """Build a compact JSON representation of the skeleton for LLM consumption."""
        compact = {
            "source": skeleton.source_ref,
            "type": skeleton.source_type,
            "metadata": skeleton.metadata,
            "sections": [
                {"name": s.name, "level": s.level, "preview": s.content_preview[:150]}
                for s in skeleton.sections[:40]
            ],
            "chunks": [c[:300] for c in skeleton.structural_chunks[:20]],
            "structural_relations": skeleton.structural_relations[:30],
        }
        return json.dumps(compact, ensure_ascii=False, indent=None)

    def _parse_llm_output(
        self,
        result: dict,
        skeleton: StructuralSkeleton,
        graph_id: str,
    ) -> KnowledgeGraph:
        """Parse LLM JSON output into typed KnowledgeGraph objects."""
        graph = KnowledgeGraph(graph_id=graph_id)

        # Parse nodes
        for raw_node in result.get("nodes", []):
            try:
                node_type = NodeType(raw_node.get("type", "concept"))
            except ValueError:
                node_type = NodeType.CONCEPT

            node = GraphNode(
                id=raw_node.get("id", GraphNode.make_id(node_type, raw_node.get("name", "unnamed"))),
                type=node_type,
                name=raw_node.get("name", "Unnamed"),
                summary=raw_node.get("summary", ""),
                tags=raw_node.get("tags", []),
                complexity=raw_node.get("complexity", "moderate"),
                source_path=skeleton.source_ref,
                fingerprint=skeleton.fingerprint,
            )
            graph.nodes.append(node)

        # Parse edges
        for raw_edge in result.get("edges", []):
            try:
                edge_type = EdgeType(raw_edge.get("type", "related_to"))
            except ValueError:
                edge_type = EdgeType.RELATED_TO

            edge = GraphEdge(
                source_id=raw_edge.get("source_id", ""),
                target_id=raw_edge.get("target_id", ""),
                type=edge_type,
                weight=raw_edge.get("weight", EDGE_WEIGHTS.get(edge_type, 0.5)),
                description=raw_edge.get("description", ""),
            )
            graph.edges.append(edge)

        # Store graph-level summary
        graph.metadata["summary"] = result.get("graph_summary", "")
        graph.metadata["source_ref"] = skeleton.source_ref
        graph.metadata["fingerprint"] = skeleton.fingerprint

        logger.info(
            "Parsed LLM output: %d nodes, %d edges for %s",
            graph.node_count, graph.edge_count, skeleton.source_ref
        )
        return graph

    def _fallback_structural_graph(
        self,
        skeleton: StructuralSkeleton,
        graph_id: str,
    ) -> KnowledgeGraph:
        """
        Fallback: build a graph from structural data alone (no LLM).
        Used when LLM enrichment fails or is unavailable.
        """
        graph = KnowledgeGraph(graph_id=graph_id)

        # Create a document root node
        doc_id = GraphNode.make_id(NodeType.DOCUMENT, skeleton.source_ref)
        graph.nodes.append(GraphNode(
            id=doc_id,
            type=NodeType.DOCUMENT,
            name=skeleton.metadata.get("title", skeleton.source_ref),
            summary=f"Document from {skeleton.source_type} source",
            source_path=skeleton.source_ref,
            fingerprint=skeleton.fingerprint,
        ))

        # Create section nodes + contains edges
        for sec in skeleton.sections[:40]:
            sec_id = GraphNode.make_id(NodeType.SECTION, sec.name)
            graph.nodes.append(GraphNode(
                id=sec_id,
                type=NodeType.SECTION,
                name=sec.name,
                summary=sec.content_preview[:150],
                source_path=skeleton.source_ref,
                fingerprint=skeleton.fingerprint,
            ))
            graph.edges.append(GraphEdge(
                source_id=doc_id,
                target_id=sec_id,
                type=EdgeType.CONTAINS,
                weight=1.0,
            ))

        # Add structural relations from extractor
        for rel in skeleton.structural_relations:
            try:
                edge_type = EdgeType(rel.get("type", "contains"))
            except ValueError:
                edge_type = EdgeType.CONTAINS
            graph.edges.append(GraphEdge(
                source_id=rel.get("source", ""),
                target_id=rel.get("target", ""),
                type=edge_type,
                weight=rel.get("weight", 0.8),
            ))

        logger.info(
            "Fallback structural graph: %d nodes, %d edges",
            graph.node_count, graph.edge_count
        )
        return graph
