"""
Knowledge Types — Universal node and edge type definitions for Mories knowledge graph.

Inspired by Understand-Anything's multi-dimensional type system,
adapted for universal data sources (documents, events, metrics, agents, etc.)
rather than code-only analysis.

Usage:
    from app.models.knowledge_types import NodeType, EdgeType, GraphNode, GraphEdge
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


# ──────────────────────────────────────────
# Node Types (10 universal types)
# ──────────────────────────────────────────

class NodeType(str, Enum):
    """
    10 universal node types covering all data domains.

    Code-agnostic: designed for documents, reports, meetings,
    simulations, metrics, and any structured/unstructured data.
    """
    DOCUMENT = "document"       # PDF, report, article, web page
    SECTION = "section"         # Section/paragraph within a document
    ENTITY = "entity"           # Person, organization, place
    CONCEPT = "concept"         # Abstract concept, pattern, topic
    EVENT = "event"             # Meeting, milestone, incident
    DATA_SOURCE = "data_source" # DB, API endpoint, file source
    METRIC = "metric"           # Numeric value, KPI, statistic
    DECISION = "decision"       # Decision, conclusion, resolution
    TASK = "task"               # Action item, to-do, assignment
    AGENT = "agent"             # Simulation agent, AI persona
    
    # Orchestration & State Tracking (Phase 3 Blackboard)
    SESSION = "session"         # A continuous working session
    ERROR_LOG = "error_log"     # Tracebacks or failures
    REVIEW = "review"           # Feedback from Expert Agent
    CODE_UPDATE = "code_update" # Pull Request or proposed change

# ──────────────────────────────────────────
# Edge Types (20 types in 7 categories)
# ──────────────────────────────────────────

class EdgeType(str, Enum):
    """
    16 edge types with semantic categories and associated weights.

    Each edge carries a default weight (0.0–1.0) indicating
    the strength of the relationship.
    """
    # Structural (0.8–1.0)
    CONTAINS = "contains"           # Parent contains child
    REFERENCES = "references"       # Cites or links to
    FOLLOWS = "follows"             # Sequential ordering

    # Causal (0.7–0.9)
    CAUSES = "causes"               # Direct causation
    SUPPORTS = "supports"           # Provides evidence for
    CONTRADICTS = "contradicts"     # Conflicts with

    # Temporal (0.6)
    PRECEDES = "precedes"           # Happens before
    CONCURRENT_WITH = "concurrent_with"  # Happens at same time

    # Semantic (0.5–0.7)
    RELATED_TO = "related_to"       # General topical relation
    SIMILAR_TO = "similar_to"       # High similarity
    ELABORATES = "elaborates"       # Expands on / details

    # Behavioral (0.7–0.8)
    CREATED_BY = "created_by"       # Authored / produced by
    DECIDED_BY = "decided_by"       # Decision made by
    ASSIGNED_TO = "assigned_to"     # Task assigned to person

    # Data flow (0.6–0.8)
    SOURCED_FROM = "sourced_from"   # Data originates from
    VALIDATES = "validates"         # Confirms / verifies
    
    # Execution & Orchestration (0.7-1.0)
    RESOLVED_BY = "resolved_by"     # Issue/Error fixed by update
    BLOCKS = "blocks"               # Error prevents Task
    IMPLEMENTS = "implements"       # Update implements Task
    REQUIRED_FOR = "required_for"   # Dependency link between Tasks


# Default weights for each edge type
EDGE_WEIGHTS: Dict[EdgeType, float] = {
    EdgeType.CONTAINS: 1.0,
    EdgeType.REFERENCES: 0.8,
    EdgeType.FOLLOWS: 0.8,
    EdgeType.CAUSES: 0.9,
    EdgeType.SUPPORTS: 0.7,
    EdgeType.CONTRADICTS: 0.7,
    EdgeType.PRECEDES: 0.6,
    EdgeType.CONCURRENT_WITH: 0.6,
    EdgeType.RELATED_TO: 0.5,
    EdgeType.SIMILAR_TO: 0.6,
    EdgeType.ELABORATES: 0.7,
    EdgeType.CREATED_BY: 0.8,
    EdgeType.DECIDED_BY: 0.7,
    EdgeType.ASSIGNED_TO: 0.7,
    EdgeType.SOURCED_FROM: 0.6,
    EdgeType.VALIDATES: 0.8,
    EdgeType.RESOLVED_BY: 0.9,
    EdgeType.BLOCKS: 0.9,
    EdgeType.IMPLEMENTS: 0.8,
    EdgeType.REQUIRED_FOR: 1.0,
}

# Edge category groupings (for UI filtering)
EDGE_CATEGORIES: Dict[str, List[EdgeType]] = {
    "structural": [EdgeType.CONTAINS, EdgeType.REFERENCES, EdgeType.FOLLOWS],
    "causal": [EdgeType.CAUSES, EdgeType.SUPPORTS, EdgeType.CONTRADICTS],
    "temporal": [EdgeType.PRECEDES, EdgeType.CONCURRENT_WITH],
    "semantic": [EdgeType.RELATED_TO, EdgeType.SIMILAR_TO, EdgeType.ELABORATES],
    "behavioral": [EdgeType.CREATED_BY, EdgeType.DECIDED_BY, EdgeType.ASSIGNED_TO],
    "data_flow": [EdgeType.SOURCED_FROM, EdgeType.VALIDATES],
    "orchestration": [EdgeType.RESOLVED_BY, EdgeType.BLOCKS, EdgeType.IMPLEMENTS, EdgeType.REQUIRED_FOR],
}


# ──────────────────────────────────────────
# Graph Data Structures
# ──────────────────────────────────────────

@dataclass
class SectionInfo:
    """Structural section extracted from a document."""
    name: str
    level: int                  # Heading level (1=H1, 2=H2, ...)
    line_range: Optional[tuple] = None  # (start_line, end_line)
    content_preview: str = ""   # First ~200 chars


@dataclass
class GraphNode:
    """
    Universal knowledge graph node.

    Compatible with Neo4j storage — maps to Entity nodes
    with extended labels and properties.
    """
    id: str                                 # Unique ID (e.g., "document:report-2024.pdf")
    type: NodeType                          # One of 10 types
    name: str                               # Display name
    summary: str = ""                       # 1-2 sentence LLM-generated summary
    tags: List[str] = field(default_factory=list)   # 3-5 classification tags
    complexity: str = "moderate"            # simple | moderate | complex
    source_path: Optional[str] = None       # Original file path or URL
    metadata: Dict[str, Any] = field(default_factory=dict)
    fingerprint: Optional[str] = None       # Content hash for incremental updates

    def to_neo4j_props(self) -> Dict[str, Any]:
        """Convert to Neo4j-compatible property dict."""
        import json
        return {
            "uuid": self.id,
            "name": self.name,
            "node_type": self.type.value,
            "summary": self.summary,
            "tags": json.dumps(self.tags),
            "complexity": self.complexity,
            "source_path": self.source_path or "",
            "fingerprint": self.fingerprint or "",
            "metadata": json.dumps(self.metadata),
        }

    @staticmethod
    def make_id(node_type: NodeType, identifier: str) -> str:
        """Generate standardized node ID."""
        safe_id = identifier.replace(" ", "_").lower()
        return f"{node_type.value}:{safe_id}"


@dataclass
class GraphEdge:
    """
    Universal knowledge graph edge with weight and direction.

    Carries semantic meaning beyond simple "RELATES_TO" connections.
    """
    source_id: str
    target_id: str
    type: EdgeType
    weight: float = 0.5
    direction: str = "forward"      # forward | backward | bidirectional
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Apply default weight from EDGE_WEIGHTS if not explicitly set."""
        if self.weight == 0.5 and self.type in EDGE_WEIGHTS:
            self.weight = EDGE_WEIGHTS[self.type]

    def to_neo4j_props(self) -> Dict[str, Any]:
        """Convert to Neo4j-compatible property dict."""
        import json
        return {
            "edge_type": self.type.value,
            "weight": self.weight,
            "direction": self.direction,
            "description": self.description or "",
            "metadata": json.dumps(self.metadata),
        }


@dataclass
class KnowledgeGraph:
    """
    Complete knowledge graph snapshot.

    Equivalent to Understand-Anything's root KnowledgeGraph structure,
    adapted for Mories' universal data model.
    """
    graph_id: str
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def node_types(self) -> List[str]:
        return list({n.type.value for n in self.nodes})

    @property
    def edge_types(self) -> List[str]:
        return list({e.type.value for e in self.edges})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_types": self.node_types,
            "edge_types": self.edge_types,
            "nodes": [n.to_neo4j_props() for n in self.nodes],
            "edges": [e.to_neo4j_props() for e in self.edges],
            "metadata": self.metadata,
        }
