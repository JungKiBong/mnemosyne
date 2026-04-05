import pytest
from src.app.harness.orchestration.memory_bridge import (
    MemoryBridge,
    HarnessExperience,
    ExperienceType
)

class MockMemoryBackend:
    def __init__(self):
        self.instructions = []

    def record_instruction(self, category, rule, description, strictness):
        item = {
            "category": category,
            "rule": rule,
            "description": description,
            "strictness": strictness
        }
        self.instructions.append(item)
        return {"status": "saved", "item": item}

def test_human_feedback_memory_bridge():
    backend = MockMemoryBackend()
    bridge = MemoryBridge(memory_backend=backend)
    
    # Create a HUMAN_CORRECTED experience
    exp = HarnessExperience(
        harness_id="test_hitl_harness",
        domain="core",
        run_id="run_001",
        experience_type=ExperienceType.HUMAN_CORRECTED,
        tool_chain=["hitl_gate", "code"],
        elapsed_ms=1000,
        summary="Always ensure deployment region is us-east-1"
    )
    
    res = bridge.publish(exp)
    
    # Verify the action was logged correctly
    assert res["status"] == "published"
    assert len(res["actions"]) == 1
    assert res["actions"][0]["action"] == "human_feedback"
    
    # Verify backend received the instruction
    assert len(backend.instructions) == 1
    instr = backend.instructions[0]
    assert instr["category"] == "human_feedback"
    assert instr["rule"] == "Always ensure deployment region is us-east-1"
    assert instr["strictness"] == "must"
    assert "test_hitl_harness" in instr["description"]
