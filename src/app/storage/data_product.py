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
    AI-Ready Data Product generator for Mories memories.

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
                "system": "Mories",
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

    # ──────────────────────────────────────────
    # 6. Import — Manifest / RAG Corpus
    # ──────────────────────────────────────────

    def import_manifest(
        self,
        manifest: Dict[str, Any],
        target_graph_id: str = "",
        merge_strategy: str = "merge",
        imported_by: str = "api",
    ) -> Dict[str, Any]:
        """
        Import a Memory Manifest JSON back into Neo4j.

        Supports both fresh manifests and exports from other Mories instances.
        Uses MERGE for idempotent imports (safe to re-run).

        Args:
            manifest: The manifest dict (from create_manifest or JSON file).
            target_graph_id: Optional graph_id to assign imported nodes to.
            merge_strategy: 'merge' (upsert) or 'create' (always create new).
            imported_by: Who triggered the import.

        Returns:
            Import statistics and list of imported UUIDs.
        """
        now = datetime.now(timezone.utc).isoformat()
        nodes = manifest.get("entities", manifest.get("nodes", []))
        edges = manifest.get("relations", manifest.get("edges", []))
        agents = manifest.get("agents", [])
        source_manifest_id = manifest.get("manifest_id", "unknown")
        source_name = manifest.get("name", "Imported Manifest")

        stats = {
            "nodes_imported": 0,
            "nodes_skipped": 0,
            "edges_imported": 0,
            "edges_skipped": 0,
            "agents_imported": 0,
            "errors": [],
        }

        with self._driver.session() as session:
            # ── Import Entities (Nodes) ──
            for node in nodes:
                try:
                    node_id = node.get("id") or node.get("uuid")
                    if not node_id:
                        # Generate new UUID for nodes without one
                        node_id = str(uuid.uuid4())

                    label = node.get("label") or node.get("name", "")
                    if not label:
                        stats["nodes_skipped"] += 1
                        continue

                    if merge_strategy == "create":
                        # Always create new node with new UUID
                        node_id = str(uuid.uuid4())
                        query = """
                            CREATE (e:Entity:Memory {
                                uuid: $uuid,
                                graph_id: $graph_id,
                                name: $name,
                                name_lower: $name_lower,
                                entity_type: $entity_type,
                                summary: $summary,
                                salience: $salience,
                                scope: $scope,
                                source_type: $source_type,
                                access_count: $access_count,
                                created_at: $created_at,
                                owner_id: $owner_id,
                                imported: true,
                                imported_at: $now,
                                imported_by: $imported_by,
                                import_source: $import_source
                            })
                        """
                    else:
                        # MERGE — upsert (safe for re-import)
                        query = """
                            MERGE (e:Entity {uuid: $uuid})
                            ON CREATE SET
                                e:Memory,
                                e.graph_id = $graph_id,
                                e.name = $name,
                                e.name_lower = $name_lower,
                                e.entity_type = $entity_type,
                                e.summary = $summary,
                                e.salience = $salience,
                                e.scope = $scope,
                                e.source_type = $source_type,
                                e.access_count = $access_count,
                                e.created_at = $created_at,
                                e.owner_id = $owner_id,
                                e.imported = true,
                                e.imported_at = $now,
                                e.imported_by = $imported_by,
                                e.import_source = $import_source
                            ON MATCH SET
                                e.salience = CASE
                                    WHEN $salience > COALESCE(e.salience, 0) THEN $salience
                                    ELSE e.salience
                                END,
                                e.summary = COALESCE($summary, e.summary),
                                e.imported = true,
                                e.imported_at = $now
                        """

                    session.run(query,
                        uuid=node_id,
                        graph_id=target_graph_id or node.get("graph_id", ""),
                        name=label,
                        name_lower=label.lower(),
                        entity_type=node.get("type", node.get("entity_type", "unknown")),
                        summary=node.get("summary", ""),
                        salience=node.get("salience", 0.5),
                        scope=node.get("scope", "personal"),
                        source_type=node.get("source_type", "imported"),
                        access_count=node.get("access_count", 0) or 0,
                        created_at=node.get("created_at", now),
                        owner_id=node.get("owner_id", ""),
                        now=now,
                        imported_by=imported_by,
                        import_source=source_manifest_id,
                    )
                    stats["nodes_imported"] += 1

                except Exception as e:
                    stats["errors"].append(f"Node '{label}': {str(e)[:100]}")
                    stats["nodes_skipped"] += 1

            # ── Import Relations (Edges) ──
            for edge in edges:
                try:
                    source_uuid = edge.get("source")
                    target_uuid = edge.get("target")
                    relation = edge.get("relation", "RELATES_TO")

                    if not source_uuid or not target_uuid:
                        stats["edges_skipped"] += 1
                        continue

                    session.run("""
                        MATCH (s:Entity {uuid: $source})
                        MATCH (t:Entity {uuid: $target})
                        MERGE (s)-[r:RELATES_TO {name: $relation}]->(t)
                        ON CREATE SET
                            r.weight = $weight,
                            r.fact = $fact,
                            r.imported = true,
                            r.imported_at = $now
                        ON MATCH SET
                            r.weight = CASE
                                WHEN $weight > COALESCE(r.weight, 0) THEN $weight
                                ELSE r.weight
                            END
                    """,
                        source=source_uuid,
                        target=target_uuid,
                        relation=relation,
                        weight=edge.get("weight", 1.0) or 1.0,
                        fact=edge.get("fact", ""),
                        now=now,
                    )
                    stats["edges_imported"] += 1

                except Exception as e:
                    stats["errors"].append(f"Edge '{relation}': {str(e)[:100]}")
                    stats["edges_skipped"] += 1

            # ── Import Agents ──
            for agent in agents:
                try:
                    agent_id = agent.get("id") or agent.get("agent_id")
                    if not agent_id:
                        continue

                    session.run("""
                        MERGE (a:Agent {agent_id: $agent_id})
                        ON CREATE SET
                            a.name = $name,
                            a.role = $role,
                            a.subscribed_scopes = $scopes,
                            a.registered_at = $now,
                            a.last_active = $now,
                            a.imported = true
                        ON MATCH SET
                            a.last_active = $now
                    """,
                        agent_id=agent_id,
                        name=agent.get("label") or agent.get("name", ""),
                        role=agent.get("role", "observer"),
                        scopes=agent.get("scopes") or agent.get("subscribed_scopes") or ["personal"],
                        now=now,
                    )
                    stats["agents_imported"] += 1

                except Exception as e:
                    stats["errors"].append(f"Agent: {str(e)[:100]}")

            # ── Record import manifest ──
            import_id = str(uuid.uuid4())
            session.run("""
                CREATE (m:MemoryImport {
                    import_id: $import_id,
                    source_manifest_id: $source_id,
                    source_name: $source_name,
                    imported_at: $now,
                    imported_by: $imported_by,
                    merge_strategy: $strategy,
                    target_graph_id: $graph_id,
                    nodes_imported: $nodes,
                    edges_imported: $edges,
                    agents_imported: $agents
                })
            """,
                import_id=import_id,
                source_id=source_manifest_id,
                source_name=source_name,
                now=now,
                imported_by=imported_by,
                strategy=merge_strategy,
                graph_id=target_graph_id,
                nodes=stats["nodes_imported"],
                edges=stats["edges_imported"],
                agents=stats["agents_imported"],
            )

        logger.info(
            f"Manifest imported: {source_name} — "
            f"{stats['nodes_imported']} nodes, "
            f"{stats['edges_imported']} edges, "
            f"{stats['agents_imported']} agents"
        )

        return {
            "status": "imported",
            "import_id": import_id,
            "source_manifest_id": source_manifest_id,
            "source_name": source_name,
            "merge_strategy": merge_strategy,
            "target_graph_id": target_graph_id,
            "stats": stats,
            "imported_at": now,
        }

    def import_rag_corpus(
        self,
        content: str,
        target_graph_id: str = "",
        default_scope: str = "personal",
        imported_by: str = "api",
    ) -> Dict[str, Any]:
        """
        Import a JSONL RAG corpus file into Neo4j as Entity nodes.

        Each line: {"id":"uuid","text":"...","metadata":{"name":"...","salience":0.9,...}}

        Args:
            content: JSONL string (one JSON object per line).
            target_graph_id: Optional graph_id for imported nodes.
            default_scope: Scope to assign if not in metadata.
            imported_by: Who triggered the import.

        Returns:
            Import statistics.
        """
        now = datetime.now(timezone.utc).isoformat()
        lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
        stats = {"total_lines": len(lines), "imported": 0, "skipped": 0, "errors": []}

        with self._driver.session() as session:
            for i, line in enumerate(lines):
                try:
                    doc = json.loads(line)
                    doc_id = doc.get("id") or str(uuid.uuid4())
                    text = doc.get("text", "")
                    meta = doc.get("metadata", {})

                    if not text:
                        stats["skipped"] += 1
                        continue

                    name = meta.get("name") or text[:80]
                    salience = meta.get("salience", 0.5)
                    scope = meta.get("scope", default_scope)

                    session.run("""
                        MERGE (e:Entity {uuid: $uuid})
                        ON CREATE SET
                            e:Memory,
                            e.graph_id = $graph_id,
                            e.name = $name,
                            e.name_lower = $name_lower,
                            e.summary = $text,
                            e.salience = $salience,
                            e.scope = $scope,
                            e.source_type = $source_type,
                            e.access_count = $access_count,
                            e.created_at = $created_at,
                            e.imported = true,
                            e.imported_at = $now,
                            e.imported_by = $imported_by
                        ON MATCH SET
                            e.summary = COALESCE($text, e.summary),
                            e.imported = true,
                            e.imported_at = $now
                    """,
                        uuid=doc_id,
                        graph_id=target_graph_id,
                        name=name,
                        name_lower=name.lower(),
                        text=text,
                        salience=salience,
                        scope=scope,
                        source_type=meta.get("source_type", "imported"),
                        access_count=meta.get("access_count", 0) or 0,
                        created_at=meta.get("created_at", now),
                        now=now,
                        imported_by=imported_by,
                    )
                    stats["imported"] += 1

                except json.JSONDecodeError as e:
                    stats["errors"].append(f"Line {i+1}: invalid JSON")
                    stats["skipped"] += 1
                except Exception as e:
                    stats["errors"].append(f"Line {i+1}: {str(e)[:100]}")
                    stats["skipped"] += 1

        logger.info(f"RAG corpus imported: {stats['imported']}/{stats['total_lines']} documents")

        return {
            "status": "imported",
            "format": "jsonl",
            "target_graph_id": target_graph_id,
            "default_scope": default_scope,
            "stats": stats,
            "imported_at": now,
        }

    def list_imports(self) -> List[Dict[str, Any]]:
        """List all import records."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (m:MemoryImport)
                RETURN m.import_id AS import_id,
                       m.source_manifest_id AS source_manifest_id,
                       m.source_name AS source_name,
                       m.imported_at AS imported_at,
                       m.imported_by AS imported_by,
                       m.merge_strategy AS merge_strategy,
                       m.target_graph_id AS target_graph_id,
                       m.nodes_imported AS nodes_imported,
                       m.edges_imported AS edges_imported,
                       m.agents_imported AS agents_imported
                ORDER BY m.imported_at DESC
            """).data()
        return records
