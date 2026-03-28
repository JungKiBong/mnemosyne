"""
Memory Scopes — Phase 8: Hierarchical Memory Architecture

Implements 4-tier memory scope hierarchy:
  1. Personal — Individual agent/user memories (conversations, notes, code)
  2. Tribal — Team/project shared memories
  3. Social — Organization/community-wide patterns
  4. Global — Universal knowledge (no decay)

Each Entity node gains a `scope` property and `source_type` property.
Promotion rules govern how memories escalate across scopes.
"""

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.memory_scopes')


# ──────────────────────────────────────────
# Enums
# ──────────────────────────────────────────

class MemoryScope(Enum):
    PERSONAL = "personal"
    TRIBAL = "tribal"
    SOCIAL = "social"
    GLOBAL = "global"


class MemorySourceType(Enum):
    CONVERSATION = "conversation"
    DOCUMENT = "document"
    CODE = "code"
    NOTE = "note"
    OBSERVATION = "observation"
    SIMULATION = "simulation"
    EXTERNAL = "external"


# Scope hierarchy (lower index = lower tier)
SCOPE_HIERARCHY = [
    MemoryScope.PERSONAL,
    MemoryScope.TRIBAL,
    MemoryScope.SOCIAL,
    MemoryScope.GLOBAL,
]

# Scope-specific decay rates
SCOPE_DECAY_RATES = {
    MemoryScope.PERSONAL: 0.95,   # Fastest decay
    MemoryScope.TRIBAL: 0.98,     # Slower
    MemoryScope.SOCIAL: 0.99,     # Very slow
    MemoryScope.GLOBAL: 1.0,      # No decay
}

# Scope-specific promotion thresholds
SCOPE_PROMOTION_RULES = {
    MemoryScope.PERSONAL: {
        "min_salience": 0.8,
        "min_accessors": 2,        # How many distinct agents accessed
        "target": MemoryScope.TRIBAL,
    },
    MemoryScope.TRIBAL: {
        "min_salience": 0.85,
        "min_tribal_refs": 3,      # Referenced by 3+ tribal groups
        "target": MemoryScope.SOCIAL,
    },
    MemoryScope.SOCIAL: {
        "min_salience": 0.9,
        "requires_admin_approval": True,
        "target": MemoryScope.GLOBAL,
    },
}


class MemoryScopeManager:
    """
    Manages hierarchical memory scopes and promotions.

    Each memory has a `scope` that determines:
    - Who can access it (visibility)
    - How fast it decays (decay rate override)
    - Conditions for promotion to next tier
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

        self._ensure_scope_schema()

    def close(self):
        if self._owns_driver:
            self._driver.close()

    # ──────────────────────────────────────────
    # Schema
    # ──────────────────────────────────────────

    def _ensure_scope_schema(self):
        """Add scope and source_type to existing entities."""
        queries = [
            # Default scope for existing entities
            """
            MATCH (n:Entity) WHERE n.scope IS NULL
            SET n.scope = 'personal'
            """,
            # Default source_type
            """
            MATCH (n:Entity) WHERE n.source_type IS NULL
            SET n.source_type = CASE
                WHEN n.promoted_from_stm = true THEN 'observation'
                ELSE 'document'
            END
            """,
            # Add owner_id (which agent/user owns this memory)
            """
            MATCH (n:Entity) WHERE n.owner_id IS NULL
            SET n.owner_id = 'system'
            """,
            # Index on scope
            "CREATE INDEX entity_scope IF NOT EXISTS FOR (n:Entity) ON (n.scope)",
            # Index on source_type
            "CREATE INDEX entity_source IF NOT EXISTS FOR (n:Entity) ON (n.source_type)",
            # Index on owner_id
            "CREATE INDEX entity_owner IF NOT EXISTS FOR (n:Entity) ON (n.owner_id)",
        ]
        with self._driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.debug(f"Scope schema warning: {e}")

        logger.info("Memory scope schema initialized")

    # ──────────────────────────────────────────
    # Query by Scope
    # ──────────────────────────────────────────

    def get_by_scope(
        self,
        scope: str,
        limit: int = 50,
        sort_by: str = "salience",
    ) -> List[Dict[str, Any]]:
        """Get memories filtered by scope."""
        order = "n.salience DESC" if sort_by == "salience" else "n.access_count DESC"
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (n:Entity)
                WHERE n.scope = $scope AND n.salience IS NOT NULL
                RETURN n.uuid AS uuid, n.name AS name,
                       n.salience AS salience, n.scope AS scope,
                       n.source_type AS source_type,
                       n.owner_id AS owner_id,
                       n.access_count AS access_count,
                       n.last_accessed AS last_accessed,
                       n.created_at AS created_at
                ORDER BY {order}
                LIMIT $limit
            """, scope=scope, limit=limit).data()
        return records

    def get_scope_summary(self) -> Dict[str, Any]:
        """Get summary stats per scope."""
        with self._driver.session() as session:
            # Count per scope
            scope_counts = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                WITH COALESCE(n.scope, 'personal') AS scope,
                     count(n) AS cnt,
                     avg(n.salience) AS avg_sal,
                     sum(n.access_count) AS total_access
                RETURN scope, cnt, avg_sal, total_access
                ORDER BY cnt DESC
            """).data()

            # Count per source_type
            source_counts = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                WITH COALESCE(n.source_type, 'document') AS stype,
                     count(n) AS cnt
                RETURN stype, cnt
                ORDER BY cnt DESC
            """).data()

            # Promotion candidates
            candidates = session.run("""
                MATCH (n:Entity)
                WHERE n.scope = 'personal' AND n.salience >= 0.8
                RETURN count(n) AS cnt
            """).single()

        return {
            "scopes": {
                s["scope"]: {
                    "count": s["cnt"],
                    "avg_salience": round(s["avg_sal"] or 0, 3),
                    "total_accesses": s["total_access"] or 0,
                    "decay_rate": SCOPE_DECAY_RATES.get(
                        MemoryScope(s["scope"]) if s["scope"] in [ms.value for ms in MemoryScope] else MemoryScope.PERSONAL,
                        0.95
                    ),
                }
                for s in scope_counts
            },
            "source_types": {s["stype"]: s["cnt"] for s in source_counts},
            "promotion_candidates": candidates["cnt"] if candidates else 0,
        }

    # ──────────────────────────────────────────
    # Scope Promotion
    # ──────────────────────────────────────────

    def promote_memory(
        self,
        memory_uuid: str,
        target_scope: str,
        promoted_by: str = "admin",
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Promote a memory to a higher scope.

        Creates a PROMOTED_TO relationship and updates the scope property.
        """
        target = MemoryScope(target_scope)
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            # Get current state
            current = session.run("""
                MATCH (n:Entity {uuid: $uuid})
                RETURN n.scope AS scope, n.salience AS salience, n.name AS name
            """, uuid=memory_uuid).single()

            if not current:
                return {"error": "Memory not found"}

            old_scope = current["scope"] or "personal"

            # Validate hierarchy (can only promote upward)
            old_idx = next((i for i, s in enumerate(SCOPE_HIERARCHY) if s.value == old_scope), 0)
            new_idx = next((i for i, s in enumerate(SCOPE_HIERARCHY) if s.value == target_scope), 0)

            if new_idx <= old_idx:
                return {"error": f"Cannot promote from {old_scope} to {target_scope} (same or lower tier)"}

            # Update scope
            session.run("""
                MATCH (n:Entity {uuid: $uuid})
                SET n.scope = $new_scope,
                    n.promoted_at = $now,
                    n.promoted_by = $promoted_by
            """, uuid=memory_uuid, new_scope=target_scope, now=now, promoted_by=promoted_by)

            # Record in audit trail
            try:
                from .memory_audit import MemoryAudit
                audit = MemoryAudit(driver=self._driver)
                audit.record(
                    memory_uuid=memory_uuid,
                    field="scope",
                    old_value=old_scope,
                    new_value=target_scope,
                    change_type="promote",
                    changed_by=promoted_by,
                    reason=reason or f"Promoted {old_scope} → {target_scope}",
                )
            except Exception as e:
                logger.debug(f"Audit record failed: {e}")

        logger.info(f"Memory {memory_uuid[:8]} promoted: {old_scope} → {target_scope}")
        return {
            "status": "promoted",
            "uuid": memory_uuid,
            "name": current["name"],
            "old_scope": old_scope,
            "new_scope": target_scope,
            "salience": current["salience"],
        }

    def find_promotion_candidates(self, scope: str = "personal") -> List[Dict[str, Any]]:
        """Find memories eligible for promotion from the given scope."""
        rules = SCOPE_PROMOTION_RULES.get(MemoryScope(scope))
        if not rules:
            return []

        min_sal = rules["min_salience"]

        with self._driver.session() as session:
            candidates = session.run("""
                MATCH (n:Entity)
                WHERE n.scope = $scope
                  AND n.salience >= $min_sal
                RETURN n.uuid AS uuid, n.name AS name,
                       n.salience AS salience, n.scope AS scope,
                       n.access_count AS access_count,
                       n.source_type AS source_type,
                       n.owner_id AS owner_id
                ORDER BY n.salience DESC
                LIMIT 50
            """, scope=scope, min_sal=min_sal).data()

        return candidates

    def set_source_type(self, memory_uuid: str, source_type: str) -> Dict[str, Any]:
        """Set the source type for a memory."""
        with self._driver.session() as session:
            result = session.run("""
                MATCH (n:Entity {uuid: $uuid})
                SET n.source_type = $stype
                RETURN n.uuid AS uuid, n.name AS name, n.source_type AS source_type
            """, uuid=memory_uuid, stype=source_type).single()

            if not result:
                return {"error": "Memory not found"}
            return dict(result)

    def get_decay_rate_for(self, scope: str) -> float:
        """Get the decay rate for a given scope."""
        try:
            return SCOPE_DECAY_RATES[MemoryScope(scope)]
        except (ValueError, KeyError):
            return 0.95  # default

    @staticmethod
    def get_decay_rate_static(scope: str) -> float:
        """Static version — no driver needed."""
        try:
            return SCOPE_DECAY_RATES[MemoryScope(scope)]
        except (ValueError, KeyError):
            return 0.95
