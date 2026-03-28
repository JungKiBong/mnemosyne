"""
Integration tests for ReconciliationService.

Tests data consistency checks against live Neo4j.
"""

import uuid
import pytest
from datetime import datetime, timezone


class TestReconciliationService:
    """Test the ReconciliationService data consistency checks."""

    @pytest.fixture
    def recon_service(self, neo4j_driver):
        from app.storage.reconciliation_service import ReconciliationService
        svc = ReconciliationService(driver=neo4j_driver)
        yield svc
        # Don't close — driver is session-scoped

    @pytest.fixture
    def test_entity(self, neo4j_driver, test_prefix):
        """Create a test entity for reconciliation checks."""
        entity_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with neo4j_driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid, graph_id: $gid, name: 'Recon Test',
                    name_lower: 'recon test', salience: 0.5,
                    access_count: 1, last_accessed: $now, created_at: $now,
                    scope: 'personal', source_type: 'document', owner_id: 'test'
                })
            """, uuid=entity_uuid, gid=test_prefix, now=now)

        yield entity_uuid

        # Cleanup
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (n:Entity {uuid: $uuid}) "
                "OPTIONAL MATCH (n)-[:HAS_REVISION]->(r) "
                "DETACH DELETE r, n",
                uuid=entity_uuid,
            )

    def test_quick_check_returns_valid_structure(self, recon_service):
        """Quick check returns expected fields."""
        result = recon_service.quick_check()

        assert 'total_memories' in result
        assert 'without_scope' in result
        assert 'without_audit' in result
        assert 'stale_30d' in result
        assert 'health_score' in result
        assert 0.0 <= result['health_score'] <= 1.0

    def test_full_run_returns_result(self, recon_service, test_entity):
        """Full reconciliation run returns a valid result."""
        result = recon_service.run(auto_fix=False)

        assert result.run_id is not None
        assert result.completed_at is not None
        assert result.total_checked > 0
        assert 0.0 <= result._calc_health_score() <= 1.0

    def test_auto_fix_scope(self, neo4j_driver, test_prefix, recon_service):
        """Auto-fix fills in missing scope."""
        entity_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with neo4j_driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid, graph_id: $gid, name: 'No Scope',
                    name_lower: 'no scope', salience: 0.5,
                    access_count: 0, last_accessed: $now, created_at: $now
                })
            """, uuid=entity_uuid, gid=test_prefix, now=now)

        try:
            result = recon_service.run(auto_fix=True)

            # Should have fixed the scope
            with neo4j_driver.session() as session:
                record = session.run(
                    "MATCH (n:Entity {uuid: $uuid}) RETURN n.scope AS scope",
                    uuid=entity_uuid,
                ).single()

                assert record is not None
                assert record['scope'] == 'personal'
        finally:
            with neo4j_driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n",
                    uuid=entity_uuid,
                )

    def test_run_history_persistence(self, recon_service, neo4j_driver, test_entity):
        """Reconciliation runs are persisted in Neo4j."""
        recon_service.run(auto_fix=False)
        history = recon_service.get_run_history(limit=5)

        assert len(history) >= 1
        latest = history[0]
        assert 'run_id' in latest
        assert 'health_score' in latest

        # Cleanup reconciliation run nodes
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (r:ReconciliationRun {run_id: $rid}) DELETE r",
                rid=latest['run_id'],
            )

    def test_health_score_calculation(self, recon_service):
        """Health score is between 0 and 1."""
        from app.storage.reconciliation_service import ReconciliationResult
        result = ReconciliationResult()
        result.total_checked = 100

        # Perfect health
        assert result._calc_health_score() == 1.0

        # Add some issues
        from app.storage.reconciliation_service import DriftType, DriftSeverity
        result.add_issue(
            DriftType.STALE_SALIENCE, DriftSeverity.WARNING,
            "test-uuid", "Stale"
        )
        score = result._calc_health_score()
        assert 0.0 < score < 1.0

    def test_missing_audit_detected(self, neo4j_driver, test_prefix, recon_service):
        """Entities without audit trail are flagged."""
        entity_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with neo4j_driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid, graph_id: $gid, name: 'No Audit',
                    name_lower: 'no audit', salience: 0.6,
                    access_count: 0, last_accessed: $now, created_at: $now,
                    scope: 'personal'
                })
            """, uuid=entity_uuid, gid=test_prefix, now=now)

        try:
            result = recon_service.run(auto_fix=False)
            missing_audit = [
                i for i in result.issues
                if i['drift_type'] == 'missing_audit'
                and i['entity_uuid'] == entity_uuid
            ]
            assert len(missing_audit) >= 1
        finally:
            with neo4j_driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n",
                    uuid=entity_uuid,
                )
