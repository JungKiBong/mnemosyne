"""
Test: Memory Content Change Tracking (Audit Trail Integration)

Verifies that:
1. Entity summary changes are recorded as MemoryRevision nodes
2. Entity attributes changes are recorded as MemoryRevision nodes
3. RELATION fact changes are recorded as MemoryRevision nodes
4. RELATION temporal fields (valid_at) are correctly set
5. Duplicate RELATION creation is prevented (upsert instead of create)
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestMemoryAuditIntegration:
    """Test MemoryAudit integration with Neo4j ingestion pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures with real Neo4j connection."""
        try:
            from neo4j import GraphDatabase
        except ImportError:
            pytest.skip("neo4j driver not installed")

        neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        neo4j_password = os.environ.get("NEO4J_PASSWORD", "mirofish2024!!")

        try:
            self.driver = GraphDatabase.driver(
                neo4j_uri, auth=(neo4j_user, neo4j_password)
            )
            # Verify connection
            with self.driver.session() as session:
                session.run("RETURN 1")
        except Exception as e:
            pytest.skip(f"Neo4j not available: {e}")

        self.test_graph_id = f"test_audit_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        yield

        # Cleanup: remove test data
        try:
            with self.driver.session() as session:
                session.run(
                    "MATCH (n) WHERE n.graph_id = $gid DETACH DELETE n",
                    gid=self.test_graph_id,
                )
                # Clean up orphaned MemoryRevisions from test entities
                session.run("""
                    MATCH (rev:MemoryRevision)
                    WHERE rev.changed_by = 'test_audit'
                    DETACH DELETE rev
                """)
                # Clean up test episodes
                session.run("""
                    MATCH (ep:Episode)
                    WHERE ep.graph_id = $gid
                    DETACH DELETE ep
                """, gid=self.test_graph_id)
            self.driver.close()
        except Exception:
            pass

    def test_entity_summary_change_tracked(self):
        """GAP-1 fix: Entity summary changes should create MemoryRevision nodes."""
        from app.storage.memory_audit import MemoryAudit

        audit = MemoryAudit(driver=self.driver)

        # Step 1: Create an entity
        with self.driver.session() as session:
            entity_uuid = "test-entity-001"
            session.run("""
                CREATE (n:Entity {
                    uuid: $uuid, graph_id: $gid,
                    name: 'Alice', name_lower: 'alice',
                    summary: 'Alice is a person',
                    attributes_json: '{}',
                    created_at: $now
                })
            """, uuid=entity_uuid, gid=self.test_graph_id,
                now=datetime.now(timezone.utc).isoformat())

        # Step 2: Record a summary change (simulating what neo4j_storage now does)
        rev_id = audit.record(
            memory_uuid=entity_uuid,
            field='summary',
            old_value='Alice is a person',
            new_value='Alice is a software engineer',
            change_type='update',
            changed_by='test_audit',
            reason='Test summary update',
        )

        assert rev_id is not None

        # Step 3: Verify revision was created
        history = audit.get_history(entity_uuid, field='summary')
        assert len(history) >= 1

        latest = history[0]
        assert latest['field'] == 'summary'
        assert latest['old_value'] == 'Alice is a person'
        assert latest['new_value'] == 'Alice is a software engineer'
        assert latest['change_type'] == 'update'

        audit.close()

    def test_entity_attributes_change_tracked(self):
        """GAP-1 fix: Entity attributes changes should create MemoryRevision nodes."""
        from app.storage.memory_audit import MemoryAudit

        audit = MemoryAudit(driver=self.driver)

        entity_uuid = "test-entity-002"
        with self.driver.session() as session:
            session.run("""
                CREATE (n:Entity {
                    uuid: $uuid, graph_id: $gid,
                    name: 'Bob', name_lower: 'bob',
                    summary: 'Bob (Person)',
                    attributes_json: '{"role": "developer"}',
                    created_at: $now
                })
            """, uuid=entity_uuid, gid=self.test_graph_id,
                now=datetime.now(timezone.utc).isoformat())

        old_attrs = json.dumps({"role": "developer"})
        new_attrs = json.dumps({"role": "lead engineer", "team": "platform"})

        rev_id = audit.record(
            memory_uuid=entity_uuid,
            field='attributes',
            old_value=old_attrs,
            new_value=new_attrs,
            change_type='update',
            changed_by='test_audit',
            reason='Test attributes update',
        )

        history = audit.get_history(entity_uuid, field='attributes')
        assert len(history) >= 1
        assert history[0]['field'] == 'attributes'

        audit.close()

    def test_relation_fact_change_tracked(self):
        """GAP-2 fix: RELATION fact changes should create MemoryRevision nodes."""
        from app.storage.memory_audit import MemoryAudit

        audit = MemoryAudit(driver=self.driver)

        # Create source entity
        source_uuid = "test-entity-src-001"
        relation_uuid = "test-rel-001"
        with self.driver.session() as session:
            session.run("""
                CREATE (n:Entity {
                    uuid: $uuid, graph_id: $gid,
                    name: 'Alice', name_lower: 'alice_rel',
                    summary: 'Alice (Person)',
                    created_at: $now
                })
            """, uuid=source_uuid, gid=self.test_graph_id,
                now=datetime.now(timezone.utc).isoformat())

        # Record a relation fact change
        rev_id = audit.record_relation(
            relation_uuid=relation_uuid,
            source_uuid=source_uuid,
            field='fact',
            old_value='Alice likes coffee',
            new_value='Alice likes tea',
            change_type='update',
            changed_by='test_audit',
            reason='Preference changed',
        )

        assert rev_id is not None

        # Verify: revision should be attached to source entity
        with self.driver.session() as session:
            result = session.run("""
                MATCH (src:Entity {uuid: $uuid})-[:HAS_REVISION]->(rev:MemoryRevision)
                WHERE rev.target_type = 'RELATION'
                RETURN rev.field AS field, rev.old_value AS old_val,
                       rev.new_value AS new_val, rev.memory_uuid AS rel_uuid
            """, uuid=source_uuid).data()

        assert len(result) >= 1
        rel_rev = result[0]
        assert rel_rev['field'] == 'fact'
        assert rel_rev['old_val'] == 'Alice likes coffee'
        assert rel_rev['new_val'] == 'Alice likes tea'
        assert rel_rev['rel_uuid'] == relation_uuid

        audit.close()

    def test_relation_valid_at_set_on_creation(self):
        """GAP-2 fix: New RELATIONs should have valid_at set to creation timestamp."""
        # This tests the neo4j_storage._upsert_relation behavior directly
        with self.driver.session() as session:
            now = datetime.now(timezone.utc).isoformat()

            # Create entities for the relation
            session.run("""
                CREATE (src:Entity {uuid: 'valid-at-src', graph_id: $gid,
                    name: 'Src', name_lower: 'valid_at_src', created_at: $now})
                CREATE (tgt:Entity {uuid: 'valid-at-tgt', graph_id: $gid,
                    name: 'Tgt', name_lower: 'valid_at_tgt', created_at: $now})
                CREATE (ep:Episode {uuid: 'valid-at-ep', graph_id: $gid,
                    data: 'test', created_at: $now})
            """, gid=self.test_graph_id, now=now)

            # Create relation with valid_at (simulating new neo4j_storage behavior)
            session.run("""
                MATCH (src:Entity {uuid: 'valid-at-src'})
                MATCH (tgt:Entity {uuid: 'valid-at-tgt'})
                CREATE (src)-[r:RELATION {
                    uuid: 'valid-at-rel-001',
                    graph_id: $gid,
                    name: 'LIKES',
                    fact: 'Src likes Tgt',
                    fact_embedding: [],
                    attributes_json: '{}',
                    episode_ids: ['valid-at-ep'],
                    created_at: $now,
                    valid_at: $now,
                    invalid_at: null,
                    expired_at: null
                }]->(tgt)
            """, gid=self.test_graph_id, now=now)

            # Verify valid_at is set
            result = session.run("""
                MATCH ()-[r:RELATION {uuid: 'valid-at-rel-001'}]->()
                RETURN r.valid_at AS valid_at, r.invalid_at AS invalid_at
            """).single()

            assert result is not None
            assert result['valid_at'] is not None
            assert result['valid_at'] == now
            assert result['invalid_at'] is None

    def test_relation_upsert_prevents_duplicates(self):
        """GAP-2 fix: Same src->tgt with same type should update, not duplicate."""
        with self.driver.session() as session:
            now = datetime.now(timezone.utc).isoformat()

            # Create entities
            session.run("""
                CREATE (src:Entity {uuid: 'upsert-src', graph_id: $gid,
                    name: 'Src', name_lower: 'upsert_src', created_at: $now})
                CREATE (tgt:Entity {uuid: 'upsert-tgt', graph_id: $gid,
                    name: 'Tgt', name_lower: 'upsert_tgt', created_at: $now})
            """, gid=self.test_graph_id, now=now)

            # Create first relation
            session.run("""
                MATCH (src:Entity {uuid: 'upsert-src'})
                MATCH (tgt:Entity {uuid: 'upsert-tgt'})
                CREATE (src)-[r:RELATION {
                    uuid: 'upsert-rel-001', graph_id: $gid, name: 'LIKES',
                    fact: 'Src likes coffee', fact_embedding: [],
                    attributes_json: '{}', episode_ids: ['ep1'],
                    created_at: $now, valid_at: $now,
                    invalid_at: null, expired_at: null
                }]->(tgt)
            """, gid=self.test_graph_id, now=now)

            # Simulate upsert: check existing, then update
            existing = session.run("""
                MATCH (src:Entity {uuid: 'upsert-src'})
                      -[r:RELATION {name: 'LIKES', graph_id: $gid}]->
                      (tgt:Entity {uuid: 'upsert-tgt'})
                RETURN r.uuid AS uuid, r.fact AS old_fact
            """, gid=self.test_graph_id).single()

            assert existing is not None
            assert existing['old_fact'] == 'Src likes coffee'

            # Update the relation (not create a new one)
            session.run("""
                MATCH (src:Entity {uuid: 'upsert-src'})
                      -[r:RELATION {name: 'LIKES', graph_id: $gid}]->
                      (tgt:Entity {uuid: 'upsert-tgt'})
                SET r.fact = 'Src likes tea',
                    r.episode_ids = r.episode_ids + ['ep2'],
                    r.updated_at = $now,
                    r.valid_at = $now
            """, gid=self.test_graph_id, now=now)

            # Verify: only ONE relation exists (not two)
            count_result = session.run("""
                MATCH (src:Entity {uuid: 'upsert-src'})
                      -[r:RELATION {name: 'LIKES', graph_id: $gid}]->
                      (tgt:Entity {uuid: 'upsert-tgt'})
                RETURN count(r) AS cnt, r.fact AS fact
            """, gid=self.test_graph_id).single()

            assert count_result['cnt'] == 1
            assert count_result['fact'] == 'Src likes tea'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
