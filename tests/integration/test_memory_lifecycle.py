"""
Integration tests — Memory Lifecycle (Phase 7 + 8 + 10)

Tests the real STM → LTM lifecycle, scope promotions, decay,
audit trail, and retrieval boost using a live Neo4j connection.
"""

import time
import uuid
import pytest

from app.storage.memory_manager import MemoryManager, MemoryConfig, STMItem


class TestSTMLifecycle:
    """Test Short-Term Memory buffer operations."""

    def test_stm_add_and_list(self, memory_manager):
        """STM items can be added and listed."""
        item = memory_manager.stm_add(
            content="테스트 기억: 프로젝트 미팅에서 아키텍처 결정",
            source="test_integration",
            metadata={"topic": "architecture"},
        )

        assert item.id is not None
        assert item.salience == 0.5
        assert item.source == "test_integration"

        items = memory_manager.stm_list()
        found = [i for i in items if i['id'] == item.id]
        assert len(found) == 1
        assert found[0]['content'] == "테스트 기억: 프로젝트 미팅에서 아키텍처 결정"

    def test_stm_evaluate_promote(self, memory_manager):
        """Evaluate salience → auto-promote determination."""
        item = memory_manager.stm_add(content="High salience memory", source="test")

        result = memory_manager.stm_evaluate(item.id, salience=0.85)
        assert result['evaluation_result'] == 'promote'
        assert result['salience'] == 0.85

    def test_stm_evaluate_discard(self, memory_manager):
        """Low salience items get discard recommendation."""
        item = memory_manager.stm_add(content="Low value noise", source="test")

        result = memory_manager.stm_evaluate(item.id, salience=0.1)
        assert result['evaluation_result'] == 'discard'

    def test_stm_evaluate_hitl(self, memory_manager):
        """Mid-range salience requires HITL review."""
        item = memory_manager.stm_add(content="Ambiguous info", source="test")

        result = memory_manager.stm_evaluate(item.id, salience=0.5)
        assert result['evaluation_result'] == 'pending_hitl'

    def test_stm_ttl_expiry(self):
        """Expired items are cleaned from STM."""
        config = MemoryConfig(stm_default_ttl=0.5)  # 0.5 second TTL
        mgr = MemoryManager(config=config)
        try:
            item = mgr.stm_add(content="Ephemeral memory", source="test")
            assert len(mgr.stm_list()) >= 1

            time.sleep(0.7)  # Wait for expiry
            items = mgr.stm_list()  # This triggers cleanup
            found = [i for i in items if i['id'] == item.id]
            assert len(found) == 0
        finally:
            mgr.close()

    def test_stm_discard(self, memory_manager):
        """Discard removes item from STM buffer."""
        item = memory_manager.stm_add(content="To be discarded", source="test")
        result = memory_manager.stm_discard(item.id)
        assert result['status'] == 'discarded'

        # Verify it's gone
        items = memory_manager.stm_list()
        found = [i for i in items if i['id'] == item.id]
        assert len(found) == 0


class TestSTMtoLTMPromotion:
    """Test the complete STM → LTM promotion to Neo4j."""

    def test_promote_creates_neo4j_node(self, memory_manager, test_prefix):
        """Promoting STM item creates an Entity:Memory node in Neo4j."""
        item = memory_manager.stm_add(
            content="Important discovery: Neo4j performance optimized",
            source="test_integration",
        )
        memory_manager.stm_evaluate(item.id, salience=0.9)

        result = memory_manager.stm_promote(item.id, graph_id=test_prefix)

        assert result['status'] == 'promoted'
        assert 'ltm_uuid' in result
        ltm_uuid = result['ltm_uuid']

        # Verify in Neo4j
        with memory_manager._driver.session() as session:
            record = session.run(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n.uuid AS uuid, "
                "n.salience AS salience, n.source AS source",
                uuid=ltm_uuid,
            ).single()

            assert record is not None
            assert record['salience'] == 0.9
            assert record['source'] == 'test_integration'

        # Cleanup
        with memory_manager._driver.session() as session:
            session.run(
                "MATCH (n:Entity {uuid: $uuid}) "
                "OPTIONAL MATCH (n)-[:HAS_REVISION]->(r) "
                "DETACH DELETE r, n",
                uuid=ltm_uuid,
            )

    def test_promote_not_found(self, memory_manager):
        """Promoting a non-existent STM item returns error."""
        result = memory_manager.stm_promote("nonexistent_id")
        assert 'error' in result


class TestDecayAndBoost:
    """Test Ebbinghaus decay and retrieval boost."""

    def _create_test_entity(self, driver, test_prefix, salience=0.5):
        """Helper: create a test entity in Neo4j with known salience."""
        entity_uuid = str(uuid.uuid4())
        from datetime import datetime, timezone, timedelta
        # Set last_accessed to 2 days ago to trigger meaningful decay
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

        with driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid,
                    graph_id: $graph_id,
                    name: $name,
                    name_lower: $name_lower,
                    salience: $salience,
                    access_count: 3,
                    last_accessed: $last_accessed,
                    created_at: $last_accessed,
                    scope: 'personal'
                })
            """,
                uuid=entity_uuid,
                graph_id=test_prefix,
                name=f"Test Entity {entity_uuid[:6]}",
                name_lower=f"test entity {entity_uuid[:6]}",
                salience=salience,
                last_accessed=two_days_ago,
            )

        return entity_uuid

    def test_decay_reduces_salience(self, memory_manager, test_prefix):
        """Decay cycle reduces salience based on idle time."""
        entity_uuid = self._create_test_entity(
            memory_manager._driver, test_prefix, salience=0.7
        )
        try:
            result = memory_manager.run_decay(dry_run=False)

            assert result['total_processed'] > 0

            # Verify salience decreased
            with memory_manager._driver.session() as session:
                record = session.run(
                    "MATCH (n:Entity {uuid: $uuid}) RETURN n.salience AS salience",
                    uuid=entity_uuid,
                ).single()

                assert record is not None
                assert record['salience'] < 0.7  # Should have decayed
        finally:
            with memory_manager._driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) "
                    "OPTIONAL MATCH (n)-[:HAS_REVISION]->(r) "
                    "DETACH DELETE r, n",
                    uuid=entity_uuid,
                )

    def test_dry_run_no_change(self, memory_manager, test_prefix):
        """Dry run calculates but doesn't modify Neo4j."""
        entity_uuid = self._create_test_entity(
            memory_manager._driver, test_prefix, salience=0.6
        )
        try:
            memory_manager.run_decay(dry_run=True)

            with memory_manager._driver.session() as session:
                record = session.run(
                    "MATCH (n:Entity {uuid: $uuid}) RETURN n.salience AS salience",
                    uuid=entity_uuid,
                ).single()

                assert record['salience'] == 0.6  # Unchanged
        finally:
            with memory_manager._driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n",
                    uuid=entity_uuid,
                )

    def test_retrieval_boost_increases_salience(self, memory_manager, test_prefix):
        """Retrieval boost increases salience and access_count."""
        entity_uuid = self._create_test_entity(
            memory_manager._driver, test_prefix, salience=0.5
        )
        try:
            boosted = memory_manager.boost_on_retrieval([entity_uuid])
            assert boosted == 1

            with memory_manager._driver.session() as session:
                record = session.run(
                    "MATCH (n:Entity {uuid: $uuid}) "
                    "RETURN n.salience AS salience, n.access_count AS ac",
                    uuid=entity_uuid,
                ).single()

                assert record['salience'] > 0.5
                assert record['ac'] > 3  # Was 3, now incremented
        finally:
            with memory_manager._driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n",
                    uuid=entity_uuid,
                )

    def test_manual_boost(self, memory_manager, test_prefix):
        """Manual boost adjusts salience by given amount."""
        entity_uuid = self._create_test_entity(
            memory_manager._driver, test_prefix, salience=0.5
        )
        try:
            result = memory_manager.manual_boost(entity_uuid, amount=0.2)
            assert result['salience'] == pytest.approx(0.7, abs=0.01)
            assert result['type'] == 'entity'
        finally:
            with memory_manager._driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) "
                    "OPTIONAL MATCH (n)-[:HAS_REVISION]->(r) "
                    "DETACH DELETE r, n",
                    uuid=entity_uuid,
                )


class TestAuditTrailIntegration:
    """Test audit trail records are created during memory operations."""

    def test_promote_creates_audit_record(self, memory_manager, test_prefix):
        """STM promotion should create an audit trail record."""
        item = memory_manager.stm_add(content="Audit test memory", source="test")
        memory_manager.stm_evaluate(item.id, salience=0.8)

        result = memory_manager.stm_promote(item.id, graph_id=test_prefix)
        ltm_uuid = result['ltm_uuid']

        try:
            # Check audit trail
            from app.storage.memory_audit import MemoryAudit
            audit = MemoryAudit(driver=memory_manager._driver)
            history = audit.get_history(ltm_uuid)

            assert len(history) >= 1
            creation = [h for h in history if h['change_type'] == 'create']
            assert len(creation) >= 1
        finally:
            with memory_manager._driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) "
                    "OPTIONAL MATCH (n)-[:HAS_REVISION]->(r) "
                    "DETACH DELETE r, n",
                    uuid=ltm_uuid,
                )

    def test_boost_creates_audit_record(self, memory_manager, test_prefix):
        """Manual boost should create an audit trail record."""
        # Create entity directly
        entity_uuid = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with memory_manager._driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid, graph_id: $gid, name: 'Audit Test',
                    name_lower: 'audit test', salience: 0.5,
                    access_count: 0, last_accessed: $now, created_at: $now
                })
            """, uuid=entity_uuid, gid=test_prefix, now=now)

        try:
            memory_manager.manual_boost(entity_uuid, amount=0.15)

            from app.storage.memory_audit import MemoryAudit
            audit = MemoryAudit(driver=memory_manager._driver)
            history = audit.get_history(entity_uuid)

            boost_records = [h for h in history if h['change_type'] == 'boost']
            assert len(boost_records) >= 1
        finally:
            with memory_manager._driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) "
                    "OPTIONAL MATCH (n)-[:HAS_REVISION]->(r) "
                    "DETACH DELETE r, n",
                    uuid=entity_uuid,
                )

    def test_rollback_restores_salience(self, memory_manager, test_prefix):
        """Rollback should restore the previous value from audit trail."""
        entity_uuid = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with memory_manager._driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid, graph_id: $gid, name: 'Rollback Test',
                    name_lower: 'rollback test', salience: 0.5,
                    access_count: 0, last_accessed: $now, created_at: $now
                })
            """, uuid=entity_uuid, gid=test_prefix, now=now)

        try:
            # Boost to 0.8
            memory_manager.manual_boost(entity_uuid, amount=0.3)

            from app.storage.memory_audit import MemoryAudit
            audit = MemoryAudit(driver=memory_manager._driver)
            history = audit.get_history(entity_uuid)

            boost_rev = [h for h in history if h['change_type'] == 'boost']
            assert len(boost_rev) >= 1

            # Rollback
            rollback_result = audit.rollback_to_revision(boost_rev[0]['revision_id'])
            assert rollback_result['status'] == 'rolled_back'

            # Verify salience restored
            with memory_manager._driver.session() as session:
                record = session.run(
                    "MATCH (n:Entity {uuid: $uuid}) RETURN n.salience AS salience",
                    uuid=entity_uuid,
                ).single()
                # Should be restored to approximately 0.5
                assert record['salience'] == pytest.approx(0.5, abs=0.05)
        finally:
            with memory_manager._driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) "
                    "OPTIONAL MATCH (n)-[:HAS_REVISION]->(r) "
                    "DETACH DELETE r, n",
                    uuid=entity_uuid,
                )


class TestScopePromotion:
    """Test memory scope promotion (Phase 8)."""

    def test_personal_to_tribal_promotion(self, scope_manager, test_prefix, neo4j_driver):
        """Promote a personal memory to tribal scope."""
        entity_uuid = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        with neo4j_driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid, graph_id: $gid, name: 'Scope Test',
                    name_lower: 'scope test', salience: 0.85,
                    access_count: 5, last_accessed: $now, created_at: $now,
                    scope: 'personal', source_type: 'document', owner_id: 'agent_a'
                })
            """, uuid=entity_uuid, gid=test_prefix, now=now)

        try:
            result = scope_manager.promote_memory(
                entity_uuid, target_scope="tribal",
                promoted_by="test", reason="High salience + multi-agent access"
            )
            assert result['status'] == 'promoted'
            assert result['old_scope'] == 'personal'
            assert result['new_scope'] == 'tribal'

            # Verify in Neo4j
            with neo4j_driver.session() as session:
                record = session.run(
                    "MATCH (n:Entity {uuid: $uuid}) RETURN n.scope AS scope",
                    uuid=entity_uuid,
                ).single()
                assert record['scope'] == 'tribal'
        finally:
            with neo4j_driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) "
                    "OPTIONAL MATCH (n)-[:HAS_REVISION]->(r) "
                    "DETACH DELETE r, n",
                    uuid=entity_uuid,
                )

    def test_cannot_demote_scope(self, scope_manager, test_prefix, neo4j_driver):
        """Cannot promote from tribal to personal (downward)."""
        entity_uuid = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        with neo4j_driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid, graph_id: $gid, name: 'Demote Test',
                    name_lower: 'demote test', salience: 0.9,
                    access_count: 3, last_accessed: $now, created_at: $now,
                    scope: 'tribal'
                })
            """, uuid=entity_uuid, gid=test_prefix, now=now)

        try:
            result = scope_manager.promote_memory(entity_uuid, target_scope="personal")
            assert 'error' in result
        finally:
            with neo4j_driver.session() as session:
                session.run(
                    "MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n",
                    uuid=entity_uuid,
                )

    def test_scope_summary(self, scope_manager):
        """get_scope_summary returns valid structure."""
        summary = scope_manager.get_scope_summary()
        assert 'scopes' in summary
        assert 'source_types' in summary
        assert 'promotion_candidates' in summary


class TestOverviewAPI:
    """Test the dashboard overview data retrieval."""

    def test_memory_overview_structure(self, memory_manager):
        """get_memory_overview returns expected data structure."""
        overview = memory_manager.get_memory_overview()

        assert 'stm' in overview
        assert 'ltm' in overview
        assert 'distribution' in overview
        assert 'config' in overview
        assert 'stats' in overview
        assert 'at_risk' in overview

        assert 'count' in overview['stm']
        assert 'entity_count' in overview['ltm']
        assert 'decay_rate' in overview['config']
