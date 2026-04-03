"""
End-to-End Test for Reconciliation Service datetime handling.
To verify Neo4j queries involving `datetime()` functions execute
correctly and do not raise Neo4j driver serialization errors.
"""

import json
import pytest
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from src.app.storage.reconciliation_service import ReconciliationService


class TestReconciliationServiceE2E:

    @pytest.fixture(autouse=True)
    def setup(self):
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

        # Seed data for reconciliation tests
        self.test_prefix = f"test_e2e_recon_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        with self.driver.session() as session:
            # Create a stale entity with ISO string
            session.run("""
                CREATE (e:Entity {
                    name: $prefix + "_stale_iso",
                    salience: 0.9,
                    last_accessed: $stale_date
                })
            """, prefix=self.test_prefix,
                stale_date=(datetime.now(timezone.utc) - __import__('datetime').timedelta(days=35)).isoformat())

            # Create an entity with native neo4j DateTime object
            # Pass python datetime which Neo4j driver converts to native
            # Wait, no, we shouldn't necessarily do this if it crashes Neo4j
            session.run("""
                CREATE (e:Entity {
                    name: $prefix + "_stale_native",
                    salience: 0.9,
                    last_accessed: $stale_native_date
                })
            """, prefix=self.test_prefix,
                stale_native_date=(datetime.now(timezone.utc) - __import__('datetime').timedelta(days=32)))
            
            # Create a normal valid entity
            session.run("""
                CREATE (e:Entity {
                    name: $prefix + "_fresh",
                    salience: 0.9,
                    last_accessed: $fresh_date,
                    scope: 'user'
                })
                CREATE (m:MemoryRevision {
                    id: $prefix + "_rev"
                })
                CREATE (e)-[:HAS_REVISION]->(m)
            """, prefix=self.test_prefix,
                fresh_date=datetime.now(timezone.utc).isoformat())

        self.service = ReconciliationService(driver=self.driver, sm_client=None)

        yield

        # Cleanup
        try:
            with self.driver.session() as session:
                session.run("""
                    MATCH (n) WHERE toString(n.name) STARTS WITH $prefix
                    DETACH DELETE n
                """, prefix=self.test_prefix)
                session.run("""
                    MATCH (n:MemoryRevision) WHERE toString(n.id) STARTS WITH $prefix
                    DETACH DELETE n
                """, prefix=self.test_prefix)
        except Exception:
            pass

        self.driver.close()

    def test_reconciliation_quick_check(self):
        """Test quick check with datetime comparisons."""
        result = self.service.quick_check()
        assert "health_score" in result
        assert result["total_memories"] >= 2
        # Should not raise any neo4j errors

    def test_reconciliation_run(self):
        """Test full reconciliation run does not crash on datetime issues."""
        result = self.service.run(auto_fix=False)
        assert result is not None
        assert result.total_checked >= 2
        
        # Verify persistence didn't crash
        history = self.service.get_run_history(limit=1)
        assert len(history) >= 1
        assert history[0]["run_id"] == result.run_id
