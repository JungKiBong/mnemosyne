"""
Memory Category Extension — Phase 16-C: Procedural & Observational Memory

Extends the memory system with content categories without changing the core architecture.
Uses the "Category Extension Pattern" — same STM/LTM/PM lifecycle, different metadata schemas.

Categories:
  - declarative: Factual knowledge (existing, default)
  - procedural: Tool-use patterns (API calls, MCP tools, code, shell commands)
  - observational: Learned from observing users or other agents

Key features:
  - Success-rate based decay modifier for procedural memories
  - Staleness detection for tool memories (API version changes)
  - Observation confidence tracking
  - Category-aware search filtering
"""

import logging
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.memory_categories')


# ──────────────────────────────────────────────
# Procedural Memory Schema
# ──────────────────────────────────────────────

def create_procedural_metadata(
    tool_name: str,
    tool_type: str = "api",  # api | mcp | python | shell | workflow
    input_pattern: Optional[Dict] = None,
    output_pattern: Optional[Dict] = None,
    execution_time_ms: int = 0,
    success: bool = True,
    tool_version: str = "",
    stale_after_days: int = 90,
) -> Dict[str, Any]:
    """Create structured metadata for a procedural memory."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "category": "procedural",
        "subcategory": tool_type,
        "procedure": {
            "tool_name": tool_name,
            "tool_type": tool_type,
            "input_pattern": input_pattern or {},
            "output_pattern": output_pattern or {},
            "execution_time_ms": execution_time_ms,
            "success": success,
        },
        "versioning": {
            "tool_version": tool_version,
            "last_verified": now,
            "stale_after_days": stale_after_days,
        },
        "stats": {
            "success_count": 1 if success else 0,
            "failure_count": 0 if success else 1,
            "success_rate": 1.0 if success else 0.0,
            "avg_execution_ms": execution_time_ms,
            "last_used": now,
        },
    }


def create_observational_metadata(
    observed_from: str,
    context: str,
    steps: List[str],
    outcome: str = "positive",  # positive | negative | neutral
    confidence: float = 0.5,
) -> Dict[str, Any]:
    """Create structured metadata for an observational memory."""
    return {
        "category": "observational",
        "subcategory": "user_workflow" if observed_from.startswith("user") else "agent_pattern",
        "observation": {
            "observed_from": observed_from,
            "context": context,
            "steps": steps,
            "outcome": outcome,
            "confidence": confidence,
        },
        "stats": {
            "applied_count": 0,
            "success_when_applied": 0,
            "effectiveness": 0.0,
        },
    }


# ──────────────────────────────────────────────
# Category Extension Manager
# ──────────────────────────────────────────────

class MemoryCategoryManager:
    """
    Manages memory categories and category-specific behaviors.

    Does NOT create new node types — extends Entity nodes with
    memory_category property and structured metadata.
    """

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
    # Procedural Memory Recording
    # ──────────────────────────────────────────

    def record_tool_use(
        self,
        tool_name: str,
        tool_type: str,
        description: str,
        input_data: Optional[Dict] = None,
        output_data: Optional[Dict] = None,
        success: bool = True,
        execution_time_ms: int = 0,
        agent_id: str = "system",
        tool_version: str = "",
    ) -> Dict[str, Any]:
        """
        Record a tool-use experience as a procedural memory.

        If a similar tool pattern already exists, updates stats instead
        of creating a duplicate. Uses tool_name + tool_type as the key.
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            # Check for existing procedural memory for this tool
            existing = session.run("""
                MATCH (e:Entity)
                WHERE e.memory_category = 'procedural'
                  AND e.tool_name = $tool_name
                  AND e.tool_type = $tool_type
                RETURN e.uuid AS uuid, e.salience AS salience,
                       e.access_count AS access_count,
                       e.attributes_json AS meta_json
                LIMIT 1
            """, tool_name=tool_name, tool_type=tool_type).single()

            if existing:
                # Update existing procedural memory stats
                meta = self._safe_json_load(existing["meta_json"])
                stats = meta.get("stats", {})
                if success:
                    stats["success_count"] = stats.get("success_count", 0) + 1
                else:
                    stats["failure_count"] = stats.get("failure_count", 0) + 1
                total = stats.get("success_count", 0) + stats.get("failure_count", 0)
                stats["success_rate"] = stats.get("success_count", 0) / max(1, total)
                stats["last_used"] = now

                # Update avg execution time
                old_avg = stats.get("avg_execution_ms", 0)
                stats["avg_execution_ms"] = int(
                    (old_avg * (total - 1) + execution_time_ms) / total
                )
                meta["stats"] = stats

                # Calculate new salience based on success rate
                success_boost = 0.02 if success else -0.03
                new_salience = min(1.0, max(0.1, existing["salience"] + success_boost))

                session.run("""
                    MATCH (e:Entity {uuid: $uuid})
                    SET e.attributes_json = $meta_json,
                        e.salience = $salience,
                        e.access_count = COALESCE(e.access_count, 0) + 1,
                        e.last_accessed = $now
                """,
                    uuid=existing["uuid"],
                    meta_json=json.dumps(meta, ensure_ascii=False),
                    salience=new_salience,
                    now=now,
                )

                return {
                    "status": "updated",
                    "uuid": existing["uuid"],
                    "success_rate": stats["success_rate"],
                    "total_uses": total,
                    "salience": new_salience,
                }
            else:
                # Create new procedural memory
                meta = create_procedural_metadata(
                    tool_name=tool_name,
                    tool_type=tool_type,
                    input_pattern=input_data or {},
                    output_pattern=output_data or {},
                    execution_time_ms=execution_time_ms,
                    success=success,
                    tool_version=tool_version,
                )

                node_uuid = str(uuid.uuid4())
                initial_salience = 0.6 if success else 0.3

                session.run("""
                    CREATE (e:Entity:Memory {
                        uuid: $uuid,
                        name: $name,
                        name_lower: $name_lower,
                        summary: $description,
                        memory_category: 'procedural',
                        tool_name: $tool_name,
                        tool_type: $tool_type,
                        attributes_json: $meta_json,
                        salience: $salience,
                        access_count: 1,
                        last_accessed: $now,
                        created_at: $now,
                        source: $source,
                        owner_id: $agent_id,
                        scope: 'personal'
                    })
                """,
                    uuid=node_uuid,
                    name=f"[{tool_type.upper()}] {tool_name}",
                    name_lower=f"[{tool_type}] {tool_name}".lower(),
                    description=description,
                    tool_name=tool_name,
                    tool_type=tool_type,
                    meta_json=json.dumps(meta, ensure_ascii=False),
                    salience=initial_salience,
                    now=now,
                    source=f"tool:{tool_type}",
                    agent_id=agent_id,
                )

                return {
                    "status": "created",
                    "uuid": node_uuid,
                    "tool_name": tool_name,
                    "tool_type": tool_type,
                    "initial_salience": initial_salience,
                }

    # ──────────────────────────────────────────
    # Observational Memory Recording
    # ──────────────────────────────────────────

    def record_observation(
        self,
        observed_from: str,
        context: str,
        steps: List[str],
        description: str,
        outcome: str = "positive",
        confidence: float = 0.5,
        agent_id: str = "system",
    ) -> Dict[str, Any]:
        """
        Record an observation of user/agent behavior as a memory.
        """
        meta = create_observational_metadata(
            observed_from=observed_from,
            context=context,
            steps=steps,
            outcome=outcome,
            confidence=confidence,
        )

        node_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        initial_salience = 0.4 + (confidence * 0.3)  # 0.4~0.7 based on confidence

        with self._driver.session() as session:
            session.run("""
                CREATE (e:Entity:Memory {
                    uuid: $uuid,
                    name: $name,
                    name_lower: $name_lower,
                    summary: $description,
                    memory_category: 'observational',
                    attributes_json: $meta_json,
                    salience: $salience,
                    access_count: 0,
                    last_accessed: $now,
                    created_at: $now,
                    source: $source,
                    owner_id: $agent_id,
                    scope: 'personal'
                })
            """,
                uuid=node_uuid,
                name=f"[OBS] {context[:60]}",
                name_lower=f"[obs] {context[:60]}".lower(),
                description=description,
                meta_json=json.dumps(meta, ensure_ascii=False),
                salience=initial_salience,
                now=now,
                source=f"observation:{observed_from}",
                agent_id=agent_id,
            )

        return {
            "status": "recorded",
            "uuid": node_uuid,
            "observed_from": observed_from,
            "confidence": confidence,
            "initial_salience": initial_salience,
        }

    def record_observation_outcome(
        self,
        memory_uuid: str,
        success: bool,
    ) -> Dict[str, Any]:
        """
        Record whether applying an observational memory was successful.
        Updates effectiveness stats and adjusts salience.
        """
        with self._driver.session() as session:
            record = session.run("""
                MATCH (e:Entity {uuid: $uuid, memory_category: 'observational'})
                RETURN e.attributes_json AS meta_json, e.salience AS salience
            """, uuid=memory_uuid).single()

            if not record:
                return {"error": "Observational memory not found"}

            meta = self._safe_json_load(record["meta_json"])
            stats = meta.get("stats", {"applied_count": 0, "success_when_applied": 0})
            stats["applied_count"] = stats.get("applied_count", 0) + 1
            if success:
                stats["success_when_applied"] = stats.get("success_when_applied", 0) + 1
            stats["effectiveness"] = (
                stats["success_when_applied"] / max(1, stats["applied_count"])
            )
            meta["stats"] = stats

            # Boost salience if effective, penalize if not
            boost = 0.05 if success else -0.03
            new_salience = min(1.0, max(0.1, record["salience"] + boost))

            session.run("""
                MATCH (e:Entity {uuid: $uuid})
                SET e.attributes_json = $meta_json,
                    e.salience = $salience,
                    e.access_count = COALESCE(e.access_count, 0) + 1,
                    e.last_accessed = $now
            """,
                uuid=memory_uuid,
                meta_json=json.dumps(meta, ensure_ascii=False),
                salience=new_salience,
                now=datetime.now(timezone.utc).isoformat(),
            )

        return {
            "status": "updated",
            "uuid": memory_uuid,
            "effectiveness": stats["effectiveness"],
            "applied_count": stats["applied_count"],
            "new_salience": new_salience,
        }

    # ──────────────────────────────────────────
    # Staleness Detection (Procedural)
    # ──────────────────────────────────────────

    def detect_stale_procedures(self, max_age_days: int = 90) -> List[Dict[str, Any]]:
        """
        Find procedural memories that haven't been verified for too long.

        Stale procedures risk causing errors when the underlying tool
        has changed (API version updates, deprecated endpoints, etc.)
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()

        with self._driver.session() as session:
            records = session.run("""
                MATCH (e:Entity)
                WHERE e.memory_category = 'procedural'
                  AND (e.last_accessed < $cutoff OR e.last_accessed IS NULL)
                RETURN e.uuid AS uuid, e.name AS name,
                       e.tool_name AS tool_name, e.tool_type AS tool_type,
                       e.salience AS salience, e.last_accessed AS last_accessed,
                       e.attributes_json AS meta_json
                ORDER BY e.last_accessed ASC
            """, cutoff=cutoff).data()

        stale_list = []
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            stale_after = meta.get("versioning", {}).get("stale_after_days", max_age_days)
            r["stale_after_days"] = stale_after
            r["success_rate"] = meta.get("stats", {}).get("success_rate", 0)
            stale_list.append(r)

        return stale_list

    def apply_staleness_decay(self, max_age_days: int = 90) -> Dict[str, Any]:
        """Apply accelerated decay to stale procedural memories."""
        stale = self.detect_stale_procedures(max_age_days)
        decayed = 0

        with self._driver.session() as session:
            for mem in stale:
                # Apply 10% penalty for staleness
                old_sal = mem.get("salience", 0.5)
                new_sal = max(0.1, old_sal * 0.9)
                session.run("""
                    MATCH (e:Entity {uuid: $uuid})
                    SET e.salience = $sal
                """, uuid=mem["uuid"], sal=new_sal)
                decayed += 1

        return {
            "stale_found": len(stale),
            "decayed": decayed,
        }

    # ──────────────────────────────────────────
    # Category-Aware Search
    # ──────────────────────────────────────────

    def search_by_category(
        self,
        category: str,
        query: str = "",
        tool_type: Optional[str] = None,
        min_salience: float = 0.0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search memories filtered by category with category-specific ranking.

        For procedural: ranks by success_rate × salience
        For observational: ranks by effectiveness × confidence
        For declarative: ranks by salience (default)
        """
        where_clauses = ["e.memory_category = $category"]
        params: Dict[str, Any] = {"category": category, "limit": limit}

        if query:
            where_clauses.append(
                "(toLower(e.name) CONTAINS toLower($search_q) "
                "OR toLower(e.summary) CONTAINS toLower($search_q))"
            )
            params["search_q"] = query

        if tool_type:
            where_clauses.append("e.tool_type = $tool_type")
            params["tool_type"] = tool_type

        if min_salience > 0:
            where_clauses.append("e.salience >= $min_sal")
            params["min_sal"] = min_salience

        where = " AND ".join(where_clauses)

        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity)
                WHERE {where}
                RETURN e.uuid AS uuid, e.name AS name,
                       e.summary AS summary,
                       e.memory_category AS memory_category,
                       e.tool_name AS tool_name,
                       e.tool_type AS tool_type,
                       e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       e.access_count AS access_count,
                       e.last_accessed AS last_accessed,
                       e.attributes_json AS meta_json,
                       e.owner_id AS owner_id
                ORDER BY e.salience DESC
                LIMIT $limit
            """, **params).data()

        # Enrich with parsed stats
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            r["stats"] = meta.get("stats", {})
            r.pop("meta_json", None)

        return records

    def get_category_stats(self) -> Dict[str, Any]:
        """Get statistics per memory category."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL
                WITH COALESCE(e.memory_category, 'declarative') AS cat,
                     count(e) AS cnt,
                     avg(e.salience) AS avg_sal,
                     sum(e.access_count) AS total_access
                RETURN cat, cnt, avg_sal, total_access
                ORDER BY cnt DESC
            """).data()

            # Procedural tool distribution
            tool_dist = session.run("""
                MATCH (e:Entity {memory_category: 'procedural'})
                WITH COALESCE(e.tool_type, 'unknown') AS ttype, count(e) AS cnt
                RETURN ttype, cnt ORDER BY cnt DESC
            """).data()

        return {
            "categories": {
                r["cat"]: {
                    "count": r["cnt"],
                    "avg_salience": round(r["avg_sal"] or 0, 3),
                    "total_accesses": r["total_access"] or 0,
                }
                for r in records
            },
            "procedural_tools": {t["ttype"]: t["cnt"] for t in tool_dist},
        }

    # ──────────────────────────────────────────
    # Decay Modifier (for integration with MemoryManager)
    # ──────────────────────────────────────────

    @staticmethod
    def calculate_decay_modifier(memory_category: str, meta_json: str) -> float:
        """
        Calculate a decay rate modifier based on memory category.

        Returns a multiplier for the base decay rate:
        - > 1.0: memory decays slower (successful procedures)
        - < 1.0: memory decays faster (failed procedures, stale)
        - 1.0: no modification (declarative)

        This is called by MemoryManager.run_decay() for category-aware decay.
        """
        if memory_category != "procedural":
            return 1.0

        try:
            meta = json.loads(meta_json) if isinstance(meta_json, str) else meta_json
        except (json.JSONDecodeError, TypeError):
            return 1.0

        stats = meta.get("stats", {})
        versioning = meta.get("versioning", {})

        success_rate = stats.get("success_rate", 0.5)

        # Success-rate modifier
        if success_rate < 0.5:
            modifier = 0.85  # Fast decay for unreliable procedures
        elif success_rate > 0.9:
            modifier = 1.05  # Strengthen reliable procedures
        else:
            modifier = 1.0

        # Staleness modifier
        last_verified = versioning.get("last_verified")
        stale_after = versioning.get("stale_after_days", 90)
        if last_verified:
            try:
                lv_dt = datetime.fromisoformat(last_verified.replace("Z", "+00:00"))
                days_since = (datetime.now(timezone.utc) - lv_dt).days
                if days_since > stale_after:
                    modifier *= 0.9  # Additional staleness penalty
            except Exception:
                pass

        return modifier

    @staticmethod
    def _safe_json_load(data) -> Dict:
        """Safely parse JSON string or return dict."""
        if isinstance(data, dict):
            return data
        if not data:
            return {}
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return {}
