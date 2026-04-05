"""Tests for HITL (Human-in-the-Loop) logic."""
import os
import pytest
from src.app.harness.harness_runtime import HarnessRuntime

@pytest.fixture
def hitl_workflow():
    return {
        "harness_id": "test_hitl",
        "domain": "test",
        "state_storage": {"type": "json_file", "path": "/tmp/hitl_test"},
        "steps": [
            {
                "id": "step1",
                "type": "wait",
                "timeout_seconds": 0
            },
            {
                "id": "approval_gate",
                "type": "hitl_gate",
                "prompt": "Approve this workflow?",
                "allowed_actions": ["approve", "reject"]
            },
            {
                "id": "step3",
                "type": "wait",
                "timeout_seconds": 0
            }
        ]
    }

def test_hitl_suspends_and_resumes(hitl_workflow):
    runtime = HarnessRuntime(hitl_workflow)
    
    # 1. First run should execute step1, and suspend at approval_gate
    res1 = runtime.run()
    assert res1["success"] is True
    assert res1["status"] == "suspended"
    assert res1["suspended_at"] == "approval_gate"
    assert "prompt" in res1["prompt"]
    assert res1["prompt"]["prompt"] == "Approve this workflow?"
    
    # Checkpoint should have advanced to step 1 (idx 1)
    
    # 2. Emulate user providing an answer asynchronously
    runtime.context.setdefault("hitl_responses", {})["approval_gate"] = {"action": "approve"}
    
    # 3. Resume run
    res2 = runtime.run(resume=True)
    assert res2.get("status") != "suspended"  # Should complete fully
    # step3 should have run
