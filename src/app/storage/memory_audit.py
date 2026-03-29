"""
Memory Audit Trail — Phase 10

Tracks all changes to memory nodes (salience, content, scope, labels).
Enables rollback to any previous revision and full history timeline.

Every mutation to a memory node creates a MemoryRevision node in Neo4j:

    (:Entity)-[:HAS_REVISION]->(:MemoryRevision {
        revision_id, field, old_value, new_value,
        changed_by, changed_at, change_type, reason
    })
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.memory_audit')


class MemoryAudit:
    """
    Audit trail engine for memory changes.

    Records every salience change, content edit, scope promotion,
    and label modification as an immutable MemoryRevision node.
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
        """Create indexes for MemoryRevision nodes."""
        queries = [
            "CREATE CONSTRAINT rev_uuid IF NOT EXISTS FOR (r:MemoryRevision) REQUIRE r.revision_id IS UNIQUE",
            "CREATE INDEX rev_memory IF NOT EXISTS FOR (r:MemoryRevision) ON (r.memory_uuid)",
            "CREATE INDEX rev_time IF NOT EXISTS FOR (r:MemoryRevision) ON (r.changed_at)",
        ]
        with self._driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.debug(f"Audit schema warning: {e}")

    # ──────────────────────────────────────────
    # Record Revision
    # ──────────────────────────────────────────

    def record(
        self,
        memory_uuid: str,
        field: str,
        old_value: Any,
        new_value: Any,
        change_type: str,
        changed_by: str = "system",
        reason: str = "",
    ) -> str:
        """
        Record a single field change as a MemoryRevision node.

        Args:
            memory_uuid: UUID of the target Entity/Relation
            field: Field name that changed (e.g., 'salience', 'summary', 'scope')
            old_value: Previous value
            new_value: New value
            change_type: One of: boost, decay, edit, promote, archive, rollback, create
            changed_by: Agent or user identifier
            reason: Human-readable reason for the change

        Returns:
            revision_id (UUID string)
        """
        rev_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            session.run("""
                MATCH (m:Entity {uuid: $memory_uuid})
                CREATE (m)-[:HAS_REVISION]->(rev:MemoryRevision {
                    revision_id: $rev_id,
                    memory_uuid: $memory_uuid,
                    field: $field,
                    old_value: $old_value,
                    new_value: $new_value,
                    change_type: $change_type,
                    changed_by: $changed_by,
                    changed_at: $changed_at,
                    reason: $reason
                })
            """,
                rev_id=rev_id,
                memory_uuid=memory_uuid,
                field=field,
                old_value=str(old_value),
                new_value=str(new_value),
                change_type=change_type,
                changed_by=changed_by,
                changed_at=now,
                reason=reason,
            )

        logger.debug(
            f"Revision {rev_id[:8]}: {memory_uuid[:8]}.{field} "
            f"{old_value} → {new_value} ({change_type})"
        )
        return rev_id

    def record_batch(
        self,
        memory_uuid: str,
        changes: List[Dict[str, Any]],
        change_type: str,
        changed_by: str = "system",
        reason: str = "",
    ) -> List[str]:
        """
        Record multiple field changes at once (e.g., during decay cycle).

        Each entry in changes: {"field": "salience", "old": 0.8, "new": 0.76}
        """
        rev_ids = []
        for change in changes:
            rid = self.record(
                memory_uuid=memory_uuid,
                field=change["field"],
                old_value=change["old"],
                new_value=change["new"],
                change_type=change_type,
                changed_by=changed_by,
                reason=reason,
            )
            rev_ids.append(rid)
        return rev_ids

    # ──────────────────────────────────────────
    # Query History
    # ──────────────────────────────────────────

    def get_history(
        self,
        memory_uuid: str,
        limit: int = 50,
        field: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get revision history for a specific memory.

        Returns list sorted by changed_at DESC (newest first).
        """
        field_filter = "AND rev.field = $field" if field else ""

        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (m:Entity {{uuid: $uuid}})-[:HAS_REVISION]->(rev:MemoryRevision)
                WHERE true {field_filter}
                RETURN rev.revision_id AS revision_id,
                       rev.field AS field,
                       rev.old_value AS old_value,
                       rev.new_value AS new_value,
                       rev.change_type AS change_type,
                       rev.changed_by AS changed_by,
                       rev.changed_at AS changed_at,
                       rev.reason AS reason
                ORDER BY rev.changed_at DESC
                LIMIT $limit
            """,
                uuid=memory_uuid,
                field=field or "",
                limit=limit,
            ).data()

        return records

    def get_revision(self, revision_id: str) -> Optional[Dict[str, Any]]:
        """Get a single revision by ID."""
        with self._driver.session() as session:
            record = session.run("""
                MATCH (rev:MemoryRevision {revision_id: $rid})
                RETURN rev.revision_id AS revision_id,
                       rev.memory_uuid AS memory_uuid,
                       rev.field AS field,
                       rev.old_value AS old_value,
                       rev.new_value AS new_value,
                       rev.change_type AS change_type,
                       rev.changed_by AS changed_by,
                       rev.changed_at AS changed_at,
                       rev.reason AS reason
            """, rid=revision_id).single()

        return dict(record) if record else None

    def get_recent_activity(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Get most recent revisions across all memories (for Activity Feed)."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (m:Entity)-[:HAS_REVISION]->(rev:MemoryRevision)
                RETURN rev.revision_id AS revision_id,
                       rev.memory_uuid AS memory_uuid,
                       m.name AS memory_name,
                       rev.field AS field,
                       rev.old_value AS old_value,
                       rev.new_value AS new_value,
                       rev.change_type AS change_type,
                       rev.changed_by AS changed_by,
                       rev.changed_at AS changed_at,
                       rev.reason AS reason
                ORDER BY rev.changed_at DESC
                LIMIT $limit
            """, limit=limit).data()

        return records

    def get_decay_cycles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get summary of recent decay cycles."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (rev:MemoryRevision)
                WHERE rev.change_type = 'decay'
                WITH rev.changed_at AS cycle_time,
                     count(rev) AS affected_count,
                     avg(toFloat(rev.old_value) - toFloat(rev.new_value)) AS avg_decay
                RETURN cycle_time, affected_count, avg_decay
                ORDER BY cycle_time DESC
                LIMIT $limit
            """, limit=limit).data()

        return records

    # ──────────────────────────────────────────
    # Rollback
    # ──────────────────────────────────────────

    def rollback_to_revision(
        self,
        revision_id: str,
        rolled_back_by: str = "admin",
    ) -> Dict[str, Any]:
        """
        Rollback a memory to the state before a specific revision.

        Uses the revision's old_value to restore the field.
        The rollback itself is recorded as a new revision.
        """
        rev = self.get_revision(revision_id)
        if not rev:
            return {"error": "Revision not found"}

        memory_uuid = rev["memory_uuid"]
        field = rev["field"]
        restore_value = rev["old_value"]
        current_value = rev["new_value"]

        # Apply rollback to Neo4j
        with self._driver.session() as session:
            if field == "salience":
                session.run("""
                    MATCH (n:Entity {uuid: $uuid})
                    SET n.salience = toFloat($value)
                """, uuid=memory_uuid, value=restore_value)
            elif field == "summary":
                session.run("""
                    MATCH (n:Entity {uuid: $uuid})
                    SET n.summary = $value
                """, uuid=memory_uuid, value=restore_value)
            elif field == "name":
                session.run("""
                    MATCH (n:Entity {uuid: $uuid})
                    SET n.name = $value, n.name_lower = toLower($value)
                """, uuid=memory_uuid, value=restore_value)
            elif field == "scope":
                session.run("""
                    MATCH (n:Entity {uuid: $uuid})
                    SET n.scope = $value
                """, uuid=memory_uuid, value=restore_value)
            else:
                return {"error": f"Rollback not supported for field: {field}"}

        # Record the rollback as a new revision
        rollback_rev_id = self.record(
            memory_uuid=memory_uuid,
            field=field,
            old_value=current_value,
            new_value=restore_value,
            change_type="rollback",
            changed_by=rolled_back_by,
            reason=f"Rolled back from revision {revision_id[:8]}",
        )

        logger.info(
            f"Rollback: {memory_uuid[:8]}.{field} "
            f"restored from revison {revision_id[:8]}"
        )

        return {
            "status": "rolled_back",
            "memory_uuid": memory_uuid,
            "field": field,
            "restored_value": restore_value,
            "from_revision": revision_id,
            "rollback_revision": rollback_rev_id,
        }

    def rollback_decay_cycle(
        self,
        cycle_timestamp: str,
        rolled_back_by: str = "admin",
    ) -> Dict[str, Any]:
        """
        Rollback an entire decay cycle by timestamp.

        Finds all revisions with change_type='decay' at the given timestamp
        and restores each memory to its pre-decay state.
        """
        with self._driver.session() as session:
            revisions = session.run("""
                MATCH (rev:MemoryRevision)
                WHERE rev.change_type = 'decay'
                  AND rev.changed_at = $ts
                RETURN rev.revision_id AS revision_id,
                       rev.memory_uuid AS memory_uuid,
                       rev.field AS field,
                       rev.old_value AS old_value,
                       rev.new_value AS new_value
            """, ts=cycle_timestamp).data()

        rolled_back = 0
        for rev in revisions:
            result = self.rollback_to_revision(
                rev["revision_id"],
                rolled_back_by=rolled_back_by,
            )
            if result.get("status") == "rolled_back":
                rolled_back += 1

        return {
            "status": "cycle_rolled_back",
            "cycle_timestamp": cycle_timestamp,
            "revisions_found": len(revisions),
            "rolled_back": rolled_back,
        }

    # ──────────────────────────────────────────
    # Statistics
    # ──────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get audit trail statistics."""
        with self._driver.session() as session:
            stats = session.run("""
                MATCH (rev:MemoryRevision)
                WITH rev.change_type AS ct, count(rev) AS cnt
                RETURN ct, cnt ORDER BY cnt DESC
            """).data()

            total = session.run(
                "MATCH (rev:MemoryRevision) RETURN count(rev) AS total"
            ).single()

        return {
            "total_revisions": total["total"] if total else 0,
            "by_type": {s["ct"]: s["cnt"] for s in stats if s["ct"] is not None},
        }
