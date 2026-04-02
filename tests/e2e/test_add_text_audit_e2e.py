"""
End-to-End Test: Verify neo4j_storage.add_text() now creates MemoryRevision
for Entity summary changes and RELATION fact updates through the NER pipeline.

This is the critical test that validates GAP-1/2/3 are truly closed —
testing through the real add_text() codepath, not just individual methods.
"""

import json
import pytest
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestAddTextAuditTrail:
    """E2E: add_text() → NER → MERGE → MemoryAudit pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup with real Neo4j and mocked NER (to control exact entities/relations)."""
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
            with self.driver.session() as session:
                session.run("RETURN 1")
        except Exception as e:
            pytest.skip(f"Neo4j not available: {e}")

        self.test_graph_id = f"test_e2e_audit_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Create the graph node
        with self.driver.session() as session:
            session.run("""
                CREATE (g:Graph {
                    graph_id: $gid,
                    name: 'E2E Audit Test',
                    created_at: $now
                })
            """, gid=self.test_graph_id,
                now=datetime.now(timezone.utc).isoformat())

        yield

        # Cleanup
        try:
            with self.driver.session() as session:
                # Remove all test nodes (entities, episodes, revisions, graph)
                session.run("""
                    MATCH (n)
                    WHERE n.graph_id = $gid
                    OPTIONAL MATCH (n)-[:HAS_REVISION]->(rev:MemoryRevision)
                    DETACH DELETE rev, n
                """, gid=self.test_graph_id)
                session.run("""
                    MATCH (g:Graph {graph_id: $gid}) DETACH DELETE g
                """, gid=self.test_graph_id)
            self.driver.close()
        except Exception:
            pass

    def _create_storage_with_mock_ner(self, ner_returns):
        """Create a Neo4jStorage with a mocked NER extractor."""
        from unittest.mock import MagicMock
        from app.storage.neo4j_storage import Neo4jStorage
        from app.storage.embedding_service import EmbeddingService

        mock_ner = MagicMock()
        mock_ner.extract.return_value = ner_returns

        mock_embedding = MagicMock(spec=EmbeddingService)
        mock_embedding.embed_batch.return_value = [
            [0.0] * 768 for _ in range(100)  # dummy embeddings
        ]

        storage = Neo4jStorage(
            uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", "mirofish2024!!"),
            embedding_service=mock_embedding,
            ner_extractor=mock_ner,
        )

        return storage

    def test_entity_summary_audit_on_second_ingestion(self):
        """
        Scenario: Same entity ingested twice with different type/summary.
        Expected: MemoryRevision created for summary change.
        
        Note: summary_text is auto-generated as "{name} ({type})" in add_text(),
        so we change the entity type to produce a different summary.
        """
        # First ingestion: Alice as Person → summary = "Alice (Person)"
        ner_result_1 = {
            "entities": [
                {"name": "Alice", "type": "Person", "attributes": {"role": "student"}}
            ],
            "relations": [],
        }
        storage = self._create_storage_with_mock_ner(ner_result_1)
        storage.add_text(self.test_graph_id, "Alice is a student.")

        # Second ingestion: Alice as Engineer → summary = "Alice (Engineer)"
        ner_result_2 = {
            "entities": [
                {"name": "Alice", "type": "Engineer", "attributes": {"role": "engineer"}}
            ],
            "relations": [],
        }
        storage._ner.extract.return_value = ner_result_2
        storage.add_text(self.test_graph_id, "Alice is now an engineer.")

        # Verify: MemoryRevision exists for summary change
        with self.driver.session() as session:
            revisions = session.run("""
                MATCH (n:Entity {graph_id: $gid, name_lower: 'alice'})
                      -[:HAS_REVISION]->(rev:MemoryRevision)
                WHERE rev.field = 'summary'
                RETURN rev.old_value AS old_val, rev.new_value AS new_val,
                       rev.change_type AS change_type, rev.changed_by AS changed_by
                ORDER BY rev.changed_at DESC
            """, gid=self.test_graph_id).data()

        assert len(revisions) >= 1, (
            f"Expected at least 1 summary revision, got {len(revisions)}. "
            "This means GAP-1 is NOT fixed."
        )
        latest = revisions[0]
        assert latest['change_type'] == 'update'
        assert latest['changed_by'] == 'ner_ingestion'
        assert 'Person' in latest['old_val']
        assert 'Engineer' in latest['new_val']

        storage.close()

    def test_relation_upsert_and_audit_on_second_ingestion(self):
        """
        Scenario: Same relation (Alice->Coffee, LIKES) ingested twice with changed fact.
        Expected:
        - Only ONE RELATION exists (upserted, not duplicated)
        - MemoryRevision created for fact change
        - valid_at is set (not null)
        """
        # First ingestion
        ner_result_1 = {
            "entities": [
                {"name": "Alice", "type": "Person", "attributes": {}},
                {"name": "Coffee", "type": "Beverage", "attributes": {}},
            ],
            "relations": [
                {"source": "Alice", "target": "Coffee", "type": "LIKES",
                 "fact": "Alice likes coffee very much"}
            ],
        }
        storage = self._create_storage_with_mock_ner(ner_result_1)
        storage.add_text(self.test_graph_id, "Alice likes coffee very much.")

        # Second ingestion: Alice now prefers tea over coffee
        ner_result_2 = {
            "entities": [
                {"name": "Alice", "type": "Person", "attributes": {}},
                {"name": "Coffee", "type": "Beverage", "attributes": {}},
            ],
            "relations": [
                {"source": "Alice", "target": "Coffee", "type": "LIKES",
                 "fact": "Alice used to like coffee but now prefers tea"}
            ],
        }
        storage._ner.extract.return_value = ner_result_2
        storage.add_text(self.test_graph_id, "Alice now prefers tea.")

        with self.driver.session() as session:
            # Verify: only ONE RELATION exists (upsert, not duplicate)
            rel_count = session.run("""
                MATCH (a:Entity {name_lower: 'alice', graph_id: $gid})
                      -[r:RELATION {name: 'LIKES'}]->
                      (c:Entity {name_lower: 'coffee', graph_id: $gid})
                RETURN count(r) AS cnt
            """, gid=self.test_graph_id).single()

            assert rel_count['cnt'] == 1, (
                f"Expected 1 RELATION, got {rel_count['cnt']}. "
                "GAP-2 (upsert) is NOT fixed."
            )

            # Verify: valid_at is set (not null)
            rel_data = session.run("""
                MATCH (a:Entity {name_lower: 'alice', graph_id: $gid})
                      -[r:RELATION {name: 'LIKES'}]->
                      (c:Entity {name_lower: 'coffee', graph_id: $gid})
                RETURN r.valid_at AS valid_at, r.fact AS fact,
                       size(r.episode_ids) AS episode_count
            """, gid=self.test_graph_id).single()

            assert rel_data['valid_at'] is not None, (
                "RELATION.valid_at is null. Temporal tracking NOT active."
            )
            assert rel_data['fact'] == 'Alice used to like coffee but now prefers tea'
            assert rel_data['episode_count'] == 2  # linked to both episodes

            # Verify: MemoryRevision for fact change
            revisions = session.run("""
                MATCH (a:Entity {name_lower: 'alice', graph_id: $gid})
                      -[:HAS_REVISION]->(rev:MemoryRevision)
                WHERE rev.target_type = 'RELATION' AND rev.field = 'fact'
                RETURN rev.old_value AS old_val, rev.new_value AS new_val,
                       rev.change_type AS change_type
            """, gid=self.test_graph_id).data()

            assert len(revisions) >= 1, (
                f"Expected at least 1 RELATION fact revision, got {len(revisions)}. "
                "GAP-2 (audit) is NOT fixed."
            )
            assert 'Alice likes coffee very much' in revisions[0]['old_val']
            assert 'prefers tea' in revisions[0]['new_val']

        storage.close()

    def test_no_audit_when_content_unchanged(self):
        """
        Scenario: Same entity ingested twice with IDENTICAL summary.
        Expected: NO new MemoryRevision created (avoid noise).
        """
        ner_result = {
            "entities": [
                {"name": "Bob", "type": "Person", "attributes": {"age": "30"}}
            ],
            "relations": [],
        }
        storage = self._create_storage_with_mock_ner(ner_result)
        storage.add_text(self.test_graph_id, "Bob is 30 years old.")
        # Ingest again with identical NER output
        storage.add_text(self.test_graph_id, "Bob is 30 years old.")

        with self.driver.session() as session:
            revisions = session.run("""
                MATCH (n:Entity {graph_id: $gid, name_lower: 'bob'})
                      -[:HAS_REVISION]->(rev:MemoryRevision)
                WHERE rev.field = 'summary'
                RETURN count(rev) AS cnt
            """, gid=self.test_graph_id).single()

            # Should be 0 because summary didn't change
            assert revisions['cnt'] == 0, (
                f"Expected 0 summary revisions for unchanged content, got {revisions['cnt']}"
            )

        storage.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
