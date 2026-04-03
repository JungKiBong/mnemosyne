"""
Integration tests for Harness Analytics & Process Patterns.
"""

import pytest
import uuid
from datetime import datetime, timezone

@pytest.fixture
def memory_category_manager(neo4j_driver):
    from app.storage.memory_categories import MemoryCategoryManager
    mgr = MemoryCategoryManager(driver=neo4j_driver)
    yield mgr
    

def test_record_and_list_harness(memory_category_manager, neo4j_driver):
    domain = "test_engineering"
    trigger = "Fix API Error"
    
    tool_chain = [
        {"tool_name": "search_nodes"},
        {"tool_name": "read_file"}
    ]
    conditionals = [
        {"type": "retry", "condition": "search fails", "then_action": "use web"}
    ]
    
    # 1. Record harness
    result = memory_category_manager.record_harness(
        domain=domain,
        trigger=trigger,
        tool_chain=tool_chain,
        description="Standard error fix",
        conditionals=conditionals
    )
    
    assert result["status"] == "created"
    harness_uuid = result["uuid"]
    
    try:
        # 2. List harnesses
        harnesses = memory_category_manager.list_harnesses(domain=domain)
        
        found = False
        for h in harnesses:
            if h["uuid"] == harness_uuid:
                found = True
                assert h["domain"] == domain
                assert h["version"] == 1
                assert h["trigger"] == trigger
                
        assert found
        
        # Verify conditionals via recall
        recalled = memory_category_manager.recall_harness(harness_uuid=harness_uuid)
        assert len(recalled) == 1
        assert len(recalled[0]["conditionals"]) == 1
    finally:
        # Cleanup
        with neo4j_driver.session() as session:
            session.run("MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n", uuid=harness_uuid)


def test_harness_execution(memory_category_manager, neo4j_driver):
    harness_uuid = str(uuid.uuid4())
    domain = "test_execution"
    now = datetime.now(timezone.utc).isoformat()
    
    import json
    meta = json.dumps({
        "category": "harness",
        "harness": {
            "domain": domain,
            "trigger": "test execution",
            "process_type": "pipeline",
            "tool_chain": [{"tool_name": "step1", "tool": "step1", "order": 0}],
            "data_flow": {"input": "", "intermediate": [], "output": ""},
            "tags": [],
            "conditionals": [],
        },
        "stats": {
            "execution_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "avg_execution_time_ms": 0,
            "last_executed": None,
        },
        "evolution": {
            "current_version": 1,
            "history": [{"version": 1, "created_at": now, "tool_chain_hash": "000000000000", "success_rate": 0.0, "change_reason": "initial"}],
        },
        "extraction": {
            "auto_extracted": False,
            "source_log_ids": [],
            "extraction_confidence": 1.0,
            "user_verified": True,
            "source_agent": "system",
        },
    })

    with neo4j_driver.session() as session:
        session.run("""
            CREATE (e:Entity:Memory {
                uuid: $uuid,
                name: 'Test Exec Harness', name_lower: 'test exec harness',
                memory_category: 'harness',
                harness_domain: $domain,
                harness_process_type: 'pipeline',
                harness_version: 1,
                owner_id: 'system',
                scope: 'tribal',
                attributes_json: $meta,
                salience: 0.5,
                access_count: 0, last_accessed: $now, created_at: $now
            })
        """, uuid=harness_uuid, domain=domain, now=now, meta=meta)
        
    try:
        # Record execution success
        exec_res = memory_category_manager.record_harness_execution(harness_uuid, success=True, execution_time_ms=100)
        assert exec_res["status"] == "recorded"
        
        # Verify stats updated
        harnesses = memory_category_manager.recall_harness(harness_uuid=harness_uuid)
        assert len(harnesses) == 1
        h = harnesses[0]
        assert h["stats"]["execution_count"] == 1
        assert h["stats"]["success_rate"] == 1.0
        
    finally:
        with neo4j_driver.session() as session:
            session.run("MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n", uuid=harness_uuid)


def test_harness_evolve(memory_category_manager, neo4j_driver):
    domain = "test_evolve"
    trigger = "Initial task"
    
    tool_chain = [{"tool_name": "step1"}]
    
    # 1. Record harness
    result = memory_category_manager.record_harness(
        domain=domain,
        trigger=trigger,
        tool_chain=tool_chain,
    )
    harness_uuid = result["uuid"]
    
    try:
        # 2. Evolve harness
        new_chain = [{"tool_name": "step1"}, {"tool_name": "step2"}]
        evolve_res = memory_category_manager.evolve_harness(
            harness_uuid=harness_uuid,
            new_tool_chain=new_chain,
            change_reason="Add step 2 for better reliability"
        )
        assert evolve_res["status"] == "evolved"
        
        # 3. Check new version
        harnesses = memory_category_manager.recall_harness(harness_uuid=harness_uuid)
        assert len(harnesses) > 0
        h = harnesses[0]
        assert h["version"] == 2
        assert len(h["tool_chain"]) == 2
    finally:
        with neo4j_driver.session() as session:
            session.run("MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n", uuid=harness_uuid)
