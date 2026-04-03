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


def test_harness_recommend(memory_category_manager, neo4j_driver):
    """Test AI-powered harness recommendation by keyword relevance."""
    domain = "test_recommend"

    # Create two harnesses with different triggers
    r1 = memory_category_manager.record_harness(
        domain=domain,
        trigger="PR review automation with code analysis",
        tool_chain=[{"tool_name": "grep_search"}, {"tool_name": "read_file"}],
        description="Review pull requests automatically",
        tags=["review", "automation"],
    )
    r2 = memory_category_manager.record_harness(
        domain=domain,
        trigger="deploy production server monitoring",
        tool_chain=[{"tool_name": "run_command"}, {"tool_name": "health_check"}],
        description="Deploy and monitor production servers",
        tags=["deploy", "monitoring"],
    )

    try:
        # Search for "review" should match r1 preferentially
        results = memory_category_manager.recommend_harness(query="code review automation")
        assert len(results) > 0
        # The review-related harness should appear
        found_uuids = [r["uuid"] for r in results]
        assert r1["uuid"] in found_uuids, f"Expected {r1['uuid']} in {found_uuids}"

        # Search for "deploy" should match r2
        results2 = memory_category_manager.recommend_harness(query="deploy server")
        found_uuids2 = [r["uuid"] for r in results2]
        assert r2["uuid"] in found_uuids2

        # Unrelated search should return empty or not match
        results3 = memory_category_manager.recommend_harness(query="quantum computing")
        assert r1["uuid"] not in [r["uuid"] for r in results3]

    finally:
        with neo4j_driver.session() as session:
            session.run("MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n", uuid=r1["uuid"])
            session.run("MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n", uuid=r2["uuid"])


def test_harness_rollback(memory_category_manager, neo4j_driver):
    """Test manual rollback to a specific harness version."""
    domain = "test_rollback"
    original_chain = [{"tool_name": "step_a"}]

    result = memory_category_manager.record_harness(
        domain=domain,
        trigger="rollback test",
        tool_chain=original_chain,
    )
    harness_uuid = result["uuid"]

    try:
        # Evolve to v2
        memory_category_manager.evolve_harness(
            harness_uuid=harness_uuid,
            new_tool_chain=[{"tool_name": "step_a"}, {"tool_name": "step_b"}],
            change_reason="Add step B",
        )

        # Verify v2
        h = memory_category_manager.recall_harness(harness_uuid=harness_uuid)[0]
        assert h["version"] == 2
        assert len(h["tool_chain"]) == 2

        # Rollback to v1
        rb_result = memory_category_manager.rollback_harness(
            harness_uuid=harness_uuid,
            to_version=1,
        )
        assert rb_result["status"] == "rolled_back"
        assert rb_result["from_version"] == 2
        assert rb_result["to_version"] == 1
        assert rb_result["new_version"] == 3

        # Verify rolled-back state
        h2 = memory_category_manager.recall_harness(harness_uuid=harness_uuid)[0]
        assert h2["version"] == 3
        assert len(h2["tool_chain"]) == 1  # Back to original

        # Verify evolution history
        compare = memory_category_manager.compare_harness_versions(harness_uuid)
        assert compare["total_versions"] == 3
        assert "rollback" in compare["version_b"]["change_reason"].lower()

    finally:
        with neo4j_driver.session() as session:
            session.run("MATCH (n:Entity {uuid: $uuid}) DETACH DELETE n", uuid=harness_uuid)
