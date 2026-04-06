"""
Neo4j Memory Backend — Implements MemoryBridge protocol via Neo4j Bolt driver.

Persists harness execution experiences, reflections, patterns, and instructions
as a connected knowledge graph in Neo4j.

Schema:
  (:HarnessExperience {run_id, harness_id, domain, type, elapsed_ms, ...})
    -[:USED_TOOL]-> (:Tool {name, type})
    -[:PRODUCED]-> (:Reflection {event, lesson, severity})
    -[:HAS_PATTERN]-> (:HarnessPattern {trigger, tool_chain})
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_neo4j_driver(uri: str, user: str, password: str):
    """Lazy-load Neo4j driver."""
    try:
        from neo4j import GraphDatabase
        return GraphDatabase.driver(uri, auth=(user, password))
    except ImportError:
        raise RuntimeError(
            "neo4j package not installed. Run: pip install neo4j"
        )


class Neo4jMemoryBackend:
    """
    Neo4j-backed memory backend for MemoryBridge.

    Implements the MemoryBridge protocol:
      - ingest(content, salience, scope, source, metadata) → dict
      - record_pattern(domain, tool_chain, trigger, metadata) → dict
      - record_reflection(event, lesson, domain, severity) → dict
      - record_instruction(category, rule, description, strictness) → dict
      - find_patterns(domain, limit) → list  # For OODA recall
      - get_execution_tree(run_id) → dict    # For dashboard
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.environ.get("NEO4J_USER", "neo4j")
        self._password = password or os.environ.get("NEO4J_PASSWORD", "password")
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            self._driver = _get_neo4j_driver(
                self._uri, self._user, self._password
            )
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    # ─── MemoryBridge Protocol ─────────────────

    def ingest(
        self,
        content: str,
        salience: float = 0.7,
        scope: str = "tribal",
        source: str = "harness",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Ingest a harness experience into Neo4j as a knowledge node."""
        meta = metadata or {}
        node_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        driver = self._get_driver()
        with driver.session() as session:
            # Create Experience node
            session.run(
                """
                CREATE (e:HarnessExperience {
                    uuid: $uuid,
                    content: $content,
                    salience: $salience,
                    scope: $scope,
                    source: $source,
                    harness_id: $harness_id,
                    domain: $domain,
                    run_id: $run_id,
                    experience_type: $exp_type,
                    elapsed_ms: $elapsed_ms,
                    created_at: $created_at
                })
                """,
                uuid=node_id,
                content=content[:2000],  # Truncate for safety
                salience=salience,
                scope=scope,
                source=source,
                harness_id=meta.get("harness_id", "unknown"),
                domain=meta.get("domain", "unknown"),
                run_id=meta.get("run_id", ""),
                exp_type=meta.get("experience_type", "SUCCESS"),
                elapsed_ms=meta.get("elapsed_ms", 0),
                created_at=now,
            )

            # Create Tool nodes and relationships
            tool_chain = meta.get("tool_chain", [])
            for i, tool_name in enumerate(tool_chain):
                tool_type = meta.get("tool_types", {}).get(tool_name, "unknown")
                session.run(
                    """
                    MERGE (t:Tool {name: $tool_name})
                    ON CREATE SET t.type = $tool_type
                    WITH t
                    MATCH (e:HarnessExperience {uuid: $exp_uuid})
                    CREATE (e)-[:USED_TOOL {position: $pos}]->(t)
                    """,
                    tool_name=tool_name,
                    tool_type=tool_type,
                    exp_uuid=node_id,
                    pos=i,
                )

        logger.info(
            f"[Neo4jBackend] Ingested experience {node_id} "
            f"({meta.get('experience_type', '?')})"
        )
        return {"status": "ingested", "uuid": node_id}

    def record_pattern(
        self,
        domain: str,
        tool_chain: List[str],
        trigger: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Record a reusable harness pattern."""
        meta = metadata or {}
        pattern_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                CREATE (p:HarnessPattern {
                    uuid: $uuid,
                    domain: $domain,
                    tool_chain: $tool_chain,
                    trigger: $trigger,
                    scope: $scope,
                    source_harness: $source_harness,
                    created_at: $created_at
                })
                """,
                uuid=pattern_id,
                domain=domain,
                tool_chain=json.dumps(tool_chain),
                trigger=trigger,
                scope=meta.get("scope", "tribal"),
                source_harness=meta.get("source_harness", "unknown"),
                created_at=now,
            )

        logger.info(f"[Neo4jBackend] Recorded pattern {pattern_id}")
        return {"status": "recorded", "uuid": pattern_id}

    def record_reflection(
        self,
        event: str,
        lesson: str,
        domain: str = "general",
        severity: str = "medium",
    ) -> dict:
        """Record a failure reflection (lesson learned)."""
        reflection_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                CREATE (r:Reflection {
                    uuid: $uuid,
                    event: $event,
                    lesson: $lesson,
                    domain: $domain,
                    severity: $severity,
                    source: 'harness',
                    created_at: $created_at
                })
                """,
                uuid=reflection_id,
                event=event[:500],
                lesson=lesson[:1000],
                domain=domain,
                severity=severity,
                created_at=now,
            )

        logger.info(f"[Neo4jBackend] Recorded reflection {reflection_id}")
        return {"status": "recorded", "uuid": reflection_id}

    def record_instruction(
        self,
        category: str = "general",
        rule: str = "",
        description: str = "",
        strictness: str = "should",
    ) -> dict:
        """Record an instructional rule from human feedback."""
        instruction_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                """
                CREATE (i:Instruction {
                    uuid: $uuid,
                    category: $category,
                    rule: $rule,
                    description: $description,
                    strictness: $strictness,
                    source: 'harness_hitl',
                    created_at: $created_at
                })
                """,
                uuid=instruction_id,
                category=category,
                rule=rule[:500],
                description=description[:1000],
                strictness=strictness,
                created_at=now,
            )

        logger.info(f"[Neo4jBackend] Recorded instruction {instruction_id}")
        return {"status": "recorded", "uuid": instruction_id}

    # ─── Query Methods (for OODA + Dashboard) ──

    def find_patterns(
        self, domain: Optional[str] = None, limit: int = 5
    ) -> List[dict]:
        """Find historically successful patterns for OODA recall."""
        driver = self._get_driver()
        with driver.session() as session:
            if domain:
                result = session.run(
                    """
                    MATCH (p:HarnessPattern)
                    WHERE p.domain = $domain OR p.domain = 'general'
                    RETURN p.uuid AS uuid, p.domain AS domain,
                           p.tool_chain AS tool_chain, p.trigger AS trigger,
                           p.created_at AS created_at
                    ORDER BY p.created_at DESC
                    LIMIT $limit
                    """,
                    domain=domain, limit=limit,
                )
            else:
                result = session.run(
                    """
                    MATCH (p:HarnessPattern)
                    RETURN p.uuid AS uuid, p.domain AS domain,
                           p.tool_chain AS tool_chain, p.trigger AS trigger,
                           p.created_at AS created_at
                    ORDER BY p.created_at DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                )

            patterns = []
            for record in result:
                tc = record["tool_chain"]
                if isinstance(tc, str):
                    try:
                        tc = json.loads(tc)
                    except json.JSONDecodeError:
                        tc = [tc]
                patterns.append({
                    "uuid": record["uuid"],
                    "domain": record["domain"],
                    "tool_chain": tc,
                    "trigger": record["trigger"],
                    "created_at": record["created_at"],
                })
            return patterns

    def find_reflections(
        self, domain: Optional[str] = None, limit: int = 5
    ) -> List[dict]:
        """Find past failure reflections for similar domains."""
        driver = self._get_driver()
        with driver.session() as session:
            if domain:
                result = session.run(
                    """
                    MATCH (r:Reflection)
                    WHERE r.domain = $domain
                    RETURN r.uuid AS uuid, r.event AS event,
                           r.lesson AS lesson, r.severity AS severity,
                           r.created_at AS created_at
                    ORDER BY r.created_at DESC
                    LIMIT $limit
                    """,
                    domain=domain, limit=limit,
                )
            else:
                result = session.run(
                    """
                    MATCH (r:Reflection)
                    RETURN r.uuid AS uuid, r.event AS event,
                           r.lesson AS lesson, r.severity AS severity,
                           r.created_at AS created_at
                    ORDER BY r.created_at DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                )

            return [dict(record) for record in result]

    def get_execution_tree(self, run_id: str) -> Optional[dict]:
        """Reconstruct execution tree from Neo4j for dashboard."""
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (e:HarnessExperience {run_id: $run_id})
                OPTIONAL MATCH (e)-[ut:USED_TOOL]->(t:Tool)
                RETURN e, collect({tool: t.name, type: t.type, pos: ut.position}) AS tools
                ORDER BY e.created_at
                """,
                run_id=run_id,
            )
            records = list(result)
            if not records:
                return None

            tree = {"run_id": run_id, "experiences": []}
            for record in records:
                exp = dict(record["e"])
                exp["tools"] = sorted(
                    record["tools"],
                    key=lambda x: x.get("pos", 0),
                )
                tree["experiences"].append(exp)
            return tree
