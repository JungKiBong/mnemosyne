"""
neo4j_memory_backend.py — Neo4j Direct 메모리 백엔드

MemoryBridge의 pluggable backend 구현체.
Mories 내부 Neo4j 그래프 데이터베이스에 직접 연결하여
하네스 경험을 Entity/Relation 노드로 영구 저장한다.

MCP나 REST API 없이, 같은 프로세스 내에서
GraphStorage 인터페이스를 직접 활용하는 경우.

작성: 2026-04-04
"""
import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("harness.neo4j_backend")


# ─────────────────────────────────────────────
# Cypher Templates — Harness Ontology
# ─────────────────────────────────────────────

CREATE_HARNESS_EXPERIENCE_NODE = """
MERGE (h:HarnessExperience {harness_id: $harness_id, run_id: $run_id})
SET h.uuid = $uuid,
    h.domain = $domain,
    h.experience_type = $experience_type,
    h.tool_chain = $tool_chain,
    h.elapsed_ms = $elapsed_ms,
    h.summary = $summary,
    h.error = $error,
    h.salience = $salience,
    h.scope = $scope,
    h.source = $source,
    h.created_at = $created_at,
    h.content = $content
"""

CREATE_PATTERN_NODE = """
MERGE (p:HarnessPattern {domain: $domain, tool_chain_hash: $tool_chain_hash})
ON CREATE SET
    p.uuid = $uuid,
    p.tool_chain = $tool_chain,
    p.trigger = $trigger,
    p.first_seen = $now,
    p.execution_count = 1,
    p.success_count = 1,
    p.tags = $tags
ON MATCH SET
    p.execution_count = p.execution_count + 1,
    p.success_count = p.success_count + 1,
    p.last_seen = $now
"""

CREATE_REFLECTION_NODE = """
CREATE (r:Reflection {
    uuid: $uuid,
    event: $event,
    lesson: $lesson,
    domain: $domain,
    severity: $severity,
    created_at: $now
})
"""

LINK_EXPERIENCE_TO_DOMAIN = """
MATCH (h:HarnessExperience {uuid: $exp_uuid})
MERGE (d:Domain {name: $domain})
MERGE (h)-[:BELONGS_TO]->(d)
"""

LINK_PATTERN_TO_DOMAIN = """
MATCH (p:HarnessPattern {uuid: $pat_uuid})
MERGE (d:Domain {name: $domain})
MERGE (p)-[:BELONGS_TO]->(d)
"""


class Neo4jMemoryBackend:
    """
    Neo4j Direct Memory Backend.

    동일 프로세스 내 Neo4j 드라이버를 직접 사용.
    MCP/REST 없이도 Mories Knowledge Graph에 기록.
    """

    def __init__(self, driver=None):
        """
        Args:
            driver: neo4j.Driver 인스턴스.
                    None이면 Config로부터 자동 생성.
        """
        if driver is not None:
            self._driver = driver
            self._owns_driver = False
        else:
            from neo4j import GraphDatabase
            from src.app.config import Config
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
            )
            self._owns_driver = True

        self._ensure_schema()

    def close(self):
        if self._owns_driver and self._driver:
            self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _ensure_schema(self):
        """하네스 전용 인덱스/제약 조건 생성."""
        queries = [
            "CREATE CONSTRAINT harness_exp_uuid IF NOT EXISTS "
            "FOR (h:HarnessExperience) REQUIRE h.uuid IS UNIQUE",
            "CREATE CONSTRAINT harness_pat_uuid IF NOT EXISTS "
            "FOR (p:HarnessPattern) REQUIRE p.uuid IS UNIQUE",
            "CREATE CONSTRAINT reflection_uuid IF NOT EXISTS "
            "FOR (r:Reflection) REQUIRE r.uuid IS UNIQUE",
        ]
        try:
            with self._driver.session() as session:
                for q in queries:
                    session.run(q)
        except Exception as e:
            logger.warning(f"Schema creation warning (may already exist): {e}")

    # ─────────────────────────────────────────
    # MemoryBridge Backend Protocol
    # ─────────────────────────────────────────

    def ingest(
        self,
        content: str,
        salience: float,
        scope: str,
        source: str,
        metadata: Dict[str, Any],
    ) -> dict:
        """경험을 HarnessExperience 노드로 저장."""
        node_uuid = str(_uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        harness_id = metadata.get("harness_id", "unknown")
        run_id = metadata.get("run_id", "")

        with self._driver.session() as session:
            session.run(
                CREATE_HARNESS_EXPERIENCE_NODE,
                uuid=node_uuid,
                harness_id=harness_id,
                run_id=run_id,
                domain=metadata.get("domain", "unknown"),
                experience_type=metadata.get("experience_type", "SUCCESS"),
                tool_chain=metadata.get("tool_chain", []),
                elapsed_ms=metadata.get("elapsed_ms", 0),
                summary=content[:500],
                error=None,
                salience=salience,
                scope=scope,
                source=source,
                created_at=now,
                content=content,
            )

            # Domain 연결
            session.run(
                LINK_EXPERIENCE_TO_DOMAIN,
                exp_uuid=node_uuid,
                domain=metadata.get("domain", "unknown"),
            )

        logger.info(
            f"Neo4j: Ingested HarnessExperience {node_uuid} "
            f"(harness={harness_id})"
        )
        return {"status": "ingested", "id": node_uuid}

    def record_pattern(
        self,
        domain: str,
        tool_chain: List[str],
        trigger: str,
        metadata: Dict[str, Any],
    ) -> dict:
        """재사용 가능한 패턴을 HarnessPattern 노드로 등록."""
        import hashlib

        chain_str = "→".join(tool_chain)
        chain_hash = hashlib.md5(
            f"{domain}:{chain_str}".encode()
        ).hexdigest()
        node_uuid = str(_uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            session.run(
                CREATE_PATTERN_NODE,
                uuid=node_uuid,
                domain=domain,
                tool_chain=tool_chain,
                tool_chain_hash=chain_hash,
                trigger=trigger,
                now=now,
                tags=metadata.get("tags", [domain, "auto-captured"]),
            )

            session.run(
                LINK_PATTERN_TO_DOMAIN,
                pat_uuid=node_uuid,
                domain=domain,
            )

        logger.info(
            f"Neo4j: Recorded HarnessPattern "
            f"({domain}: {chain_str})"
        )
        return {"status": "recorded", "id": node_uuid}

    def record_reflection(
        self,
        event: str,
        lesson: str,
        domain: str,
        severity: str,
    ) -> dict:
        """교훈(Reflection) 노드를 기록."""
        node_uuid = str(_uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            session.run(
                CREATE_REFLECTION_NODE,
                uuid=node_uuid,
                event=event[:500],
                lesson=lesson[:1000],
                domain=domain,
                severity=severity,
                now=now,
            )

        logger.info(f"Neo4j: Recorded Reflection ({severity}: {event[:60]})")
        return {"status": "recorded", "id": node_uuid}

    # ─────────────────────────────────────────
    # Query Methods (다른 컴포넌트가 학습 결과 검색)
    # ─────────────────────────────────────────

    def find_patterns(
        self,
        domain: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        """도메인별 성공 패턴 검색."""
        if domain:
            query = """
                MATCH (p:HarnessPattern {domain: $domain})
                RETURN p ORDER BY p.execution_count DESC
                LIMIT $limit
            """
            params = {"domain": domain, "limit": limit}
        else:
            query = """
                MATCH (p:HarnessPattern)
                RETURN p ORDER BY p.execution_count DESC
                LIMIT $limit
            """
            params = {"limit": limit}

        with self._driver.session() as session:
            records = session.run(query, **params).data()
            return [dict(r["p"]) for r in records]

    def find_reflections(
        self,
        domain: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 10,
    ) -> List[dict]:
        """교훈 검색 (도메인/심각도로 필터)."""
        conditions = []
        params: dict = {"limit": limit}

        if domain:
            conditions.append("r.domain = $domain")
            params["domain"] = domain
        if severity:
            conditions.append("r.severity = $severity")
            params["severity"] = severity

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            MATCH (r:Reflection) {where}
            RETURN r ORDER BY r.created_at DESC
            LIMIT $limit
        """

        with self._driver.session() as session:
            records = session.run(query, **params).data()
            return [dict(r["r"]) for r in records]

    def get_domain_stats(self) -> List[dict]:
        """도메인별 실행 통계 요약."""
        query = """
            MATCH (d:Domain)<-[:BELONGS_TO]-(h:HarnessExperience)
            RETURN d.name AS domain,
                   count(h) AS total_runs,
                   sum(CASE WHEN h.experience_type = 'SUCCESS'
                        THEN 1 ELSE 0 END) AS successes,
                   sum(CASE WHEN h.experience_type = 'FAILURE'
                        THEN 1 ELSE 0 END) AS failures,
                   avg(h.elapsed_ms) AS avg_elapsed_ms
            ORDER BY total_runs DESC
        """
        with self._driver.session() as session:
            return session.run(query).data()
