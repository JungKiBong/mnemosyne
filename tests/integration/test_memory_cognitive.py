import pytest
from src.app import create_app
from src.app.config import Config

@pytest.fixture
def test_app(neo4j_driver, memory_manager):
    class TestConfig(Config):
        TESTING = True
    app = create_app(TestConfig)
    app.extensions['neo4j_driver'] = neo4j_driver
    app.extensions['memory_manager'] = memory_manager
    return app

@pytest.fixture
def client(test_app):
    return test_app.test_client()

def test_synthesis_endpoint(client, memory_manager, neo4j_driver):
    # 1. Create a base memory
    mem = memory_manager.stm_add("Base observation: System crashed due to OOM.")
    result = memory_manager.stm_promote(mem.id)
    ltm_uuid = result['ltm_uuid']
    
    # 2. Call synthesize
    insight = "We must limit concurrent processes to 1."
    res = client.post(f"/api/memory/{ltm_uuid}/synthesize", json={"insight": insight})
    
    assert res.status_code == 201
    data = res.json
    assert data["status"] == "synthesized"
    assert data["content"] == insight
    new_uuid = data["uuid"]
    
    # 3. Verify graph structure SYNTHESIZED_FROM
    with neo4j_driver.session() as session:
        result = session.run(
            "MATCH (n:Memory {uuid: $uuid})-[:SYNTHESIZED_FROM]->(m:Memory {uuid: $source}) RETURN n, m",
            {"uuid": new_uuid, "source": ltm_uuid}
        ).single()
        
        assert result is not None
        assert result["n"]["content"] == insight
        assert result["m"].get("summary") == mem.content

def test_time_travel_chat_missing_params(client, memory_manager):
    # Just testing parameter validation
    mem = memory_manager.stm_add("Test memory")
    result = memory_manager.stm_promote(mem.id)
    ltm_uuid = result['ltm_uuid']
    
    res = client.post(f"/api/memory/{ltm_uuid}/chat", json={})
    assert res.status_code == 400
    assert "error" in res.json
