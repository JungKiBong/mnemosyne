import asyncio
import json
import os
import sys
import ray

from src.app.harness.orchestration.harness_orchestrator import HarnessOrchestrator

def main():
    # Connect to the remote Ray cluster
    # We can use the connection string as ray://192.168.35.101:10001
    ray_address = os.environ.get("RAY_ADDRESS", "ray://192.168.35.101:10001")
    print(f"Connecting to Ray cluster at {ray_address}...")
    ray.init(address=ray_address, ignore_reinit_error=True)
    
    print("Ray connected successfully:")
    print("Available resources:", ray.cluster_resources())

    scenario_path = "tests/fixtures/v4_scenario_complex.json"
    with open(scenario_path, "r") as f:
        data = json.load(f)
        
    orchestrator = HarnessOrchestrator(initial_workflow=data)
    
    print(f"\nStarting execution for scenario: {data.get('scenario_id')}")
    # Force the orchestrator to know it uses the cluster
    # Depending on Harness implementation, it may automatically use Ray if initialized.
    
    result = orchestrator.run_with_auto_heal()
    
    run_id = result.get('run_id')
    print(f"\nExecution completed! Run ID: {run_id}")
    print(f"Success: {result.get('success')}")
    
    # Retrieve execution tree
    if hasattr(orchestrator, "memory_bridge") and orchestrator.memory_bridge is not None:
        if hasattr(orchestrator.memory_bridge, "backend") and hasattr(orchestrator.memory_bridge.backend, "get_execution_tree"):
            tree = orchestrator.memory_bridge.backend.get_execution_tree(run_id)
            if tree:
                print("\nExecution Tree summary:")
                print(json.dumps(tree, indent=2))
        
if __name__ == "__main__":
    main()
