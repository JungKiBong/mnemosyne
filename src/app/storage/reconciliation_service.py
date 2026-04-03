"""
ReconciliationService — Data Consistency Engine

Ensures consistency between Neo4j (source of truth) and Supermemory
(async replica). Detects drift, generates repair actions, and provides
reconciliation reports.

Runs as:
  1. On-demand via API: POST /api/reconciliation/run
  2. Scheduled background job (hourly)
  3. Manual check: POST /api/reconciliation/check

Key capabilities:
  - Detect orphan records (in SM but not in Neo4j, and vice versa)
  - Detect salience/content drift between stores
  - Auto-repair or flag for manual intervention
  - Generate audit trail for all reconciliation actions
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from enum import Enum

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.reconciliation')


class DriftSeverity(Enum):
    """Severity classification for data drift."""
    INFO = "info"           # Minor inconsistency, auto-fixable
    WARNING = "warning"     # Noticeable drift, needs review
    CRITICAL = "critical"   # Data integrity issue, requires action


class DriftType(Enum):
    """Types of data drift detected."""
    ORPHAN_NEO4J = "orphan_neo4j"           # In Neo4j but not in SM
    ORPHAN_SM = "orphan_sm"                 # In SM but not in Neo4j
    STALE_SALIENCE = "stale_salience"       # Salience hasn't been updated
    MISSING_SCOPE = "missing_scope"         # Entity has no scope assigned
    MISSING_AUDIT = "missing_audit"         # Entity has no audit trail
    SCHEMA_VIOLATION = "schema_violation"   # Missing required properties
    DEAD_LETTER = "dead_letter"             # Outbox dead letters pending


class ReconciliationResult:
    """Immutable result of a reconciliation run."""

    def __init__(self):
        self.run_id = str(uuid.uuid4())
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None
        self.issues: List[Dict[str, Any]] = []
        self.auto_fixed: int = 0
        self.needs_review: int = 0
        self.total_checked: int = 0

    def add_issue(
        self,
        drift_type: DriftType,
        severity: DriftSeverity,
        entity_uuid: str,
        description: str,
        auto_fixed: bool = False,
    ):
        self.issues.append({
            "drift_type": drift_type.value,
            "severity": severity.value,
            "entity_uuid": entity_uuid,
            "description": description,
            "auto_fixed": auto_fixed,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        })
        if auto_fixed:
            self.auto_fixed += 1
        else:
            self.needs_review += 1

    def finalize(self):
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_checked": self.total_checked,
            "issues_found": len(self.issues),
            "auto_fixed": self.auto_fixed,
            "needs_review": self.needs_review,
            "issues": self.issues,
            "health_score": self._calc_health_score(),
        }

    def _calc_health_score(self) -> float:
        """Calculate a 0.0-1.0 health score. 1.0 = perfect consistency."""
        if self.total_checked == 0:
            return 1.0
        critical = sum(1 for i in self.issues if i["severity"] == "critical" and not i["auto_fixed"])
        warning = sum(1 for i in self.issues if i["severity"] == "warning" and not i["auto_fixed"])
        penalty = (critical * 0.15) + (warning * 0.05)
        return max(0.0, round(1.0 - penalty, 3))


class ReconciliationService:
    """
    Data consistency engine for Mories.

    Checks Neo4j entities for:
    1. Schema completeness (required properties present)
    2. Scope correctness (every entity has a valid scope)
    3. Audit trail coverage (every entity has at least one revision)
    4. Salience staleness (entities not updated in 30+ days)
    5. Dead letter queue health (outbox failures)
    6. Episodic binding integrity (RELATION → Episode linkage)
    7. Neo4j ↔ Supermemory drift detection
    """

    def __init__(self, driver=None, sm_client=None):
        if driver:
            self._driver = driver
            self._owns_driver = False
        else:
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
            self._owns_driver = True
        self._sm = sm_client  # Optional SupermemoryClientWrapper

    def close(self):
        if self._owns_driver:
            self._driver.close()

    # ──────────────────────────────────────────
    # Main Reconciliation
    # ──────────────────────────────────────────

    def run(self, auto_fix: bool = False) -> ReconciliationResult:
        """
        Run full reconciliation check.

        Args:
            auto_fix: If True, automatically fix INFO-level issues.

        Returns:
            ReconciliationResult with all findings
        """
        result = ReconciliationResult()
        logger.info(f"Reconciliation run started: {result.run_id}")

        try:
            # 1. Check schema completeness
            self._check_schema_completeness(result, auto_fix)

            # 2. Check scope assignments
            self._check_scope_assignments(result, auto_fix)

            # 3. Check audit trail coverage
            self._check_audit_coverage(result)

            # 4. Check salience staleness
            self._check_salience_staleness(result)

            # 5. Check dead letters (outbox)
            self._check_dead_letters(result)

            # 6. Check orphaned revisions
            self._check_orphaned_revisions(result, auto_fix)

            # 7. Episodic binding integrity
            self._check_episodic_binding(result, auto_fix)

            # 8. Neo4j ↔ Supermemory drift detection
            self._check_neo4j_sm_drift(result)

        except Exception as e:
            logger.error(f"Reconciliation error: {e}")
            result.add_issue(
                drift_type=DriftType.SCHEMA_VIOLATION,
                severity=DriftSeverity.CRITICAL,
                entity_uuid="system",
                description=f"Reconciliation engine error: {str(e)}",
            )

        result.finalize()
        logger.info(
            f"Reconciliation completed: {result.total_checked} checked, "
            f"{len(result.issues)} issues ({result.auto_fixed} auto-fixed), "
            f"health={result._calc_health_score()}"
        )

        # Persist the run result
        self._persist_run(result)

        return result

    def quick_check(self) -> Dict[str, Any]:
        """
        Lightweight health check (no auto-fix).
        Returns summary only without detailed issues.
        """
        with self._driver.session() as session:
            # Count entities
            total = session.run(
                "MATCH (n:Entity) WHERE n.salience IS NOT NULL RETURN count(n) AS cnt"
            ).single()["cnt"]

            # Count without scope
            no_scope = session.run(
                "MATCH (n:Entity) WHERE n.salience IS NOT NULL AND n.scope IS NULL "
                "RETURN count(n) AS cnt"
            ).single()["cnt"]

            # Count without audit
            no_audit = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                AND NOT EXISTS { (n)-[:HAS_REVISION]->(:MemoryRevision) }
                RETURN count(n) AS cnt
            """).single()["cnt"]

            # Count stale (>30 days without update)
            stale = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                  AND n.last_accessed IS NOT NULL
                  AND toString(n.last_accessed) =~ '\\d{4}-\\d{2}-\\d{2}.*'
                WITH n
                WHERE toString(n.last_accessed) < toString(datetime() - duration('P30D'))
                RETURN count(n) AS cnt
            """).single()["cnt"]

        return {
            "total_memories": total,
            "without_scope": no_scope,
            "without_audit": no_audit,
            "stale_30d": stale,
            "health_score": self._calc_quick_score(total, no_scope, no_audit, stale),
        }

    # ──────────────────────────────────────────
    # Individual Checks
    # ──────────────────────────────────────────

    def _check_schema_completeness(self, result: ReconciliationResult, auto_fix: bool):
        """Check that all memory entities have required properties."""
        required_props = ['uuid', 'name', 'salience']

        with self._driver.session() as session:
            # Find entities missing required properties
            for prop in required_props:
                records = session.run(f"""
                    MATCH (n:Entity)
                    WHERE n.salience IS NOT NULL AND n.{prop} IS NULL
                    RETURN n.uuid AS uuid, n.name AS name
                    LIMIT 100
                """).data()

                result.total_checked += len(records)

                for record in records:
                    entity_uuid = record.get("uuid") or "unknown"

                    if auto_fix and prop == "name":
                        # Auto-fix: set default name
                        session.run("""
                            MATCH (n:Entity {uuid: $uuid})
                            SET n.name = 'Unnamed Memory',
                                n.name_lower = 'unnamed memory'
                        """, uuid=entity_uuid)
                        result.add_issue(
                            DriftType.SCHEMA_VIOLATION, DriftSeverity.INFO,
                            entity_uuid,
                            f"Missing '{prop}' property — auto-filled with default",
                            auto_fixed=True,
                        )
                    else:
                        result.add_issue(
                            DriftType.SCHEMA_VIOLATION, DriftSeverity.WARNING,
                            entity_uuid,
                            f"Missing required property: '{prop}'",
                        )

            # Check total entities for overall count
            total = session.run(
                "MATCH (n:Entity) WHERE n.salience IS NOT NULL RETURN count(n) AS cnt"
            ).single()["cnt"]
            result.total_checked = max(result.total_checked, total)

    def _check_scope_assignments(self, result: ReconciliationResult, auto_fix: bool):
        """Check that all entities have a valid scope."""
        valid_scopes = {'personal', 'tribal', 'social', 'global'}

        with self._driver.session() as session:
            # Find entities with null or invalid scope
            records = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                  AND (n.scope IS NULL OR NOT n.scope IN $valid)
                RETURN n.uuid AS uuid, n.name AS name, n.scope AS scope
                LIMIT 200
            """, valid=list(valid_scopes)).data()

            for record in records:
                entity_uuid = record["uuid"]
                current_scope = record.get("scope")

                if auto_fix:
                    session.run("""
                        MATCH (n:Entity {uuid: $uuid})
                        SET n.scope = 'personal'
                    """, uuid=entity_uuid)
                    result.add_issue(
                        DriftType.MISSING_SCOPE, DriftSeverity.INFO,
                        entity_uuid,
                        f"Scope was '{current_scope}' — set to 'personal'",
                        auto_fixed=True,
                    )
                else:
                    result.add_issue(
                        DriftType.MISSING_SCOPE, DriftSeverity.WARNING,
                        entity_uuid,
                        f"Invalid or missing scope: '{current_scope}'",
                    )

    def _check_audit_coverage(self, result: ReconciliationResult):
        """Check that entities have audit trail entries."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                AND NOT EXISTS { (n)-[:HAS_REVISION]->(:MemoryRevision) }
                RETURN n.uuid AS uuid, n.name AS name
                LIMIT 100
            """).data()

            for record in records:
                result.add_issue(
                    DriftType.MISSING_AUDIT, DriftSeverity.INFO,
                    record["uuid"],
                    f"No audit trail for '{record.get('name', 'unknown')}'",
                )

    def _check_salience_staleness(self, result: ReconciliationResult):
        """Find entities whose salience hasn't been updated in 30+ days."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                  AND n.salience > 0.1
                  AND n.last_accessed IS NOT NULL
                  AND toString(n.last_accessed) =~ '\\d{4}-\\d{2}-\\d{2}.*'
                WITH n
                WHERE toString(n.last_accessed) < toString(datetime() - duration('P30D'))
                RETURN n.uuid AS uuid, n.name AS name,
                       n.salience AS salience, n.last_accessed AS last_accessed
                ORDER BY toString(n.last_accessed) ASC
                LIMIT 50
            """).data()

            for record in records:
                result.add_issue(
                    DriftType.STALE_SALIENCE, DriftSeverity.WARNING,
                    record["uuid"],
                    f"'{record.get('name')}' (sal={record.get('salience', 0):.2f}) "
                    f"not accessed since {record.get('last_accessed', 'unknown')}"
                )

    def _check_dead_letters(self, result: ReconciliationResult):
        """Check for unprocessed dead letters in the outbox."""
        try:
            # Try to get the outbox from app extensions
            from flask import current_app
            storage = current_app.extensions.get('neo4j_storage')
            if hasattr(storage, 'outbox'):
                dead_letters = storage.outbox.get_dead_letters()
                for dl in dead_letters:
                    result.add_issue(
                        DriftType.DEAD_LETTER, DriftSeverity.WARNING,
                        dl.get('graph_id', 'unknown'),
                        f"Dead letter: {dl.get('action', 'unknown')} — "
                        f"retries exhausted ({dl.get('retries', 0)})",
                    )
        except (RuntimeError, ImportError):
            # Outside request context — skip dead letter check
            pass

    def _check_orphaned_revisions(self, result: ReconciliationResult, auto_fix: bool):
        """Find MemoryRevision nodes not connected to any Entity."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (rev:MemoryRevision)
                WHERE NOT EXISTS { (:Entity)-[:HAS_REVISION]->(rev) }
                RETURN rev.revision_id AS rid, rev.memory_uuid AS mem_uuid
                LIMIT 50
            """).data()

            for record in records:
                if auto_fix:
                    session.run(
                        "MATCH (rev:MemoryRevision {revision_id: $rid}) DELETE rev",
                        rid=record["rid"],
                    )
                    result.add_issue(
                        DriftType.ORPHAN_NEO4J, DriftSeverity.INFO,
                        record.get("mem_uuid", "unknown"),
                        f"Orphaned revision {record['rid'][:8]} — deleted",
                        auto_fixed=True,
                    )
                else:
                    result.add_issue(
                        DriftType.ORPHAN_NEO4J, DriftSeverity.INFO,
                        record.get("mem_uuid", "unknown"),
                        f"Orphaned revision: {record['rid'][:8]}",
                    )

    # ──────────────────────────────────────────
    # Episodic Binding & SM Drift
    # ──────────────────────────────────────────

    def _check_episodic_binding(self, result: ReconciliationResult, auto_fix: bool):
        """
        Check that every RELATION's episode_ids point to existing Episode nodes.
        
        Broken bindings mean a fact has lost its causal origin — the 'why' 
        behind the knowledge is missing. This is a critical episodic memory defect.
        """
        with self._driver.session() as session:
            # Find relations with episode_ids that reference non-existent Episodes
            records = session.run("""
                MATCH (src:Entity)-[r:RELATION]->(tgt:Entity)
                WHERE r.episode_ids IS NOT NULL AND size(r.episode_ids) > 0
                UNWIND r.episode_ids AS ep_id
                OPTIONAL MATCH (ep:Episode {uuid: ep_id})
                WITH r, ep_id, ep
                WHERE ep IS NULL
                RETURN r.uuid AS rel_uuid, r.fact AS fact, ep_id AS missing_episode
                LIMIT 100
            """).data()

            for record in records:
                rel_uuid = record.get("rel_uuid", "unknown")
                fact_preview = (record.get("fact", ""))[:60]
                missing_ep = record.get("missing_episode", "unknown")[:8]

                if auto_fix:
                    # Remove the broken episode_id from the relation's list
                    session.run("""
                        MATCH ()-[r:RELATION {uuid: $uuid}]->()
                        SET r.episode_ids = [eid IN r.episode_ids WHERE eid <> $bad_id]
                    """, uuid=rel_uuid, bad_id=record.get("missing_episode"))
                    result.add_issue(
                        DriftType.ORPHAN_NEO4J, DriftSeverity.INFO,
                        rel_uuid,
                        f"Broken episode binding: '{fact_preview}...' → Episode {missing_ep} — cleaned",
                        auto_fixed=True,
                    )
                else:
                    result.add_issue(
                        DriftType.ORPHAN_NEO4J, DriftSeverity.WARNING,
                        rel_uuid,
                        f"Broken episode binding: '{fact_preview}...' → Episode {missing_ep} not found",
                    )

            # Also check Relations with empty or null episode_ids
            orphan_records = session.run("""
                MATCH (src:Entity)-[r:RELATION]->(tgt:Entity)
                WHERE r.episode_ids IS NULL OR size(r.episode_ids) = 0
                RETURN r.uuid AS rel_uuid, r.fact AS fact
                LIMIT 50
            """).data()

            for record in orphan_records:
                rel_uuid = record.get("rel_uuid", "unknown")
                fact_preview = (record.get("fact", ""))[:60]
                result.add_issue(
                    DriftType.ORPHAN_NEO4J, DriftSeverity.WARNING,
                    rel_uuid,
                    f"Relation without any episode binding: '{fact_preview}...'",
                )

            result.total_checked += len(records) + len(orphan_records)

    def _check_neo4j_sm_drift(self, result: ReconciliationResult):
        """
        Cross-check Neo4j episode/fact counts against Supermemory memory counts
        per graph_id. Large discrepancies indicate SM replication lag or data loss.
        """
        if not self._sm or not self._sm.client:
            logger.debug("SM client not available — skipping drift check")
            return

        with self._driver.session() as session:
            # Get episode counts per graph  
            graph_records = session.run("""
                MATCH (ep:Episode)
                RETURN ep.graph_id AS graph_id, count(ep) AS neo4j_count
                ORDER BY neo4j_count DESC
                LIMIT 20
            """).data()

        for record in graph_records:
            graph_id = record.get("graph_id")
            neo4j_count = record.get("neo4j_count", 0)

            if not graph_id:
                continue

            try:
                # Query SM for memories tagged to this graph
                sm_results = self._sm.search_memories(
                    query="*",  # wildcard to get count
                    container_tag=graph_id,
                    limit=1,
                )
                # Approximate SM count from response
                sm_count = len(sm_results) if isinstance(sm_results, list) else 0
                
                drift_ratio = abs(neo4j_count - sm_count) / max(neo4j_count, 1)
                
                if drift_ratio > 0.5:
                    result.add_issue(
                        DriftType.ORPHAN_SM, DriftSeverity.WARNING,
                        graph_id,
                        f"Significant drift: Neo4j has {neo4j_count} episodes, "
                        f"SM returned {sm_count} memories (drift={drift_ratio:.0%})",
                    )
                    
            except Exception as e:
                logger.debug(f"SM drift check failed for {graph_id}: {e}")

            result.total_checked += 1

    # ──────────────────────────────────────────
    # Persistence & History
    # ──────────────────────────────────────────

    def _persist_run(self, result: ReconciliationResult):
        """Save reconciliation run as a node in Neo4j for history tracking."""
        try:
            with self._driver.session() as session:
                session.run("""
                    CREATE (r:ReconciliationRun {
                        run_id: $run_id,
                        started_at: $started_at,
                        completed_at: $completed_at,
                        total_checked: $total_checked,
                        issues_found: $issues_found,
                        auto_fixed: $auto_fixed,
                        needs_review: $needs_review,
                        health_score: $health_score
                    })
                """,
                    run_id=result.run_id,
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    total_checked=result.total_checked,
                    issues_found=len(result.issues),
                    auto_fixed=result.auto_fixed,
                    needs_review=result.needs_review,
                    health_score=result._calc_health_score(),
                )
        except Exception as e:
            logger.debug(f"Failed to persist reconciliation run: {e}")

    def get_run_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get history of reconciliation runs."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (r:ReconciliationRun)
                RETURN r.run_id AS run_id,
                       r.started_at AS started_at,
                       r.completed_at AS completed_at,
                       r.total_checked AS total_checked,
                       r.issues_found AS issues_found,
                       r.auto_fixed AS auto_fixed,
                       r.needs_review AS needs_review,
                       r.health_score AS health_score
                ORDER BY r.started_at DESC
                LIMIT $limit
            """, limit=limit).data()

        return records

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    @staticmethod
    def _calc_quick_score(total: int, no_scope: int, no_audit: int, stale: int) -> float:
        """Calculate quick health score."""
        if total == 0:
            return 1.0
        issues = no_scope + stale
        penalty = (issues / total) * 0.5
        return max(0.0, round(1.0 - penalty, 3))
