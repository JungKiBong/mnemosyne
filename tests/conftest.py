"""
conftest.py — Shared fixtures for Mories test suite.

Provides:
  - Flask test client (app fixture)
  - Neo4j session helpers with test isolation
  - MemoryManager / Audit / Scope / Synaptic test instances
"""

import os
import sys
import uuid
import time
import pytest

# Ensure src/ is on PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from app.config import Config


# ──────────────────────────────────────────
# Neo4j Test Helpers
# ──────────────────────────────────────────

def _get_test_driver():
    """Get a Neo4j driver for testing."""
    from neo4j import GraphDatabase
    return GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
    )


def _cleanup_test_entities(driver, test_prefix: str):
    """Delete all entities created by a test run (by graph_id prefix)."""
    with driver.session() as session:
        # Remove test Memory/Entity nodes and their revisions
        session.run("""
            MATCH (n:Entity)
            WHERE n.graph_id STARTS WITH $prefix
            OPTIONAL MATCH (n)-[:HAS_REVISION]->(rev:MemoryRevision)
            DETACH DELETE rev, n
        """, prefix=test_prefix)
        # Remove orphaned MemoryRevision nodes from test
        session.run("""
            MATCH (rev:MemoryRevision)
            WHERE rev.memory_uuid STARTS WITH $prefix
            DETACH DELETE rev
        """, prefix=test_prefix)


# ──────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────

@pytest.fixture(scope="session")
def neo4j_driver():
    """Session-scoped Neo4j driver."""
    driver = _get_test_driver()
    yield driver
    driver.close()


@pytest.fixture
def test_prefix():
    """Unique prefix for test isolation."""
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def flask_app():
    """Create a Flask app for testing."""
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(flask_app):
    """Flask test client."""
    return flask_app.test_client()


@pytest.fixture
def memory_manager():
    """Fresh MemoryManager for each test."""
    from app.storage.memory_manager import MemoryManager, MemoryConfig
    config = MemoryConfig(
        stm_default_ttl=60.0,       # 60s for tests
        stm_max_items=50,
        decay_rate=0.90,            # Aggressive decay for tests
        auto_promote_threshold=0.7,
        auto_discard_threshold=0.3,
    )
    mgr = MemoryManager(config=config)
    yield mgr
    mgr.close()


@pytest.fixture
def memory_audit(neo4j_driver):
    """MemoryAudit instance sharing test driver."""
    from app.storage.memory_audit import MemoryAudit
    audit = MemoryAudit(driver=neo4j_driver)
    yield audit
    # Don't close — driver is session-scoped


@pytest.fixture
def scope_manager(neo4j_driver):
    """MemoryScopeManager instance sharing test driver."""
    from app.storage.memory_scopes import MemoryScopeManager
    mgr = MemoryScopeManager(driver=neo4j_driver)
    yield mgr
    # Don't close — driver is session-scoped


@pytest.fixture
def synaptic_bridge(neo4j_driver):
    """SynapticBridge instance sharing test driver."""
    from app.storage.synaptic_bridge import SynapticBridge
    bridge = SynapticBridge(driver=neo4j_driver)
    yield bridge
    # Don't close — driver is session-scoped
