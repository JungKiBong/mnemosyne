"""
Permanent Memory Manager — Phase 16: Immutable Memory, Imprinting & Priority

Implements three types of permanent (non-decaying, immutable) memory:
  1. Imprint — admin-injected foundational memories for agents
  2. Frozen LTM — long-term memories locked against decay/modification
  3. Inherited — permanent memories cascaded from higher scopes

Priority Resolution Engine:
  - Scope-based default priority (Global=1000 > Social=800 > Tribal=600 > Personal=400)
  - Admin pin (locked priority override)
  - Agent interaction weight (accumulated through usage)
  - Override monitoring & alerting

Memory Categories (Category Extension Pattern):
  - declarative — factual/semantic knowledge (existing)
  - procedural — tool-use patterns (API, MCP, code, shell)
  - observational — learned from observing users/agents
"""

import logging
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.permanent_memory')


# ──────────────────────────────────────────────
# Enums & Constants
# ──────────────────────────────────────────────

class PMCategory(Enum):
    IMPRINT = "imprint"
    FROZEN_LTM = "frozen_ltm"
    INHERITED = "inherited"


class MemoryCategory(Enum):
    """Content category — orthogonal to STM/LTM/PM lifecycle."""
    DECLARATIVE = "declarative"
    PROCEDURAL = "procedural"
    OBSERVATIONAL = "observational"


# Scope-based default priority scores
SCOPE_BASE_PRIORITY = {
    "global": 1000,
    "social": 800,
    "tribal": 600,
    "personal": 400,
}


class PermanentMemoryManager:
    """
    Core engine for permanent (immutable) memory management.

    PermanentMemory nodes are never decayed, cannot be modified after creation
    (except by admin unfreeze), and carry priority weights for resolution.
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

        self._ensure_schema()

    def close(self):
        if self._owns_driver:
            self._driver.close()

    # ──────────────────────────────────────────
    # Schema
    # ──────────────────────────────────────────

    def _ensure_schema(self):
        """Create PermanentMemory node schema and indexes."""
        queries = [
            "CREATE CONSTRAINT pm_uuid_uniq IF NOT EXISTS "
            "FOR (pm:PermanentMemory) REQUIRE pm.uuid IS UNIQUE",
            "CREATE INDEX pm_scope IF NOT EXISTS "
            "FOR (pm:PermanentMemory) ON (pm.scope)",
            "CREATE INDEX pm_category IF NOT EXISTS "
            "FOR (pm:PermanentMemory) ON (pm.category)",
            "CREATE INDEX pm_priority IF NOT EXISTS "
            "FOR (pm:PermanentMemory) ON (pm.priority)",
            # Memory category index on Entity for procedural/observational
            "CREATE INDEX entity_mem_category IF NOT EXISTS "
            "FOR (n:Entity) ON (n.memory_category)",
            # Priority override event index
            "CREATE INDEX override_time IF NOT EXISTS "
            "FOR (o:PriorityOverride) ON (o.created_at)",
        ]
        with self._driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.debug(f"PM schema warning: {e}")
        logger.info("PermanentMemory schema initialized")

    # ──────────────────────────────────────────
    # 1. Imprint (각인) Operations
    # ──────────────────────────────────────────

    def create_imprint(
        self,
        content: str,
        scope: str = "global",
        tags: Optional[List[str]] = None,
        created_by: str = "admin",
        reason: str = "",
        memory_category: str = "declarative",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create an imprint — an immutable foundational memory.

        Imprints are admin-created permanent memories that agents inherit.
        They never decay and cannot be modified after creation.
        """
        pm_uuid = f"pm-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        base_priority = SCOPE_BASE_PRIORITY.get(scope, 400)

        with self._driver.session() as session:
            session.run("""
                CREATE (pm:PermanentMemory {
                    uuid: $uuid,
                    content: $content,
                    category: 'imprint',
                    scope: $scope,
                    priority: $priority,
                    priority_locked: false,
                    parent_pm_uuid: null,
                    origin_scope: $scope,
                    created_by: $created_by,
                    created_at: $now,
                    reason: $reason,
                    source_memory_uuid: null,
                    tags: $tags,
                    immutable: true,
                    salience: 1.0,
                    decay_rate: 1.0,
                    access_count: 0,
                    memory_category: $mem_cat,
                    metadata_json: $meta_json
                })
            """,
                uuid=pm_uuid,
                content=content,
                scope=scope,
                priority=base_priority,
                created_by=created_by,
                now=now,
                reason=reason or "Admin imprint",
                tags=tags or [],
                mem_cat=memory_category,
                meta_json=json.dumps(metadata or {}, ensure_ascii=False),
            )

            # Record audit
            self._record_pm_audit(session, pm_uuid, "create_imprint",
                                  created_by, f"Imprint created: {content[:60]}")

        logger.info(f"Imprint created: {pm_uuid} scope={scope} by={created_by}")
        return {
            "status": "created",
            "uuid": pm_uuid,
            "content": content,
            "category": "imprint",
            "scope": scope,
            "priority": base_priority,
            "memory_category": memory_category,
        }

    def list_imprints(
        self,
        scope: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List imprints, optionally filtered by scope or tags."""
        where_clauses = ["pm.category = 'imprint'"]
        params: Dict[str, Any] = {"limit": limit}

        if scope:
            where_clauses.append("pm.scope = $scope")
            params["scope"] = scope
        if tags:
            where_clauses.append("ANY(t IN $tags WHERE t IN pm.tags)")
            params["tags"] = tags

        where = " AND ".join(where_clauses)

        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (pm:PermanentMemory)
                WHERE {where}
                RETURN pm.uuid AS uuid, pm.content AS content,
                       pm.scope AS scope, pm.priority AS priority,
                       pm.priority_locked AS priority_locked,
                       pm.tags AS tags, pm.created_by AS created_by,
                       pm.created_at AS created_at, pm.reason AS reason,
                       pm.memory_category AS memory_category,
                       pm.access_count AS access_count
                ORDER BY pm.priority DESC, pm.created_at ASC
                LIMIT $limit
            """, **params).data()

        return records

    def delete_imprint(self, pm_uuid: str, deleted_by: str = "admin") -> Dict[str, Any]:
        """
        Delete an imprint (admin-only). Also removes inheritance relationships.
        """
        with self._driver.session() as session:
            # Verify exists and is imprint
            existing = session.run("""
                MATCH (pm:PermanentMemory {uuid: $uuid, category: 'imprint'})
                RETURN pm.content AS content, pm.scope AS scope
            """, uuid=pm_uuid).single()

            if not existing:
                return {"error": "Imprint not found"}

            # Remove all IMPRINTED and INHERITED_FROM relationships
            session.run("""
                MATCH (pm:PermanentMemory {uuid: $uuid})
                OPTIONAL MATCH (pm)<-[r1:IMPRINTED]-()
                OPTIONAL MATCH (child:PermanentMemory)-[r2:INHERITED_FROM]->(pm)
                DELETE r1, r2
                WITH pm, collect(child.uuid) AS children
                DETACH DELETE pm
                RETURN children
            """, uuid=pm_uuid)

            self._record_pm_audit(session, pm_uuid, "delete_imprint",
                                  deleted_by, f"Imprint deleted: {existing['content'][:60]}")

        logger.info(f"Imprint deleted: {pm_uuid} by={deleted_by}")
        return {"status": "deleted", "uuid": pm_uuid}

    # ──────────────────────────────────────────
    # 2. Freeze / Unfreeze LTM
    # ──────────────────────────────────────────

    def freeze_memory(
        self,
        memory_uuid: str,
        reason: str = "",
        frozen_by: str = "admin",
    ) -> Dict[str, Any]:
        """
        Freeze an existing LTM memory → PermanentMemory.

        The original Entity is preserved; a PermanentMemory node is created
        with FROZEN_AS relationship. The original Entity gets immutable=true
        to prevent decay.
        """
        pm_uuid = f"pm-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            # Get source memory
            source = session.run("""
                MATCH (e:Entity {uuid: $uuid})
                WHERE e.salience IS NOT NULL
                RETURN e.uuid AS uuid, e.name AS name,
                       COALESCE(e.summary, '') AS summary,
                       COALESCE(e.scope, 'personal') AS scope,
                       e.salience AS salience,
                       COALESCE(e.memory_category, 'declarative') AS memory_category,
                       COALESCE(e.attributes_json, '{}') AS meta_json
            """, uuid=memory_uuid).single()

            if not source:
                return {"error": "Memory not found"}

            scope = source["scope"]
            base_priority = SCOPE_BASE_PRIORITY.get(scope, 400)

            # Create PermanentMemory node
            session.run("""
                CREATE (pm:PermanentMemory {
                    uuid: $pm_uuid,
                    content: $content,
                    category: 'frozen_ltm',
                    scope: $scope,
                    priority: $priority,
                    priority_locked: false,
                    parent_pm_uuid: null,
                    origin_scope: $scope,
                    created_by: $frozen_by,
                    created_at: $now,
                    reason: $reason,
                    source_memory_uuid: $source_uuid,
                    tags: [],
                    immutable: true,
                    salience: 1.0,
                    decay_rate: 1.0,
                    access_count: 0,
                    memory_category: $mem_cat,
                    metadata_json: $meta_json
                })
            """,
                pm_uuid=pm_uuid,
                content=f"{source['name']}: {source['summary']}" if source['summary'] else source['name'],
                scope=scope,
                priority=base_priority,
                frozen_by=frozen_by,
                now=now,
                reason=reason or "Frozen by admin",
                source_uuid=memory_uuid,
                mem_cat=source["memory_category"],
                meta_json=source["meta_json"],
            )

            # Create FROZEN_AS relationship
            session.run("""
                MATCH (e:Entity {uuid: $source_uuid})
                MATCH (pm:PermanentMemory {uuid: $pm_uuid})
                CREATE (e)-[:FROZEN_AS {at: $now, by: $frozen_by}]->(pm)
            """, source_uuid=memory_uuid, pm_uuid=pm_uuid, now=now, frozen_by=frozen_by)

            # Mark original Entity as immutable (skip in decay)
            session.run("""
                MATCH (e:Entity {uuid: $uuid})
                SET e.immutable = true, e.salience = 1.0, e.decay_rate = 1.0
            """, uuid=memory_uuid)

            self._record_pm_audit(session, pm_uuid, "freeze",
                                  frozen_by, f"Frozen: {source['name']}")

        logger.info(f"Memory frozen: {memory_uuid} → {pm_uuid}")
        return {
            "status": "frozen",
            "pm_uuid": pm_uuid,
            "source_uuid": memory_uuid,
            "source_name": source["name"],
            "scope": scope,
            "priority": base_priority,
        }

    def unfreeze_memory(
        self,
        pm_uuid: str,
        unfrozen_by: str = "admin",
    ) -> Dict[str, Any]:
        """
        Unfreeze a frozen LTM — restore it to normal decay behavior.
        Admin-only operation.
        """
        with self._driver.session() as session:
            pm = session.run("""
                MATCH (pm:PermanentMemory {uuid: $uuid, category: 'frozen_ltm'})
                RETURN pm.source_memory_uuid AS source_uuid, pm.content AS content
            """, uuid=pm_uuid).single()

            if not pm:
                return {"error": "Frozen memory not found"}

            # Restore original Entity to normal decay
            if pm["source_uuid"]:
                session.run("""
                    MATCH (e:Entity {uuid: $uuid})
                    SET e.immutable = false, e.decay_rate = null
                """, uuid=pm["source_uuid"])

            # Remove PM node and relationships
            session.run("""
                MATCH (pm:PermanentMemory {uuid: $uuid})
                DETACH DELETE pm
            """, uuid=pm_uuid)

            self._record_pm_audit(session, pm_uuid, "unfreeze",
                                  unfrozen_by, f"Unfrozen: {pm['content'][:60]}")

        logger.info(f"Memory unfrozen: {pm_uuid}")
        return {"status": "unfrozen", "pm_uuid": pm_uuid, "source_uuid": pm["source_uuid"]}

    def list_frozen(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all frozen memories."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (pm:PermanentMemory {category: 'frozen_ltm'})
                OPTIONAL MATCH (e:Entity)-[:FROZEN_AS]->(pm)
                RETURN pm.uuid AS uuid, pm.content AS content,
                       pm.scope AS scope, pm.priority AS priority,
                       pm.source_memory_uuid AS source_uuid,
                       pm.created_by AS frozen_by, pm.created_at AS frozen_at,
                       pm.reason AS reason, pm.memory_category AS memory_category,
                       e.name AS source_name, e.salience AS source_salience
                ORDER BY pm.created_at DESC
                LIMIT $limit
            """, limit=limit).data()
        return records

    # ──────────────────────────────────────────
    # 3. Inheritance Chain
    # ──────────────────────────────────────────

    def inherit_for_agent(
        self,
        agent_id: str,
        scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Inherit permanent memories for an agent from higher scopes.

        Default behavior:
        - Global scope PMs → always inherited
        - Social scope PMs → inherited if agent is in the organization
        - Tribal scope PMs → inherited if agent is in the team

        Returns list of newly inherited PM UUIDs.
        """
        target_scopes = scopes or ["global", "social", "tribal"]
        now = datetime.now(timezone.utc).isoformat()
        inherited = []

        with self._driver.session() as session:
            # Find PMs in target scopes that agent hasn't inherited yet
            records = session.run("""
                MATCH (pm:PermanentMemory)
                WHERE pm.scope IN $scopes
                  AND pm.category IN ['imprint', 'frozen_ltm']
                  AND NOT EXISTS {
                    MATCH (a:Agent {agent_id: $agent_id})-[:IMPRINTED]->(pm)
                  }
                RETURN pm.uuid AS uuid, pm.content AS content,
                       pm.scope AS scope, pm.priority AS priority,
                       pm.category AS category,
                       pm.memory_category AS memory_category
                ORDER BY pm.priority DESC
            """, scopes=target_scopes, agent_id=agent_id).data()

            for pm_rec in records:
                # Create IMPRINTED relationship
                session.run("""
                    MATCH (a:Agent {agent_id: $agent_id})
                    MATCH (pm:PermanentMemory {uuid: $pm_uuid})
                    MERGE (a)-[:IMPRINTED {at: $now, scope: $scope}]->(pm)
                """,
                    agent_id=agent_id,
                    pm_uuid=pm_rec["uuid"],
                    now=now,
                    scope=pm_rec["scope"],
                )
                inherited.append(pm_rec)

            self._record_pm_audit(
                session, f"agent:{agent_id}", "inherit",
                "system", f"Inherited {len(inherited)} PMs from {target_scopes}")

        logger.info(f"Agent {agent_id[:8]} inherited {len(inherited)} permanent memories")
        return {
            "status": "inherited",
            "agent_id": agent_id,
            "inherited_count": len(inherited),
            "inherited": inherited,
        }

    def get_inheritance_chain(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get all permanent memories inherited by an agent, ordered by priority."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (a:Agent {agent_id: $agent_id})-[r:IMPRINTED]->(pm:PermanentMemory)
                RETURN pm.uuid AS uuid, pm.content AS content,
                       pm.scope AS scope, pm.priority AS priority,
                       pm.priority_locked AS priority_locked,
                       pm.category AS category, pm.tags AS tags,
                       pm.memory_category AS memory_category,
                       pm.created_by AS created_by,
                       r.at AS inherited_at
                ORDER BY pm.priority DESC
            """, agent_id=agent_id).data()
        return records

    def sync_inheritance(self, agent_id: str) -> Dict[str, Any]:
        """
        Sync an agent's inherited PMs with current upstream state.

        Detects:
        - New PMs added to higher scopes → auto-inherit
        - Removed PMs → mark with alert
        - Priority changes → generate override alerts
        """
        now = datetime.now(timezone.utc).isoformat()
        changes = {"new": [], "removed": [], "priority_changed": []}

        with self._driver.session() as session:
            # Find new PMs in agent's subscribed scopes
            new_pms = session.run("""
                MATCH (a:Agent {agent_id: $agent_id})
                WITH a, COALESCE(a.subscribed_scopes, ['personal']) AS sub_scopes
                MATCH (pm:PermanentMemory)
                WHERE pm.scope IN sub_scopes + ['global']
                  AND pm.category IN ['imprint', 'frozen_ltm']
                  AND NOT (a)-[:IMPRINTED]->(pm)
                RETURN pm.uuid AS uuid, pm.content AS content,
                       pm.scope AS scope, pm.priority AS priority
            """, agent_id=agent_id).data()

            for pm in new_pms:
                session.run("""
                    MATCH (a:Agent {agent_id: $agent_id})
                    MATCH (pm:PermanentMemory {uuid: $pm_uuid})
                    CREATE (a)-[:IMPRINTED {at: $now, scope: $scope, via: 'sync'}]->(pm)
                """, agent_id=agent_id, pm_uuid=pm["uuid"], now=now, scope=pm["scope"])
                changes["new"].append(pm)

            if changes["new"]:
                self._record_pm_audit(
                    session, f"agent:{agent_id}", "sync_inherit",
                    "system", f"Synced {len(changes['new'])} new PMs")

        return {
            "agent_id": agent_id,
            "synced_at": now,
            "changes": changes,
            "new_count": len(changes["new"]),
        }

    # ──────────────────────────────────────────
    # 4. Priority Resolution Engine
    # ──────────────────────────────────────────

    def get_priority_stack(
        self,
        agent_id: str,
        include_ltm: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get the full priority-resolved memory stack for an agent.

        Returns permanent memories + optionally high-salience LTM,
        sorted by effective priority (scope base + agent weight + pin).
        """
        with self._driver.session() as session:
            # Get inherited PMs with agent-specific weights
            pm_records = session.run("""
                MATCH (a:Agent {agent_id: $agent_id})-[r:IMPRINTED]->(pm:PermanentMemory)
                OPTIONAL MATCH (a)-[ov:PRIORITY_OVERRIDE]->(pm)
                WITH pm, r, ov
                ORDER BY ov.created_at DESC
                WITH pm, r, head(collect(ov)) AS latest_override
                RETURN pm.uuid AS uuid, pm.content AS content,
                       pm.scope AS scope, pm.category AS category,
                       pm.priority AS base_priority,
                       pm.priority_locked AS priority_locked,
                       pm.tags AS tags,
                       pm.memory_category AS memory_category,
                       pm.access_count AS access_count,
                       COALESCE(latest_override.new_priority, pm.priority) AS effective_priority,
                       latest_override.override_type AS override_type,
                       latest_override.reason AS override_reason
                ORDER BY
                    CASE WHEN pm.priority_locked = true THEN 0 ELSE 1 END,
                    COALESCE(latest_override.new_priority, pm.priority) DESC
            """, agent_id=agent_id).data()

            stack = pm_records

            # Optionally include high-salience LTM
            if include_ltm:
                ltm_records = session.run("""
                    MATCH (e:Entity)
                    WHERE e.salience >= 0.8
                      AND e.immutable IS NULL OR e.immutable = false
                      AND (e.owner_id = $agent_id OR e.scope IN ['global', 'social'])
                    RETURN e.uuid AS uuid, e.name AS content,
                           COALESCE(e.scope, 'personal') AS scope,
                           'ltm' AS category,
                           e.salience * 400 AS base_priority,
                           false AS priority_locked,
                           [] AS tags,
                           COALESCE(e.memory_category, 'declarative') AS memory_category,
                           e.access_count AS access_count,
                           e.salience * 400 AS effective_priority,
                           null AS override_type,
                           null AS override_reason
                    ORDER BY e.salience DESC
                    LIMIT 20
                """, agent_id=agent_id).data()
                stack.extend(ltm_records)

        # Sort by effective_priority descending
        stack.sort(key=lambda x: x.get("effective_priority", 0), reverse=True)
        return stack

    def adjust_priority(
        self,
        pm_uuid: str,
        agent_id: str,
        delta: float,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Adjust priority of a PM for a specific agent via interaction weight.

        This creates a PriorityOverride event and checks if the adjustment
        causes a lower-scope memory to override a higher-scope one.
        """
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            pm = session.run("""
                MATCH (pm:PermanentMemory {uuid: $uuid})
                RETURN pm.priority AS priority, pm.priority_locked AS locked,
                       pm.scope AS scope, pm.content AS content
            """, uuid=pm_uuid).single()

            if not pm:
                return {"error": "Permanent memory not found"}
            if pm["locked"]:
                return {"error": "Priority is admin-locked", "uuid": pm_uuid}

            old_priority = pm["priority"]
            new_priority = max(0, old_priority + delta)

            # Create PriorityOverride event
            override_id = str(uuid.uuid4())
            session.run("""
                MATCH (a:Agent {agent_id: $agent_id})
                MATCH (pm:PermanentMemory {uuid: $pm_uuid})
                CREATE (a)-[:PRIORITY_OVERRIDE]->(ov:PriorityOverride {
                    uuid: $ov_id,
                    pm_uuid: $pm_uuid,
                    old_priority: $old_p,
                    new_priority: $new_p,
                    delta: $delta,
                    override_type: 'agent_weight',
                    reason: $reason,
                    agent_id: $agent_id,
                    scope: $scope,
                    created_at: $now
                })
                CREATE (ov)-[:OVERRIDES]->(pm)
            """,
                agent_id=agent_id, pm_uuid=pm_uuid,
                ov_id=override_id, old_p=old_priority, new_p=new_priority,
                delta=delta, reason=reason or "Agent interaction weight",
                scope=pm["scope"], now=now,
            )

            # Detect scope violation (lower scope overriding higher)
            alert = self._check_scope_violation(session, agent_id, pm_uuid, new_priority)

        result = {
            "status": "adjusted",
            "uuid": pm_uuid,
            "old_priority": old_priority,
            "new_priority": new_priority,
            "delta": delta,
            "agent_id": agent_id,
        }
        if alert:
            result["alert"] = alert
        return result

    def pin_priority(
        self,
        pm_uuid: str,
        priority: int,
        pinned_by: str = "admin",
    ) -> Dict[str, Any]:
        """Admin-lock a priority value. Agent adjustments are blocked."""
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            result = session.run("""
                MATCH (pm:PermanentMemory {uuid: $uuid})
                SET pm.priority = $priority,
                    pm.priority_locked = true,
                    pm.priority_locked_by = $by,
                    pm.priority_locked_at = $now
                RETURN pm.uuid AS uuid, pm.content AS content, pm.scope AS scope
            """, uuid=pm_uuid, priority=priority, by=pinned_by, now=now).single()

            if not result:
                return {"error": "Permanent memory not found"}

            self._record_pm_audit(session, pm_uuid, "pin_priority",
                                  pinned_by, f"Priority pinned to {priority}")

        return {
            "status": "pinned",
            "uuid": pm_uuid,
            "priority": priority,
            "locked_by": pinned_by,
        }

    def unpin_priority(self, pm_uuid: str, unpinned_by: str = "admin") -> Dict[str, Any]:
        """Remove admin priority lock."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (pm:PermanentMemory {uuid: $uuid})
                SET pm.priority_locked = false,
                    pm.priority_locked_by = null,
                    pm.priority_locked_at = null
                RETURN pm.uuid AS uuid, pm.scope AS scope
            """, uuid=pm_uuid).single()

            if not result:
                return {"error": "Permanent memory not found"}

            # Reset priority to scope default
            base = SCOPE_BASE_PRIORITY.get(result["scope"], 400)
            session.run("""
                MATCH (pm:PermanentMemory {uuid: $uuid})
                SET pm.priority = $base
            """, uuid=pm_uuid, base=base)

        return {"status": "unpinned", "uuid": pm_uuid, "reset_priority": base}

    # ──────────────────────────────────────────
    # 5. Override Monitoring & Alerts
    # ──────────────────────────────────────────

    def detect_priority_overrides(
        self,
        agent_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Detect cases where lower-scope memories override higher-scope ones.

        A scope violation occurs when, for a given agent, a personal PM has
        higher effective priority than a global/social PM.
        """
        with self._driver.session() as session:
            agent_filter = ""
            params: Dict[str, Any] = {"limit": limit}
            if agent_id:
                agent_filter = "AND ov.agent_id = $agent_id"
                params["agent_id"] = agent_id

            records = session.run(f"""
                MATCH (ov:PriorityOverride)-[:OVERRIDES]->(pm:PermanentMemory)
                WHERE ov.new_priority > pm.priority {agent_filter}
                OPTIONAL MATCH (a:Agent {{agent_id: ov.agent_id}})
                RETURN ov.uuid AS override_id,
                       ov.agent_id AS agent_id,
                       a.name AS agent_name,
                       ov.pm_uuid AS pm_uuid,
                       pm.content AS pm_content,
                       pm.scope AS pm_scope,
                       ov.old_priority AS old_priority,
                       ov.new_priority AS new_priority,
                       ov.delta AS delta,
                       ov.reason AS reason,
                       ov.override_type AS override_type,
                       ov.created_at AS created_at
                ORDER BY ov.created_at DESC
                LIMIT $limit
            """, **params).data()

        return records

    def get_override_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get unacknowledged priority override alerts for the admin dashboard.

        Alerts are generated when:
        1. A lower-scope PM overrides a higher-scope PM for any agent
        2. Agent weight pushes priority above a pinned value
        3. Inheritance sync detects upstream changes
        """
        with self._driver.session() as session:
            records = session.run("""
                MATCH (ov:PriorityOverride)-[:OVERRIDES]->(pm:PermanentMemory)
                WHERE ov.acknowledged IS NULL OR ov.acknowledged = false
                OPTIONAL MATCH (a:Agent {agent_id: ov.agent_id})
                WITH ov, pm, a,
                     CASE
                         WHEN pm.scope = 'global' AND ov.new_priority > 1000 THEN 'critical'
                         WHEN pm.scope = 'social' AND ov.new_priority > 800 THEN 'warning'
                         ELSE 'info'
                     END AS severity
                WHERE severity IN ['critical', 'warning']
                RETURN ov.uuid AS alert_id,
                       severity,
                       ov.agent_id AS agent_id,
                       a.name AS agent_name,
                       pm.uuid AS pm_uuid,
                       pm.content AS pm_content,
                       pm.scope AS scope,
                       ov.old_priority AS old_priority,
                       ov.new_priority AS new_priority,
                       ov.reason AS reason,
                       ov.created_at AS created_at
                ORDER BY
                    CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                    ov.created_at DESC
                LIMIT $limit
            """, limit=limit).data()
        return records

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "admin") -> Dict[str, Any]:
        """Mark an override alert as acknowledged."""
        now = datetime.now(timezone.utc).isoformat()
        with self._driver.session() as session:
            result = session.run("""
                MATCH (ov:PriorityOverride {uuid: $uuid})
                SET ov.acknowledged = true,
                    ov.acknowledged_by = $by,
                    ov.acknowledged_at = $now
                RETURN ov.uuid AS uuid
            """, uuid=alert_id, by=acknowledged_by, now=now).single()

            if not result:
                return {"error": "Alert not found"}
        return {"status": "acknowledged", "alert_id": alert_id}

    # ──────────────────────────────────────────
    # 6. Statistics & Dashboard Data
    # ──────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive PM statistics for dashboard."""
        with self._driver.session() as session:
            # Total counts by category
            by_category = session.run("""
                MATCH (pm:PermanentMemory)
                WITH pm.category AS cat, count(pm) AS cnt
                RETURN cat, cnt ORDER BY cnt DESC
            """).data()

            # By scope
            by_scope = session.run("""
                MATCH (pm:PermanentMemory)
                WITH pm.scope AS scope, count(pm) AS cnt,
                     avg(pm.priority) AS avg_priority
                RETURN scope, cnt, avg_priority ORDER BY cnt DESC
            """).data()

            # By memory_category
            by_mem_cat = session.run("""
                MATCH (pm:PermanentMemory)
                WITH COALESCE(pm.memory_category, 'declarative') AS mem_cat,
                     count(pm) AS cnt
                RETURN mem_cat, cnt ORDER BY cnt DESC
            """).data()

            # Locked priorities
            locked = session.run("""
                MATCH (pm:PermanentMemory {priority_locked: true})
                RETURN count(pm) AS cnt
            """).single()

            # Active overrides (unacknowledged)
            alerts = session.run("""
                MATCH (ov:PriorityOverride)
                WHERE ov.acknowledged IS NULL OR ov.acknowledged = false
                RETURN count(ov) AS cnt
            """).single()

            # Inheritance coverage
            inheritance = session.run("""
                MATCH (a:Agent)
                OPTIONAL MATCH (a)-[r:IMPRINTED]->(pm:PermanentMemory)
                WITH a.agent_id AS agent_id, a.name AS name,
                     count(pm) AS pm_count
                RETURN agent_id, name, pm_count
                ORDER BY pm_count DESC
            """).data()

            # Immutable Entity count (frozen originals)
            frozen_entities = session.run("""
                MATCH (e:Entity {immutable: true})
                RETURN count(e) AS cnt
            """).single()

        return {
            "total_permanent": sum(c["cnt"] for c in by_category),
            "by_category": {c["cat"]: c["cnt"] for c in by_category},
            "by_scope": {
                s["scope"]: {"count": s["cnt"], "avg_priority": round(s["avg_priority"] or 0, 1)}
                for s in by_scope
            },
            "by_memory_category": {m["mem_cat"]: m["cnt"] for m in by_mem_cat},
            "locked_count": locked["cnt"] if locked else 0,
            "active_alerts": alerts["cnt"] if alerts else 0,
            "frozen_entities": frozen_entities["cnt"] if frozen_entities else 0,
            "agent_inheritance": inheritance,
        }

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Combined dashboard payload with stats + recent alerts + top PMs."""
        stats = self.get_stats()
        alerts = self.get_override_alerts(limit=10)
        top_imprints = self.list_imprints(limit=10)
        frozen = self.list_frozen(limit=10)

        return {
            "stats": stats,
            "alerts": alerts,
            "top_imprints": top_imprints,
            "recent_frozen": frozen,
        }

    # ──────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────

    def _check_scope_violation(
        self, session, agent_id: str, pm_uuid: str, new_priority: float
    ) -> Optional[Dict[str, Any]]:
        """Check if a priority change causes a scope hierarchy violation."""
        result = session.run("""
            MATCH (pm:PermanentMemory {uuid: $pm_uuid})
            WITH pm,
                 CASE pm.scope
                     WHEN 'personal' THEN 0
                     WHEN 'tribal' THEN 1
                     WHEN 'social' THEN 2
                     WHEN 'global' THEN 3
                 END AS scope_rank
            MATCH (a:Agent {agent_id: $agent_id})-[:IMPRINTED]->(higher:PermanentMemory)
            WHERE CASE higher.scope
                      WHEN 'personal' THEN 0
                      WHEN 'tribal' THEN 1
                      WHEN 'social' THEN 2
                      WHEN 'global' THEN 3
                  END > scope_rank
              AND higher.priority < $new_priority
            RETURN higher.uuid AS higher_uuid, higher.scope AS higher_scope,
                   higher.priority AS higher_priority, higher.content AS higher_content
            LIMIT 1
        """, pm_uuid=pm_uuid, agent_id=agent_id, new_priority=new_priority).single()

        if result:
            alert = {
                "type": "scope_violation",
                "message": f"Lower-scope PM overrides {result['higher_scope']} PM",
                "overridden_uuid": result["higher_uuid"],
                "overridden_scope": result["higher_scope"],
                "overridden_priority": result["higher_priority"],
                "new_priority": new_priority,
            }
            logger.warning(f"Scope violation detected: {alert}")
            return alert
        return None

    def _record_pm_audit(self, session, target: str, action: str,
                         actor: str, detail: str):
        """Record an audit event for permanent memory operations."""
        try:
            session.run("""
                CREATE (a:PMAudit {
                    uuid: $uuid,
                    target: $target,
                    action: $action,
                    actor: $actor,
                    detail: $detail,
                    created_at: $now
                })
            """,
                uuid=str(uuid.uuid4()),
                target=target,
                action=action,
                actor=actor,
                detail=detail,
                now=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            logger.debug(f"PM audit record failed: {e}")
