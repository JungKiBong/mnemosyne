import pytest
from src.app.harness.harness_runtime import HarnessRuntime
from src.app.harness.planner.ooda import AutonomousPlanner

def test_ooda_loop_injects_steps(tmp_path):
    # Dummy workflow with one valid step. 
    # Use 'wait' instead of 'code' to easily mock execution without side effects.
    workflow = {
        "harness_id": "test_ooda_harness",
        "domain": "test",
        "state_storage": {"type": "json_file", "path": str(tmp_path)},
        "steps": [
            {
                "id": "step1",
                "type": "wait",
                "timeout_seconds": 0
            }
        ]
    }
    
    runtime = HarnessRuntime(workflow)
    
    # Run the engine initially
    runtime.run()
    
    # Check that only 1 step was run
    assert len(runtime._execution_log) == 1
    assert runtime._execution_log[0]["step_id"] == "step1"
    
    import uuid
    def mock_llm_provider(orientation):
        return [{
            "id": f"auto_fix_step_{uuid.uuid4().hex[:6]}",
            "type": "wait",
            "timeout_seconds": 0
        }]
        
    # Setup OODA planner with mock LLM provider
    planner = AutonomousPlanner(agent_registry=None, llm_provider=mock_llm_provider)
    
    # Run loop with a goal that triggers our mock LLM to branch/inject a step
    planner.run_loop(runtime, goal="We need to fix the deployment.")
    
    # The planner should have appended a new step containing "auto_fix_step_"
    new_step_id = runtime.step_order[-1]
    assert new_step_id.startswith("auto_fix_step_")
    assert new_step_id in runtime.steps
    
    # Running runtime again (with resume) should execute the new step
    # Reset current_idx is tricky because state_mgr deletes state on success.
    # We can just manually call _execute_step or re-run by clearing the execution tree.
    # Instead of full resume, we just run the newly appended step directly to verify.
    runtime._execute_step(runtime.steps[new_step_id], len(runtime.step_order)-1)
    
    # Total execution log should now be 2
    assert len(runtime._execution_log) == 2
    assert runtime._execution_log[-1]["step_id"] == new_step_id
    assert runtime._execution_log[-1]["success"] is True
