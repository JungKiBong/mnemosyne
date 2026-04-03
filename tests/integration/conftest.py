import uuid
import pytest
from neo4j import GraphDatabase

from src.app.config import Config
from src.app.storage.memory_manager import MemoryManager, MemoryConfig
from src.app.storage.memory_scopes import MemoryScopeManager

@pytest.fixture(scope="session")
def neo4j_driver():
    """Session-scoped Neo4j driver for integration tests."""
    driver = GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
    )
    yield driver
    driver.close()

@pytest.fixture
def test_prefix():
    """Returns a unique prefix for isolating graph data in tests."""
    return f"integration_test_{str(uuid.uuid4())[:8]}"

@pytest.fixture
def memory_manager(neo4j_driver):
    """MemoryManager instance with a fast STM default TTL for testing."""
    config = MemoryConfig(stm_default_ttl=2.0)
    # Clear out any existing instance singleton to avoid test pollution
    MemoryManager._instance = None
    mm = MemoryManager.get_instance(driver=neo4j_driver, config=config)
    yield mm
    mm.close()
    MemoryManager._instance = None

@pytest.fixture
def scope_manager(neo4j_driver):
    """MemoryScopeManager instance for scope tests."""
    return MemoryScopeManager(driver=neo4j_driver)
