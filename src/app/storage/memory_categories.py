"""
Memory Category Extension — Phase 16-C+: Cognitive Memory Categories

Extends the memory system with content categories without changing the core architecture.
Uses the "Category Extension Pattern" — same STM/LTM/PM lifecycle, different metadata schemas.

Categories (8 total):
  - declarative: Factual knowledge (existing, default)
  - procedural: Tool-use patterns (API calls, MCP tools, code, shell commands)
  - observational: Learned from observing users or other agents
  - preference: User/agent preferences that persist across sessions
  - instructional: Behavioral rules and constraints ("always do X")
  - reflective: Self-improvement lessons from past errors/successes
  - conditional: Context-dependent knowledge (if-then rules)
  - orchestration: Multi-agent task coordination memory

Key features:
  - Success-rate based decay modifier for procedural memories
  - Staleness detection for tool memories (API version changes)
  - Observation confidence tracking
  - Category-aware search filtering
  - Auto-PM promotion for must-priority instructional rules
  - Occurrence-based reinforcement for reflective memories
  - Context-matching for conditional knowledge retrieval
  - Multi-agent task handoff, escalation, and checkpoint tracking
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
# Preference Memory Schema
# ──────────────────────────────────────────────

def create_preference_metadata(
    key: str,
    value: str,
    subcategory: str = "general",  # communication | coding_style | workflow | ui | general
    confidence: float = 0.8,
    context: str = "conversation",
) -> Dict[str, Any]:
    """Create structured metadata for a preference memory."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "category": "preference",
        "subcategory": subcategory,
        "preference": {
            "key": key,
            "value": value,
            "confidence": confidence,
            "last_expressed": now,
            "expression_count": 1,
            "context": context,
        },
    }


# ──────────────────────────────────────────────
# Instructional Memory Schema
# ──────────────────────────────────────────────

def create_instructional_metadata(
    rule: str,
    trigger: str = "always",  # always | pre_commit | pre_code | pre_deploy | on_error
    priority: str = "should",  # must | should | may
    subcategory: str = "workflow",  # coding | workflow | communication | security
    source_agent: str = "user",
) -> Dict[str, Any]:
    """Create structured metadata for an instructional memory."""
    return {
        "category": "instructional",
        "subcategory": subcategory,
        "instruction": {
            "rule": rule,
            "trigger": trigger,
            "priority": priority,
            "source_agent": source_agent,
            "active": True,
            "supersedes": None,
        },
        "stats": {
            "applied_count": 0,
            "compliance_rate": 1.0,
        },
    }


# ──────────────────────────────────────────────
# Reflective Memory Schema
# ──────────────────────────────────────────────

def create_reflective_metadata(
    event: str,
    lesson: str,
    severity: str = "medium",  # high | medium | low
    domain: str = "general",
    subcategory: str = "lesson_learned",  # error_pattern | success_pattern | lesson_learned
) -> Dict[str, Any]:
    """Create structured metadata for a reflective memory."""
    return {
        "category": "reflective",
        "subcategory": subcategory,
        "reflection": {
            "event": event,
            "lesson": lesson,
            "severity": severity,
            "domain": domain,
            "occurrence_count": 1,
            "last_occurred": datetime.now(timezone.utc).isoformat(),
        },
        "stats": {
            "prevented_count": 0,
            "referenced_count": 0,
        },
    }


# ──────────────────────────────────────────────
# Conditional Memory Schema
# ──────────────────────────────────────────────

def create_conditional_metadata(
    condition: Dict[str, Any],
    then_action: str,
    else_action: Optional[str] = None,
    subcategory: str = "contextual",  # version_specific | env_specific | temporal | contextual
    confidence: float = 0.9,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None,
) -> Dict[str, Any]:
    """Create structured metadata for a conditional memory."""
    return {
        "category": "conditional",
        "subcategory": subcategory,
        "condition": {
            "if": condition,
            "then": then_action,
            "else": else_action,
            "confidence": confidence,
            "valid_from": valid_from,
            "valid_until": valid_until,
        },
    }


# ──────────────────────────────────────────────
# Orchestration Memory Schema (Multi-Agent)
# ──────────────────────────────────────────────

def create_orchestration_metadata(
    task_id: str,
    task_type: str = "handoff",  # handoff | delegation | coordination | escalation | checkpoint
    from_agent: str = "system",
    to_agent: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    status: str = "pending",  # pending | in_progress | completed | failed | escalated
    parent_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create structured metadata for multi-agent orchestration memory."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "category": "orchestration",
        "subcategory": task_type,
        "task": {
            "task_id": task_id,
            "task_type": task_type,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "status": status,
            "parent_task_id": parent_task_id,
            "context": context or {},
            "created_at": now,
            "updated_at": now,
        },
        "stats": {
            "handoff_count": 0,
            "escalation_count": 0,
            "avg_resolution_ms": 0,
        },
    }


# ──────────────────────────────────────────────
# Harness Memory Schema (Evolutionary Process Patterns)
# ──────────────────────────────────────────────

def _tool_chain_hash(tool_chain: List[Dict[str, Any]]) -> str:
    """Compute a stable hash of a tool chain for version comparison."""
    import hashlib
    canonical = json.dumps(
        [{"tool": t.get("tool"), "order": t.get("order")} for t in tool_chain],
        sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def create_harness_metadata(
    domain: str,
    trigger: str,
    tool_chain: List[Dict[str, Any]],
    process_type: str = "pipeline",  # pipeline | fan_out | expert_pool | producer_reviewer | supervisor | hierarchical
    data_flow: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    source_agent: str = "user",
    auto_extracted: bool = False,
    extraction_confidence: float = 1.0,
    source_log_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create structured metadata for a harness (evolutionary process pattern) memory."""
    now = datetime.now(timezone.utc).isoformat()
    chain_hash = _tool_chain_hash(tool_chain)
    return {
        "category": "harness",
        "harness": {
            "domain": domain,
            "trigger": trigger,
            "process_type": process_type,
            "tool_chain": tool_chain,
            "data_flow": data_flow or {"input": "", "intermediate": [], "output": ""},
            "tags": tags or [],
        },
        "stats": {
            "execution_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "avg_execution_time_ms": 0,
            "last_executed": None,
        },
        "evolution": {
            "current_version": 1,
            "history": [
                {
                    "version": 1,
                    "created_at": now,
                    "tool_chain_hash": chain_hash,
                    "success_rate": 0.0,
                    "change_reason": "initial",
                }
            ],
        },
        "extraction": {
            "auto_extracted": auto_extracted,
            "source_log_ids": source_log_ids or [],
            "extraction_confidence": extraction_confidence,
            "user_verified": not auto_extracted,
            "source_agent": source_agent,
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
    # Preference Memory
    # ──────────────────────────────────────────

    def record_preference(
        self,
        key: str,
        value: str,
        description: str = "",
        subcategory: str = "general",
        confidence: float = 0.8,
        context: str = "conversation",
        agent_id: str = "system",
    ) -> Dict[str, Any]:
        """Record a user/agent preference. Upserts if key already exists."""
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            existing = session.run("""
                MATCH (e:Entity)
                WHERE e.memory_category = 'preference'
                  AND e.preference_key = $key
                  AND e.owner_id = $agent_id
                RETURN e.uuid AS uuid, e.attributes_json AS meta_json,
                       e.salience AS salience
                LIMIT 1
            """, key=key, agent_id=agent_id).single()

            if existing:
                meta = self._safe_json_load(existing["meta_json"])
                pref = meta.get("preference", {})
                pref["value"] = value
                pref["confidence"] = max(pref.get("confidence", 0), confidence)
                pref["expression_count"] = pref.get("expression_count", 0) + 1
                pref["last_expressed"] = now
                meta["preference"] = pref

                new_sal = min(1.0, existing["salience"] + 0.02)
                session.run("""
                    MATCH (e:Entity {uuid: $uuid})
                    SET e.attributes_json = $meta_json,
                        e.summary = $desc,
                        e.salience = $sal,
                        e.last_accessed = $now
                """, uuid=existing["uuid"],
                    meta_json=json.dumps(meta, ensure_ascii=False),
                    desc=description or f"{key} = {value}",
                    sal=new_sal, now=now)

                return {"status": "updated", "uuid": existing["uuid"],
                        "key": key, "value": value,
                        "expression_count": pref["expression_count"]}
            else:
                meta = create_preference_metadata(
                    key=key, value=value, subcategory=subcategory,
                    confidence=confidence, context=context)
                node_uuid = str(uuid.uuid4())
                initial_salience = 0.7 + (confidence * 0.2)

                session.run("""
                    CREATE (e:Entity:Memory {
                        uuid: $uuid,
                        name: $name, name_lower: $name_lower,
                        summary: $desc,
                        memory_category: 'preference',
                        preference_key: $key,
                        attributes_json: $meta_json,
                        salience: $sal,
                        access_count: 1, last_accessed: $now,
                        created_at: $now, owner_id: $agent_id,
                        scope: 'personal'
                    })
                """, uuid=node_uuid, name=f"[PREF] {key}",
                    name_lower=f"[pref] {key}".lower(),
                    desc=description or f"{key} = {value}",
                    key=key,
                    meta_json=json.dumps(meta, ensure_ascii=False),
                    sal=initial_salience, now=now, agent_id=agent_id)

                return {"status": "created", "uuid": node_uuid,
                        "key": key, "value": value,
                        "initial_salience": initial_salience}

    def recall_preferences(
        self,
        key: Optional[str] = None,
        subcategory: Optional[str] = None,
        agent_id: str = "system",
    ) -> List[Dict[str, Any]]:
        """Recall stored preferences. Used at session start."""
        clauses = ["e.memory_category = 'preference'"]
        params: Dict[str, Any] = {}
        if key:
            clauses.append("e.preference_key = $key")
            params["key"] = key
        if agent_id != "all":
            clauses.append("e.owner_id = $agent_id")
            params["agent_id"] = agent_id

        where = " AND ".join(clauses)
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity) WHERE {where}
                RETURN e.uuid AS uuid, e.preference_key AS key,
                       e.summary AS value_desc, e.salience AS salience,
                       e.attributes_json AS meta_json
                ORDER BY e.salience DESC
            """, **params).data()

        results = []
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            pref = meta.get("preference", {})
            results.append({
                "uuid": r["uuid"], "key": r["key"],
                "value": pref.get("value", r.get("value_desc", "")),
                "confidence": pref.get("confidence", 0),
                "expression_count": pref.get("expression_count", 0),
                "salience": r["salience"],
            })
        return results

    # ──────────────────────────────────────────
    # Instructional Memory
    # ──────────────────────────────────────────

    def record_instruction(
        self,
        rule: str,
        description: str = "",
        trigger: str = "always",
        priority: str = "should",
        subcategory: str = "workflow",
        source_agent: str = "user",
        agent_id: str = "system",
    ) -> Dict[str, Any]:
        """Record a behavioral instruction/rule. Must-priority auto-promotes to PM."""
        meta = create_instructional_metadata(
            rule=rule, trigger=trigger, priority=priority,
            subcategory=subcategory, source_agent=source_agent)
        node_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        initial_salience = {"must": 0.95, "should": 0.8, "may": 0.6}.get(priority, 0.7)

        with self._driver.session() as session:
            session.run("""
                CREATE (e:Entity:Memory {
                    uuid: $uuid,
                    name: $name, name_lower: $name_lower,
                    summary: $desc,
                    memory_category: 'instructional',
                    instruction_trigger: $trigger,
                    instruction_priority: $priority,
                    attributes_json: $meta_json,
                    salience: $sal,
                    access_count: 0, last_accessed: $now,
                    created_at: $now, owner_id: $agent_id,
                    scope: 'personal'
                })
            """, uuid=node_uuid, name=f"[RULE] {rule[:60]}",
                name_lower=f"[rule] {rule[:60]}".lower(),
                desc=description or rule,
                trigger=trigger, priority=priority,
                meta_json=json.dumps(meta, ensure_ascii=False),
                sal=initial_salience, now=now, agent_id=agent_id)

        result = {"status": "created", "uuid": node_uuid,
                  "rule": rule, "priority": priority, "trigger": trigger,
                  "initial_salience": initial_salience}

        # Auto-promote must-priority rules to PermanentMemory
        if priority == "must":
            try:
                from .permanent_memory import PermanentMemoryManager
                pm_mgr = PermanentMemoryManager(driver=self._driver)
                pm_result = pm_mgr.create_imprint(
                    content=f"[MUST RULE] {rule}",
                    scope="personal",
                    tags=["instructional", trigger, subcategory],
                    created_by=source_agent,
                    reason="Auto-promoted must-priority instruction",
                    memory_category="instructional",
                )
                result["auto_promoted_pm"] = pm_result.get("uuid")
                logger.info(f"Must-rule auto-promoted to PM: {pm_result.get('uuid')}")
            except Exception as e:
                logger.warning(f"PM auto-promote failed: {e}")

        return result

    def recall_instructions(
        self,
        trigger: Optional[str] = None,
        priority: Optional[str] = None,
        agent_id: str = "system",
    ) -> List[Dict[str, Any]]:
        """Recall active instructions. Used before task execution."""
        clauses = ["e.memory_category = 'instructional'"]
        params: Dict[str, Any] = {}
        if trigger:
            clauses.append("(e.instruction_trigger = $trigger OR e.instruction_trigger = 'always')")
            params["trigger"] = trigger
        if priority:
            clauses.append("e.instruction_priority = $priority")
            params["priority"] = priority
        if agent_id != "all":
            clauses.append("e.owner_id = $agent_id")
            params["agent_id"] = agent_id

        where = " AND ".join(clauses)
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity) WHERE {where}
                RETURN e.uuid AS uuid, e.summary AS rule,
                       e.instruction_trigger AS trigger,
                       e.instruction_priority AS priority,
                       e.salience AS salience,
                       e.attributes_json AS meta_json
                ORDER BY
                  CASE e.instruction_priority
                    WHEN 'must' THEN 0
                    WHEN 'should' THEN 1
                    WHEN 'may' THEN 2
                    ELSE 3
                  END,
                  e.salience DESC
            """, **params).data()

        results = []
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            inst = meta.get("instruction", {})
            if not inst.get("active", True):
                continue
            results.append({
                "uuid": r["uuid"], "rule": r["rule"],
                "trigger": r["trigger"], "priority": r["priority"],
                "salience": r["salience"],
                "compliance_rate": meta.get("stats", {}).get("compliance_rate", 1.0),
            })
        return results

    # ──────────────────────────────────────────
    # Reflective Memory
    # ──────────────────────────────────────────

    def record_reflection(
        self,
        event: str,
        lesson: str,
        description: str = "",
        severity: str = "medium",
        domain: str = "general",
        subcategory: str = "lesson_learned",
        agent_id: str = "system",
    ) -> Dict[str, Any]:
        """Record a self-reflection/lesson. Upserts if similar lesson exists."""
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            existing = session.run("""
                MATCH (e:Entity)
                WHERE e.memory_category = 'reflective'
                  AND e.reflection_domain = $domain
                  AND (toLower(e.summary) CONTAINS toLower($lesson_key)
                       OR toLower(e.name) CONTAINS toLower($lesson_key))
                RETURN e.uuid AS uuid, e.attributes_json AS meta_json,
                       e.salience AS salience
                LIMIT 1
            """, domain=domain, lesson_key=lesson[:40]).single()

            if existing:
                meta = self._safe_json_load(existing["meta_json"])
                refl = meta.get("reflection", {})
                refl["occurrence_count"] = refl.get("occurrence_count", 0) + 1
                refl["last_occurred"] = now
                if severity == "high":
                    refl["severity"] = "high"
                meta["reflection"] = refl

                new_sal = min(1.0, existing["salience"] + 0.05)
                session.run("""
                    MATCH (e:Entity {uuid: $uuid})
                    SET e.attributes_json = $meta_json,
                        e.salience = $sal,
                        e.last_accessed = $now
                """, uuid=existing["uuid"],
                    meta_json=json.dumps(meta, ensure_ascii=False),
                    sal=new_sal, now=now)

                return {"status": "reinforced", "uuid": existing["uuid"],
                        "occurrence_count": refl["occurrence_count"],
                        "new_salience": new_sal}
            else:
                meta = create_reflective_metadata(
                    event=event, lesson=lesson, severity=severity,
                    domain=domain, subcategory=subcategory)
                node_uuid = str(uuid.uuid4())
                initial_salience = {"high": 0.85, "medium": 0.65, "low": 0.45}.get(severity, 0.6)

                session.run("""
                    CREATE (e:Entity:Memory {
                        uuid: $uuid,
                        name: $name, name_lower: $name_lower,
                        summary: $desc,
                        memory_category: 'reflective',
                        reflection_domain: $domain,
                        reflection_severity: $severity,
                        attributes_json: $meta_json,
                        salience: $sal,
                        access_count: 0, last_accessed: $now,
                        created_at: $now, owner_id: $agent_id,
                        scope: 'personal'
                    })
                """, uuid=node_uuid,
                    name=f"[REFL] {lesson[:60]}",
                    name_lower=f"[refl] {lesson[:60]}".lower(),
                    desc=description or f"Event: {event}\nLesson: {lesson}",
                    domain=domain, severity=severity,
                    meta_json=json.dumps(meta, ensure_ascii=False),
                    sal=initial_salience, now=now, agent_id=agent_id)

                return {"status": "created", "uuid": node_uuid,
                        "lesson": lesson, "severity": severity,
                        "initial_salience": initial_salience}

    def recall_reflections(
        self,
        domain: Optional[str] = None,
        severity: Optional[str] = None,
        agent_id: str = "system",
    ) -> List[Dict[str, Any]]:
        """Recall reflections/lessons. Used before task execution."""
        clauses = ["e.memory_category = 'reflective'"]
        params: Dict[str, Any] = {}
        if domain:
            clauses.append("e.reflection_domain = $domain")
            params["domain"] = domain
        if severity:
            clauses.append("e.reflection_severity = $severity")
            params["severity"] = severity
        if agent_id != "all":
            clauses.append("e.owner_id = $agent_id")
            params["agent_id"] = agent_id

        where = " AND ".join(clauses)
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity) WHERE {where}
                RETURN e.uuid AS uuid, e.summary AS description,
                       e.reflection_domain AS domain,
                       e.reflection_severity AS severity,
                       e.salience AS salience,
                       e.attributes_json AS meta_json
                ORDER BY e.salience DESC LIMIT 20
            """, **params).data()

        results = []
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            refl = meta.get("reflection", {})
            results.append({
                "uuid": r["uuid"],
                "lesson": refl.get("lesson", r.get("description", "")),
                "event": refl.get("event", ""),
                "domain": r["domain"], "severity": r["severity"],
                "occurrence_count": refl.get("occurrence_count", 1),
                "salience": r["salience"],
            })
        return results

    # ──────────────────────────────────────────
    # Conditional Memory
    # ──────────────────────────────────────────

    def record_conditional(
        self,
        condition: Dict[str, Any],
        then_action: str,
        else_action: Optional[str] = None,
        description: str = "",
        subcategory: str = "contextual",
        confidence: float = 0.9,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        agent_id: str = "system",
    ) -> Dict[str, Any]:
        """Record a conditional knowledge rule."""
        meta = create_conditional_metadata(
            condition=condition, then_action=then_action,
            else_action=else_action, subcategory=subcategory,
            confidence=confidence, valid_from=valid_from, valid_until=valid_until)
        node_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        initial_salience = 0.6 + (confidence * 0.3)

        cond_summary = json.dumps(condition, ensure_ascii=False)
        auto_desc = description or f"IF {cond_summary} THEN {then_action}"

        with self._driver.session() as session:
            session.run("""
                CREATE (e:Entity:Memory {
                    uuid: $uuid,
                    name: $name, name_lower: $name_lower,
                    summary: $desc,
                    memory_category: 'conditional',
                    condition_subcategory: $sub,
                    attributes_json: $meta_json,
                    salience: $sal,
                    access_count: 0, last_accessed: $now,
                    created_at: $now, owner_id: $agent_id,
                    scope: 'personal'
                })
            """, uuid=node_uuid,
                name=f"[COND] {then_action[:50]}",
                name_lower=f"[cond] {then_action[:50]}".lower(),
                desc=auto_desc, sub=subcategory,
                meta_json=json.dumps(meta, ensure_ascii=False),
                sal=initial_salience, now=now, agent_id=agent_id)

        return {"status": "created", "uuid": node_uuid,
                "condition": condition, "then": then_action,
                "initial_salience": initial_salience}

    def recall_conditionals(
        self,
        context: Optional[Dict[str, Any]] = None,
        subcategory: Optional[str] = None,
        agent_id: str = "system",
    ) -> List[Dict[str, Any]]:
        """Recall conditional rules, optionally matching context."""
        clauses = ["e.memory_category = 'conditional'"]
        params: Dict[str, Any] = {}
        if subcategory:
            clauses.append("e.condition_subcategory = $sub")
            params["sub"] = subcategory
        if agent_id != "all":
            clauses.append("e.owner_id = $agent_id")
            params["agent_id"] = agent_id

        where = " AND ".join(clauses)
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity) WHERE {where}
                RETURN e.uuid AS uuid, e.summary AS description,
                       e.salience AS salience,
                       e.attributes_json AS meta_json
                ORDER BY e.salience DESC LIMIT 20
            """, **params).data()

        results = []
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            cond = meta.get("condition", {})

            # Skip expired conditionals
            valid_until = cond.get("valid_until")
            if valid_until:
                try:
                    if datetime.fromisoformat(valid_until.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                        continue
                except Exception:
                    pass

            # Context matching
            matched = True
            if context and cond.get("if"):
                cond_if = cond["if"]
                for ck, cv in cond_if.items():
                    ctx_val = context.get(ck)
                    if ctx_val is not None and str(ctx_val) != str(cv):
                        if isinstance(cv, str) and cv.startswith("<"):
                            try:
                                if float(str(ctx_val)) >= float(cv[1:]):
                                    matched = False
                            except ValueError:
                                matched = False
                        elif isinstance(cv, str) and cv.startswith(">"):
                            try:
                                if float(str(ctx_val)) <= float(cv[1:]):
                                    matched = False
                            except ValueError:
                                matched = False
                        else:
                            matched = False

            if not matched:
                continue

            results.append({
                "uuid": r["uuid"],
                "condition": cond.get("if", {}),
                "then": cond.get("then", ""),
                "else": cond.get("else"),
                "confidence": cond.get("confidence", 0),
                "salience": r["salience"],
            })
        return results

    # ──────────────────────────────────────────
    # Orchestration Memory (Multi-Agent)
    # ──────────────────────────────────────────

    def record_task_handoff(
        self,
        task_id: str,
        task_description: str,
        from_agent: str,
        to_agent: str,
        context: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
        task_type: str = "handoff",
    ) -> Dict[str, Any]:
        """Record a multi-agent task handoff/delegation."""
        meta = create_orchestration_metadata(
            task_id=task_id, task_type=task_type,
            from_agent=from_agent, to_agent=to_agent,
            context=context, status="pending",
            parent_task_id=parent_task_id)
        node_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            session.run("""
                CREATE (e:Entity:Memory {
                    uuid: $uuid,
                    name: $name, name_lower: $name_lower,
                    summary: $desc,
                    memory_category: 'orchestration',
                    task_id: $task_id,
                    task_status: 'pending',
                    task_from_agent: $from_agent,
                    task_to_agent: $to_agent,
                    attributes_json: $meta_json,
                    salience: 0.9,
                    access_count: 0, last_accessed: $now,
                    created_at: $now, owner_id: $from_agent,
                    scope: 'tribal'
                })
            """, uuid=node_uuid,
                name=f"[TASK] {task_description[:60]}",
                name_lower=f"[task] {task_description[:60]}".lower(),
                desc=task_description, task_id=task_id,
                from_agent=from_agent, to_agent=to_agent,
                meta_json=json.dumps(meta, ensure_ascii=False),
                now=now)

        logger.info(f"Task handoff: {task_id} {from_agent} -> {to_agent}")
        return {"status": "created", "uuid": node_uuid,
                "task_id": task_id, "from": from_agent, "to": to_agent}

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result_summary: Optional[str] = None,
        escalate_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update a task's status. Auto-generates reflection on failure."""
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            existing = session.run("""
                MATCH (e:Entity {task_id: $task_id, memory_category: 'orchestration'})
                RETURN e.uuid AS uuid, e.attributes_json AS meta_json,
                       e.task_status AS old_status
            """, task_id=task_id).single()

            if not existing:
                return {"error": f"Task {task_id} not found"}

            meta = self._safe_json_load(existing["meta_json"])
            task = meta.get("task", {})
            old_status = task.get("status", "pending")
            task["status"] = status
            task["updated_at"] = now
            if result_summary:
                task["result_summary"] = result_summary

            stats = meta.get("stats", {})
            if status == "escalated":
                stats["escalation_count"] = stats.get("escalation_count", 0) + 1
                if escalate_to:
                    task["to_agent"] = escalate_to

            meta["task"] = task
            meta["stats"] = stats

            sal = 0.9 if status in ("pending", "in_progress", "escalated") else 0.4

            session.run("""
                MATCH (e:Entity {uuid: $uuid})
                SET e.attributes_json = $meta_json,
                    e.task_status = $status,
                    e.salience = $sal,
                    e.last_accessed = $now
            """, uuid=existing["uuid"],
                meta_json=json.dumps(meta, ensure_ascii=False),
                status=status, sal=sal, now=now)

            # Auto-reflect on failure
            if status == "failed" and result_summary:
                try:
                    self.record_reflection(
                        event=f"Task {task_id} failed: {result_summary[:100]}",
                        lesson=f"Task failure in {task.get('task_type', 'unknown')}: review approach",
                        severity="medium",
                        domain="orchestration",
                        subcategory="error_pattern",
                        agent_id=task.get("from_agent", "system"),
                    )
                except Exception as e:
                    logger.debug(f"Auto-reflection on task failure skipped: {e}")

        return {"status": "updated", "task_id": task_id,
                "old_status": old_status, "new_status": status}

    def get_active_tasks(
        self,
        agent_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get active orchestration tasks for an agent or all agents."""
        clauses = ["e.memory_category = 'orchestration'",
                   "e.task_status IN ['pending', 'in_progress', 'escalated']"]
        params: Dict[str, Any] = {}
        if agent_id:
            clauses.append("(e.task_to_agent = $agent_id OR e.task_from_agent = $agent_id)")
            params["agent_id"] = agent_id

        where = " AND ".join(clauses)
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity) WHERE {where}
                RETURN e.uuid AS uuid, e.task_id AS task_id,
                       e.summary AS description, e.task_status AS status,
                       e.task_from_agent AS from_agent,
                       e.task_to_agent AS to_agent,
                       e.salience AS salience,
                       e.attributes_json AS meta_json
                ORDER BY e.salience DESC, e.created_at DESC
            """, **params).data()

        results = []
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            task = meta.get("task", {})
            results.append({
                "uuid": r["uuid"], "task_id": r["task_id"],
                "description": r["description"],
                "status": r["status"],
                "from_agent": r["from_agent"], "to_agent": r["to_agent"],
                "context": task.get("context", {}),
                "parent_task_id": task.get("parent_task_id"),
            })
        return results

    # ──────────────────────────────────────────
    # Harness Memory — Evolutionary Process Patterns
    # ──────────────────────────────────────────

    def record_harness(
        self,
        domain: str,
        trigger: str,
        tool_chain: List[Dict[str, Any]],
        description: str = "",
        process_type: str = "pipeline",
        data_flow: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        agent_id: str = "system",
        scope: str = "tribal",
    ) -> Dict[str, Any]:
        """Manually register a process pattern as a harness memory."""
        meta = create_harness_metadata(
            domain=domain, trigger=trigger, tool_chain=tool_chain,
            process_type=process_type, data_flow=data_flow, tags=tags,
            source_agent=agent_id, auto_extracted=False)
        node_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            session.run("""
                CREATE (e:Entity:Memory {
                    uuid: $uuid,
                    name: $name, name_lower: $name_lower,
                    summary: $desc,
                    memory_category: 'harness',
                    harness_domain: $domain,
                    harness_process_type: $process_type,
                    harness_version: 1,
                    attributes_json: $meta_json,
                    salience: 0.85,
                    access_count: 0, last_accessed: $now,
                    created_at: $now, owner_id: $agent_id,
                    scope: $scope
                })
            """, uuid=node_uuid,
                name=f"[HARNESS] {domain}: {trigger[:50]}",
                name_lower=f"[harness] {domain}: {trigger[:50]}".lower(),
                desc=description or f"Process pattern for {domain} triggered by: {trigger}",
                domain=domain, process_type=process_type,
                meta_json=json.dumps(meta, ensure_ascii=False),
                now=now, agent_id=agent_id, scope=scope)

        logger.info(f"Harness recorded: {domain}/{trigger} ({len(tool_chain)} tools)")
        return {"status": "created", "uuid": node_uuid, "domain": domain,
                "trigger": trigger, "tool_count": len(tool_chain), "version": 1}

    def extract_harness_from_log(
        self,
        execution_log: Dict[str, Any],
        domain: str = "general",
        agent_id: str = "system",
        min_tools: int = 2,
    ) -> Dict[str, Any]:
        """Auto-extract a harness pattern from an execution log with loop compression and conditional extraction.

        Expected log format:
        {
            "steps": [
                {"tool": "git_diff", "type": "shell", "input": "...", "output": "...", "success": true},
                {"tool": "llm_call", "type": "api", "input": "...", "output": "...", "success": false, "error": "timeout"},
                {"tool": "llm_call_fallback", "type": "api", "input": "...", "output": "...", "success": true}
            ],
            "trigger": "PR review request",
            "overall_success": true,
            "execution_time_ms": 4500
        }
        """
        steps = execution_log.get("steps", [])
        if len(steps) < min_tools:
            return {"status": "skipped", "reason": f"Only {len(steps)} tools < min {min_tools}"}

        # Build tool chain with loop compression (consecutive identical tools become 1 step with iteration_count)
        tool_chain = []
        last_tool = None
        for step in steps:
            tool_name = step.get("tool", "unknown")
            if tool_name == last_tool:
                tool_chain[-1]["iteration_count"] = tool_chain[-1].get("iteration_count", 1) + 1
            else:
                tool_chain.append({
                    "tool": tool_name,
                    "type": step.get("type", "unknown"),
                    "order": len(tool_chain) + 1,
                    "role": step.get("role", "processing"),
                    "iteration_count": 1
                })
            last_tool = tool_name

        # Extract potential conditional knowledge (fallback patterns from failures)
        extracted_conditionals = []
        for i in range(len(steps) - 1):
            if not steps[i].get("success", True):
                failed_tool = steps[i].get("tool", "unknown")
                error_msg = steps[i].get("error", "Unknown error")
                next_tool = steps[i+1].get("tool", "unknown")
                extracted_conditionals.append({
                    "condition": f"If tool '{failed_tool}' fails with '{error_msg}'",
                    "then_action": f"Fallback to using tool '{next_tool}'"
                })

        trigger = execution_log.get("trigger", "unknown")
        log_id = execution_log.get("log_id", str(uuid.uuid4())[:8])

        # Automatically record extracted conditionals
        for cond in extracted_conditionals:
            try:
                self.record_conditional(
                    condition=cond["condition"],
                    then_action=cond["then_action"],
                    description=f"Auto-extracted fallback from harness execution log {log_id}",
                    subcategory="contextual",
                    confidence=0.7,
                    agent_id=agent_id
                )
            except Exception as e:
                logger.warning(f"Failed to record conditional logic from log {log_id}: {e}")

        # Check for existing similar harness (same domain + similar compressed tool chain)
        existing = self._find_similar_harness(domain, tool_chain)
        if existing:
            # Merge: record as additional execution of existing harness
            merge_res = self.record_harness_execution(
                harness_uuid=existing["uuid"],
                success=execution_log.get("overall_success", True),
                execution_time_ms=execution_log.get("execution_time_ms", 0),
                result_summary=f"Auto-merged from log {log_id}. Detected conditionals: {len(extracted_conditionals)}",
            )
            # Annotate with conditionals extracted
            merge_res["extracted_conditionals"] = len(extracted_conditionals)
            return merge_res

        # Build richer data flow mapping from inputs and outputs
        data_flow = {
            "input": str(steps[0].get("input", ""))[:500] if steps else "",
            "intermediate": [str(s.get("output", ""))[:200] for s in steps[1:-1] if s.get("output")] if len(steps) > 2 else [],
            "output": str(steps[-1].get("output", ""))[:500] if steps else "",
            "error_paths_detected": len(extracted_conditionals) > 0
        }

        meta = create_harness_metadata(
            domain=domain, trigger=trigger, tool_chain=tool_chain,
            data_flow=data_flow, source_agent=agent_id,
            auto_extracted=True, extraction_confidence=0.75,
            source_log_ids=[log_id])

        # Record initial execution stats
        overall_success = execution_log.get("overall_success", True)
        meta["stats"]["execution_count"] = 1
        meta["stats"]["success_count"] = 1 if overall_success else 0
        meta["stats"]["failure_count"] = 0 if overall_success else 1
        meta["stats"]["success_rate"] = 1.0 if overall_success else 0.0
        meta["stats"]["avg_execution_time_ms"] = execution_log.get("execution_time_ms", 0)
        meta["stats"]["last_executed"] = datetime.now(timezone.utc).isoformat()
        if len(extracted_conditionals) > 0:
            meta["stats"]["resilience_score"] = 0.5  # Recovered from failure

        node_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            session.run("""
                CREATE (e:Entity:Memory {
                    uuid: $uuid,
                    name: $name, name_lower: $name_lower,
                    summary: $desc,
                    memory_category: 'harness',
                    harness_domain: $domain,
                    harness_process_type: 'pipeline',
                    harness_version: 1,
                    attributes_json: $meta_json,
                    salience: 0.7,
                    access_count: 0, last_accessed: $now,
                    created_at: $now, owner_id: $agent_id,
                    scope: 'tribal'
                })
            """, uuid=node_uuid,
                name=f"[HARNESS:AUTO] {domain}: {trigger[:50]}",
                name_lower=f"[harness:auto] {domain}: {trigger[:50]}".lower(),
                desc=f"Auto-extracted process pattern ({len(tool_chain)} tools) from log {log_id}",
                domain=domain,
                meta_json=json.dumps(meta, ensure_ascii=False),
                now=now, agent_id=agent_id)

        logger.info(f"Harness auto-extracted: {domain}/{trigger} ({len(tool_chain)} tools)")
        return {"status": "extracted", "uuid": node_uuid, "domain": domain,
                "trigger": trigger, "tool_count": len(tool_chain),
                "auto_extracted": True, "confidence": 0.7}

    def _find_similar_harness(
        self, domain: str, tool_chain: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find an existing harness with >= 70% tool overlap in the same domain."""
        new_tools = {t.get("tool") for t in tool_chain}
        if not new_tools:
            return None

        with self._driver.session() as session:
            records = session.run("""
                MATCH (e:Entity)
                WHERE e.memory_category = 'harness'
                  AND e.harness_domain = $domain
                RETURN e.uuid AS uuid, e.attributes_json AS meta_json
                ORDER BY e.salience DESC
                LIMIT 20
            """, domain=domain).data()

        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            existing_tools = {t.get("tool") for t in meta.get("harness", {}).get("tool_chain", [])}
            if not existing_tools:
                continue
            overlap = len(new_tools & existing_tools) / max(len(new_tools), len(existing_tools))
            if overlap >= 0.7:
                return {"uuid": r["uuid"], "overlap": overlap}
        return None

    def recall_harness(
        self,
        domain: Optional[str] = None,
        trigger: Optional[str] = None,
        tags: Optional[List[str]] = None,
        agent_id: str = "system",
        min_success_rate: float = 0.0,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Recall suitable harness patterns for a given domain/trigger."""
        clauses = ["e.memory_category = 'harness'"]
        params: Dict[str, Any] = {"limit": limit}

        if domain:
            clauses.append("e.harness_domain = $domain")
            params["domain"] = domain
        if trigger:
            clauses.append("(toLower(e.summary) CONTAINS toLower($trigger) OR toLower(e.name) CONTAINS toLower($trigger))")
            params["trigger"] = trigger
        if agent_id != "all":
            clauses.append("(e.owner_id = $agent_id OR e.scope IN ['tribal', 'global'])")
            params["agent_id"] = agent_id

        where = " AND ".join(clauses)
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity) WHERE {where}
                RETURN e.uuid AS uuid, e.name AS name,
                       e.summary AS description,
                       e.harness_domain AS domain,
                       e.harness_process_type AS process_type,
                       e.harness_version AS version,
                       e.salience AS salience,
                       e.owner_id AS owner_id,
                       e.scope AS scope,
                       e.attributes_json AS meta_json
                ORDER BY e.salience DESC, e.harness_version DESC
                LIMIT $limit
            """, **params).data()

        results = []
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            stats = meta.get("stats", {})
            sr = stats.get("success_rate", 0)
            if sr < min_success_rate:
                continue

            harness = meta.get("harness", {})
            evolution = meta.get("evolution", {})
            extraction = meta.get("extraction", {})

            # Filter by tags if specified
            if tags:
                harness_tags = set(harness.get("tags", []))
                if not harness_tags.intersection(set(tags)):
                    continue

            results.append({
                "uuid": r["uuid"],
                "name": r["name"],
                "description": r["description"],
                "domain": r["domain"],
                "process_type": r["process_type"],
                "version": r["version"],
                "salience": r["salience"],
                "owner_id": r["owner_id"],
                "scope": r["scope"],
                "tool_chain": harness.get("tool_chain", []),
                "data_flow": harness.get("data_flow", {}),
                "tags": harness.get("tags", []),
                "stats": stats,
                "current_version": evolution.get("current_version", 1),
                "auto_extracted": extraction.get("auto_extracted", False),
                "user_verified": extraction.get("user_verified", True),
            })

        # Boost salience on retrieval
        if results:
            uuids = [r["uuid"] for r in results]
            with self._driver.session() as session:
                session.run("""
                    UNWIND $uuids AS uid
                    MATCH (e:Entity {uuid: uid})
                    SET e.access_count = COALESCE(e.access_count, 0) + 1,
                        e.last_accessed = $now
                """, uuids=uuids, now=datetime.now(timezone.utc).isoformat())

        return results

    def record_harness_execution(
        self,
        harness_uuid: str,
        success: bool,
        execution_time_ms: int = 0,
        result_summary: str = "",
        new_tool_chain: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Record execution result and auto-evolve if tool chain changed."""
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            existing = session.run("""
                MATCH (e:Entity {uuid: $uuid, memory_category: 'harness'})
                RETURN e.uuid AS uuid, e.attributes_json AS meta_json,
                       e.harness_version AS version, e.salience AS salience
            """, uuid=harness_uuid).single()

            if not existing:
                return {"error": f"Harness {harness_uuid} not found"}

            meta = self._safe_json_load(existing["meta_json"])
            stats = meta.get("stats", {})

            # Update execution stats
            stats["execution_count"] = stats.get("execution_count", 0) + 1
            if success:
                stats["success_count"] = stats.get("success_count", 0) + 1
            else:
                stats["failure_count"] = stats.get("failure_count", 0) + 1

            total = stats["execution_count"]
            stats["success_rate"] = round(stats.get("success_count", 0) / max(total, 1), 3)

            # Rolling average execution time
            old_avg = stats.get("avg_execution_time_ms", 0)
            stats["avg_execution_time_ms"] = int((old_avg * (total - 1) + execution_time_ms) / total)
            stats["last_executed"] = now
            meta["stats"] = stats

            # Auto-evolve if new tool chain provided and different
            evolved = False
            if new_tool_chain:
                old_hash = _tool_chain_hash(meta.get("harness", {}).get("tool_chain", []))
                new_hash = _tool_chain_hash(new_tool_chain)
                if old_hash != new_hash:
                    evolution = meta.get("evolution", {"current_version": 1, "history": []})
                    new_version = evolution["current_version"] + 1
                    evolution["history"].append({
                        "version": new_version,
                        "created_at": now,
                        "tool_chain_hash": new_hash,
                        "success_rate": stats["success_rate"],
                        "change_reason": result_summary or "tool chain updated",
                    })
                    evolution["current_version"] = new_version
                    meta["evolution"] = evolution
                    meta["harness"]["tool_chain"] = new_tool_chain
                    evolved = True

            # Adjust salience based on success rate
            new_salience = min(0.99, 0.5 + stats["success_rate"] * 0.4)

            session.run("""
                MATCH (e:Entity {uuid: $uuid})
                SET e.attributes_json = $meta_json,
                    e.harness_version = $version,
                    e.salience = $sal,
                    e.last_accessed = $now,
                    e.access_count = COALESCE(e.access_count, 0) + 1
            """, uuid=harness_uuid,
                meta_json=json.dumps(meta, ensure_ascii=False),
                version=meta.get("evolution", {}).get("current_version", 1),
                sal=new_salience, now=now)

            # Auto-reflect on 3+ consecutive failures
            if not success and stats.get("failure_count", 0) >= 3 and stats["success_rate"] < 0.5:
                try:
                    domain = meta.get("harness", {}).get("domain", "unknown")
                    self.record_reflection(
                        event=f"Harness {domain} failure rate critical: {stats['success_rate']:.0%}",
                        lesson=f"Process pattern in {domain} needs revision — consider alternative tool chain",
                        severity="high",
                        domain=domain,
                        subcategory="process_failure",
                        agent_id=meta.get("extraction", {}).get("source_agent", "system"),
                    )
                except Exception as e:
                    logger.debug(f"Harness auto-reflection skipped: {e}")

        return {
            "status": "recorded",
            "uuid": harness_uuid,
            "success": success,
            "stats": stats,
            "evolved": evolved,
            "new_version": meta.get("evolution", {}).get("current_version", 1) if evolved else None,
        }

    def evolve_harness(
        self,
        harness_uuid: str,
        new_tool_chain: List[Dict[str, Any]],
        change_reason: str,
        new_data_flow: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Manually evolve a harness to a new version with an updated tool chain."""
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            existing = session.run("""
                MATCH (e:Entity {uuid: $uuid, memory_category: 'harness'})
                RETURN e.uuid AS uuid, e.attributes_json AS meta_json
            """, uuid=harness_uuid).single()

            if not existing:
                return {"error": f"Harness {harness_uuid} not found"}

            meta = self._safe_json_load(existing["meta_json"])
            new_hash = _tool_chain_hash(new_tool_chain)

            evolution = meta.get("evolution", {"current_version": 1, "history": []})
            new_version = evolution["current_version"] + 1
            evolution["history"].append({
                "version": new_version,
                "created_at": now,
                "tool_chain_hash": new_hash,
                "success_rate": meta.get("stats", {}).get("success_rate", 0),
                "change_reason": change_reason,
            })
            evolution["current_version"] = new_version
            meta["evolution"] = evolution
            meta["harness"]["tool_chain"] = new_tool_chain
            if new_data_flow:
                meta["harness"]["data_flow"] = new_data_flow

            # Mark user-verified on manual evolution
            meta["extraction"]["user_verified"] = True

            # Reset failure count on evolution (fresh start)
            meta["stats"]["failure_count"] = 0

            session.run("""
                MATCH (e:Entity {uuid: $uuid})
                SET e.attributes_json = $meta_json,
                    e.harness_version = $version,
                    e.last_accessed = $now
            """, uuid=harness_uuid,
                meta_json=json.dumps(meta, ensure_ascii=False),
                version=new_version, now=now)

        logger.info(f"Harness evolved to v{new_version}: {change_reason}")
        return {"status": "evolved", "uuid": harness_uuid,
                "new_version": new_version, "change_reason": change_reason}

    def list_harnesses(
        self,
        domain: Optional[str] = None,
        agent_id: str = "system",
        include_low_success: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all harness patterns, optionally filtered by domain."""
        clauses = ["e.memory_category = 'harness'"]
        params: Dict[str, Any] = {}

        if domain:
            clauses.append("e.harness_domain = $domain")
            params["domain"] = domain
        if agent_id != "all":
            clauses.append("(e.owner_id = $agent_id OR e.scope IN ['tribal', 'global'])")
            params["agent_id"] = agent_id

        where = " AND ".join(clauses)
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity) WHERE {where}
                RETURN e.uuid AS uuid, e.name AS name,
                       e.summary AS description,
                       e.harness_domain AS domain,
                       e.harness_process_type AS process_type,
                       e.harness_version AS version,
                       e.salience AS salience,
                       e.scope AS scope,
                       e.attributes_json AS meta_json
                ORDER BY e.salience DESC
            """, **params).data()

        results = []
        for r in records:
            meta = self._safe_json_load(r.get("meta_json", "{}"))
            stats = meta.get("stats", {})
            if not include_low_success and stats.get("success_rate", 0) < 0.3 and stats.get("execution_count", 0) > 5:
                continue
            harness = meta.get("harness", {})
            results.append({
                "uuid": r["uuid"],
                "name": r["name"],
                "domain": r["domain"],
                "process_type": r["process_type"],
                "version": r["version"],
                "trigger": harness.get("trigger", ""),
                "tool_count": len(harness.get("tool_chain", [])),
                "tags": harness.get("tags", []),
                "success_rate": stats.get("success_rate", 0),
                "execution_count": stats.get("execution_count", 0),
                "scope": r["scope"],
            })
        return results

    def compare_harness_versions(
        self,
        harness_uuid: str,
        version_a: Optional[int] = None,
        version_b: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Compare two versions of a harness's evolution history."""
        with self._driver.session() as session:
            existing = session.run("""
                MATCH (e:Entity {uuid: $uuid, memory_category: 'harness'})
                RETURN e.attributes_json AS meta_json,
                       e.harness_domain AS domain
            """, uuid=harness_uuid).single()

        if not existing:
            return {"error": f"Harness {harness_uuid} not found"}

        meta = self._safe_json_load(existing["meta_json"])
        evolution = meta.get("evolution", {})
        history = evolution.get("history", [])

        if len(history) < 2:
            return {"status": "no_history", "message": "Only 1 version exists",
                    "current": history[0] if history else {}}

        # Default: compare latest two versions
        if version_a is None:
            version_a = history[-2]["version"] if len(history) >= 2 else 1
        if version_b is None:
            version_b = history[-1]["version"]

        entry_a = next((h for h in history if h["version"] == version_a), None)
        entry_b = next((h for h in history if h["version"] == version_b), None)

        if not entry_a or not entry_b:
            return {"error": f"Version {version_a} or {version_b} not found"}

        improvement = (entry_b.get("success_rate", 0) - entry_a.get("success_rate", 0))
        return {
            "domain": existing["domain"],
            "version_a": entry_a,
            "version_b": entry_b,
            "success_rate_delta": round(improvement, 3),
            "improved": improvement > 0,
            "total_versions": len(history),
        }

    # ──────────────────────────────────────────
    # Decay Modifier (for integration with MemoryManager)
    # ──────────────────────────────────────────

    @staticmethod
    def calculate_decay_modifier(memory_category: str, meta_json: str) -> float:
        """
        Calculate a decay rate modifier based on memory category.

        Category-specific policies:
        - preference: Very slow decay (1.1)
        - instructional: No decay (1.0 fixed)
        - reflective: Proportional to occurrence_count
        - conditional: Expire after valid_until
        - orchestration: Fast decay for completed tasks
        - procedural: Success-rate based
        - declarative/observational: Default (1.0)
        """
        if memory_category in ('instructional',):
            return 1.0

        if memory_category == 'preference':
            return 1.1

        try:
            meta = json.loads(meta_json) if isinstance(meta_json, str) else meta_json
        except (json.JSONDecodeError, TypeError):
            return 1.0

        if memory_category == 'reflective':
            occ = meta.get("reflection", {}).get("occurrence_count", 1)
            return min(1.1, 1.0 + (occ * 0.02))

        if memory_category == 'conditional':
            valid_until = meta.get("condition", {}).get("valid_until")
            if valid_until:
                try:
                    vu = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) > vu:
                        return 0.5
                except Exception:
                    pass
            return 1.0

        if memory_category == 'orchestration':
            status = meta.get("task", {}).get("status", "pending")
            if status in ("completed", "failed"):
                return 0.7
            return 1.0

        if memory_category == 'harness':
            stats = meta.get("stats", {})
            extraction = meta.get("extraction", {})
            success_rate = stats.get("success_rate", 0.5)

            if success_rate > 0.8:
                modifier = 1.1
            elif success_rate < 0.5:
                modifier = 0.8
            else:
                modifier = 1.0

            # Stale harness penalty (30+ days unused)
            last_exec = stats.get("last_executed")
            if last_exec:
                try:
                    le_dt = datetime.fromisoformat(last_exec.replace("Z", "+00:00"))
                    days_since = (datetime.now(timezone.utc) - le_dt).days
                    if days_since > 30:
                        modifier *= 0.9
                except Exception:
                    pass

            # User-verified bonus
            if extraction.get("user_verified", False):
                modifier = min(1.15, modifier + 0.05)

            return modifier

        if memory_category == 'procedural':
            stats = meta.get("stats", {})
            versioning = meta.get("versioning", {})
            success_rate = stats.get("success_rate", 0.5)

            if success_rate < 0.5:
                modifier = 0.85
            elif success_rate > 0.9:
                modifier = 1.05
            else:
                modifier = 1.0

            last_verified = versioning.get("last_verified")
            stale_after = versioning.get("stale_after_days", 90)
            if last_verified:
                try:
                    lv_dt = datetime.fromisoformat(last_verified.replace("Z", "+00:00"))
                    days_since = (datetime.now(timezone.utc) - lv_dt).days
                    if days_since > stale_after:
                        modifier *= 0.9
                except Exception:
                    pass
            return modifier

        return 1.0

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
