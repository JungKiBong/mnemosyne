"""
Memory Data Product — Phase 11: AI-Ready Data Productization

Transforms stored memories into consumable AI-ready data products:

  1. RAG Corpus Export — memories as embedding-ready documents
  2. Knowledge Snapshot — full graph export as structured JSON
  3. Training Dataset — memory pairs for fine-tuning
  4. Memory Manifest — versioned, shareable knowledge packages
  5. Analytics Export — salience/decay/scope statistics as CSV/JSON

Each data product includes metadata: version, scope, schema, lineage.
"""

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.data_product')


class MemoryDataProduct:
    """
    AI-Ready Data Product generator for Mnemosyne memories.

    Exports memories in formats optimized for:
    - RAG (Retrieval-Augmented Generation) pipelines
    - LLM fine-tuning datasets
    - Knowledge graph visualization
    - Cross-system sharing
    """

    VERSION = "1.0.0"

    def __init__(self, driver=None):
        if driver:
            self._driver = driver
            self._owns_driver = False
        else:
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
            self._owns_driver = True

    def close(self):
        if self._owns_driver:
            self._driver.close()

    # ──────────────────────────────────────────
    # 1. RAG Corpus Export
    # ──────────────────────────────────────────

    def export_rag_corpus(
        self,
        scope: Optional[str] = None,
        min_salience: float = 0.3,
        include_relations: bool = True,
        format: str = "jsonl",
    ) -> Dict[str, Any]:
        """
        Export memories as an embedding-ready RAG corpus.

        Each document: {
            "id": "uuid",
            "text": "entity name + summary + relations",
            "metadata": { scope, salience, source_type, created_at }
        }
        """
        scope_filter = "AND e.scope = $scope" if scope else ""
        with self._driver.session() as session:
            entities = session.run(f"""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL
                  AND e.salience >= $min_sal
                  {scope_filter}
                RETURN e.uuid AS uuid, e.name AS name,
                       e.summary AS summary,
                       e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       COALESCE(e.source_type, 'document') AS source_type,
                       e.created_at AS created_at,
                       e.access_count AS access_count
                ORDER BY e.salience DESC
            """, min_sal=min_salience, scope=scope or "").data()

            # Get relations for context enrichment
            relations = []
            if include_relations:
                relations = session.run("""
                    MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
                    WHERE s.salience IS NOT NULL AND s.salience >= $min_sal
                    RETURN s.uuid AS source_uuid, s.name AS source,
                           r.name AS relation, t.name AS target,
                           r.weight AS weight
                    ORDER BY r.weight DESC
                    LIMIT 500
                """, min_sal=min_salience).data()

        # Build relation map
        rel_map: Dict[str, List[str]] = {}
        for r in relations:
            key = r["source_uuid"]
            rel_text = f"{r['source']} → {r['relation']} → {r['target']}"
            rel_map.setdefault(key, []).append(rel_text)

        # Generate documents
        documents = []
        for ent in entities:
            # Compose rich text for RAG
            text_parts = [ent["name"]]
            if ent.get("summary"):
                text_parts.append(ent["summary"])
            if ent["uuid"] in rel_map:
                text_parts.append("Relations: " + "; ".join(rel_map[ent["uuid"]][:5]))

            doc = {
                "id": ent["uuid"],
                "text": ". ".join(text_parts),
                "metadata": {
                    "name": ent["name"],
                    "salience": round(ent["salience"], 4),
                    "scope": ent["scope"],
                    "source_type": ent["source_type"],
                    "access_count": ent.get("access_count", 0),
                    "created_at": ent.get("created_at", ""),
                },
            }
            documents.append(doc)

        # Format output
        if format == "jsonl":
            content = "\n".join(json.dumps(d, ensure_ascii=False) for d in documents)
        else:
            content = json.dumps(documents, ensure_ascii=False, indent=2)

        return {
            "product_type": "rag_corpus",
            "version": self.VERSION,
            "format": format,
            "document_count": len(documents),
            "scope_filter": scope,
            "min_salience": min_salience,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content": content,
        }

    # ──────────────────────────────────────────
    # 2. Knowledge Graph Snapshot
    # ──────────────────────────────────────────

    def export_knowledge_snapshot(
        self,
        scope: Optional[str] = None,
        min_salience: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Export full knowledge graph as a structured snapshot.

        Includes nodes, edges, scope hierarchy, and audit summary.
        Compatible with Neo4j import, vis.js, or D3 visualization.
        """
        scope_filter = "AND e.scope = $scope" if scope else ""
        with self._driver.session() as session:
            # Nodes
            nodes = session.run(f"""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL AND e.salience >= $min_sal
                  {scope_filter}
                RETURN e.uuid AS id, e.name AS label,
                       COALESCE(e.entity_type, 'unknown') AS type,
                       e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       COALESCE(e.source_type, 'document') AS source_type,
                       e.summary AS summary,
                       e.access_count AS access_count,
                       e.created_at AS created_at,
                       e.owner_id AS owner_id
                ORDER BY e.salience DESC
            """, min_sal=min_salience, scope=scope or "").data()

            # Edges
            edges = session.run(f"""
                MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
                WHERE s.salience IS NOT NULL AND s.salience >= $min_sal
                  {scope_filter.replace('e.', 's.')}
                RETURN s.uuid AS source, t.uuid AS target,
                       r.name AS relation, r.weight AS weight,
                       r.fact AS fact
                ORDER BY r.weight DESC
            """, min_sal=min_salience, scope=scope or "").data()

            # Agent nodes
            agents = session.run("""
                MATCH (a:Agent)
                RETURN a.agent_id AS id, a.name AS label,
                       a.role AS role,
                       a.subscribed_scopes AS scopes,
                       a.shared_count AS shared_count
            """).data()

        return {
            "product_type": "knowledge_snapshot",
            "version": self.VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema": {
                "node_types": ["Entity", "Agent"],
                "edge_types": ["RELATES_TO", "SHARED", "EMPATHY_BOOSTED"],
                "scope_hierarchy": ["personal", "tribal", "social", "global"],
            },
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "agent_count": len(agents),
            },
            "nodes": nodes,
            "edges": edges,
            "agents": agents,
        }

    # ──────────────────────────────────────────
    # 3. Training Dataset (Q&A pairs)
    # ──────────────────────────────────────────

    def export_training_dataset(
        self,
        format: str = "jsonl",
        min_salience: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Generate Q&A training pairs from knowledge relationships.

        Each pair: {
            "instruction": "What is the relationship between X and Y?",
            "input": "",
            "output": "X [relation] Y. Context: ..."
        }
        """
        with self._driver.session() as session:
            triples = session.run("""
                MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity)
                WHERE s.salience >= $min_sal AND t.salience >= $min_sal
                RETURN s.name AS source, r.name AS relation,
                       t.name AS target, r.fact AS fact,
                       r.weight AS weight,
                       s.summary AS source_summary,
                       t.summary AS target_summary
                ORDER BY r.weight DESC
                LIMIT 200
            """, min_sal=min_salience).data()

        pairs = []
        for t in triples:
            # QA pair 1: Direct question
            pairs.append({
                "instruction": f"{t['source']}와(과) {t['target']}의 관계는?",
                "input": "",
                "output": f"{t['source']}은(는) {t['target']}과(와) '{t['relation']}' 관계입니다."
                         + (f" {t['fact']}" if t.get('fact') else ""),
            })
            # QA pair 2: Reverse
            pairs.append({
                "instruction": f"{t['target']}에 대해 알려줘.",
                "input": "",
                "output": f"{t['target']}은(는) {t['source']}와(과) '{t['relation']}' 관계에 있습니다."
                         + (f" 요약: {t['target_summary']}" if t.get('target_summary') else ""),
            })

        if format == "jsonl":
            content = "\n".join(json.dumps(p, ensure_ascii=False) for p in pairs)
        else:
            content = json.dumps(pairs, ensure_ascii=False, indent=2)

        return {
            "product_type": "training_dataset",
            "version": self.VERSION,
            "format": format,
            "pair_count": len(pairs),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content": content,
        }

    # ──────────────────────────────────────────
    # 4. Memory Manifest (Versioned Package)
    # ──────────────────────────────────────────

    def create_manifest(
        self,
        name: str,
        description: str = "",
        scope: Optional[str] = None,
        include_audit: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a versioned Memory Manifest — a shareable knowledge package.

        Contains: metadata, entities, relations, audit trail, and lineage.
        """
        manifest_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Gather data
        snapshot = self.export_knowledge_snapshot(scope=scope)
        rag = self.export_rag_corpus(scope=scope, format="json")

        # Audit trail summary
        audit_summary = {}
        if include_audit:
            with self._driver.session() as session:
                audit_stats = session.run("""
                    MATCH (rev:MemoryRevision)
                    WITH rev.change_type AS ct, count(rev) AS cnt
                    RETURN ct, cnt ORDER BY cnt DESC
                """).data()
                audit_summary = {s["ct"]: s["cnt"] for s in audit_stats}

        manifest = {
            "manifest_id": manifest_id,
            "name": name,
            "description": description,
            "version": self.VERSION,
            "created_at": now,
            "scope_filter": scope,
            "lineage": {
                "system": "Mnemosyne",
                "generated_by": "MemoryDataProduct",
                "source_db": "Neo4j",
                "export_format": "manifest_v1",
            },
            "stats": snapshot["stats"],
            "audit_summary": audit_summary,
            "schema": snapshot["schema"],
            "entities": snapshot["nodes"],
            "relations": snapshot["edges"],
            "agents": snapshot["agents"],
            "rag_documents": json.loads(rag["content"]) if rag.get("content") else [],
        }

        # Persist manifest record in Neo4j
        with self._driver.session() as session:
            session.run("""
                CREATE (m:MemoryManifest {
                    manifest_id: $mid,
                    name: $name,
                    version: $version,
                    created_at: $now,
                    scope_filter: $scope,
                    node_count: $nodes,
                    edge_count: $edges,
                    description: $desc
                })
            """,
                mid=manifest_id, name=name, version=self.VERSION,
                now=now, scope=scope or "all",
                nodes=snapshot["stats"]["node_count"],
                edges=snapshot["stats"]["edge_count"],
                desc=description,
            )

        logger.info(
            f"Manifest created: {name} ({manifest_id[:8]}) — "
            f"{snapshot['stats']['node_count']} nodes, "
            f"{snapshot['stats']['edge_count']} edges"
        )

        return manifest

    # ──────────────────────────────────────────
    # 5. Analytics Export
    # ──────────────────────────────────────────

    def export_analytics_csv(self) -> str:
        """Export memory analytics as CSV for dashboards/spreadsheets."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL
                RETURN e.uuid AS uuid, e.name AS name,
                       e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       COALESCE(e.source_type, 'document') AS source_type,
                       e.access_count AS access_count,
                       e.last_accessed AS last_accessed,
                       e.created_at AS created_at,
                       e.owner_id AS owner_id
                ORDER BY e.salience DESC
            """).data()

        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)

        return output.getvalue()

    def list_manifests(self) -> List[Dict[str, Any]]:
        """List all created manifests."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (m:MemoryManifest)
                RETURN m.manifest_id AS manifest_id,
                       m.name AS name,
                       m.version AS version,
                       m.created_at AS created_at,
                       m.scope_filter AS scope_filter,
                       m.node_count AS node_count,
                       m.edge_count AS edge_count,
                       m.description AS description
                ORDER BY m.created_at DESC
            """).data()
        return records
