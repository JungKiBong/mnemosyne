import asyncio
import json
import os
import sys

from src.app.harness.orchestration.harness_orchestrator import HarnessOrchestrator

def main():
    scenario_path = "tests/fixtures/v4_scenario_complex.json"
    with open(scenario_path, "r") as f:
        data = json.load(f)
        
    orchestrator = HarnessOrchestrator(initial_workflow=data)
    
    print(f"Starting execution for scenario: {data.get('scenario_id')}")
    result = orchestrator.run_with_auto_heal()
    
    run_id = result.get('run_id')
    print(f"\nExecution completed! Run ID: {run_id}")
    print(f"Success: {result.get('success')}")
    
    # Retrieve execution tree
    tree = orchestrator.memory_bridge.backend.get_execution_tree(run_id) if hasattr(orchestrator.memory_bridge, "backend") and hasattr(orchestrator.memory_bridge.backend, "get_execution_tree") else None
    
    if tree:
        print("\nExecution Tree summary:")
        print(json.dumps(tree, indent=2))
        
if __name__ == "__main__":
    main()

