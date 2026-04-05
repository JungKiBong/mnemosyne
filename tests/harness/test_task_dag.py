import pytest
from src.app.harness.planner.task_dag import TaskDAG

def test_task_dag_resolution():
    dag = TaskDAG()
    
    # Step 1: No dependencies
    dag.add_step({"id": "step1", "requires": []})
    
    # Step 2: Depends on step1
    dag.add_step({"id": "step2", "requires": ["step1"]})
    
    # Step 3: Depends on step1
    dag.add_step({"id": "step3", "requires": ["step1"]})
    
    # Step 4: Depends on step2 and step3
    dag.add_step({"id": "step4", "requires": ["step2", "step3"]})
    
    dag.build_edges()
    
    # Initially, only step1 is ready
    completed = set()
    ready = dag.get_ready_steps(completed)
    assert len(ready) == 1
    assert ready[0]["id"] == "step1"
    
    # Complete step1
    completed.add("step1")
    ready = dag.get_ready_steps(completed)
    assert len(ready) == 2
    ready_ids = {s["id"] for s in ready}
    assert "step2" in ready_ids
    assert "step3" in ready_ids
    
    # Complete step2
    completed.add("step2")
    ready = dag.get_ready_steps(completed)
    assert len(ready) == 1
    assert ready[0]["id"] == "step3"
    
    # Complete step3
    completed.add("step3")
    ready = dag.get_ready_steps(completed)
    assert len(ready) == 1
    assert ready[0]["id"] == "step4"
    
    # Complete step4
    completed.add("step4")
    assert dag.is_complete(completed) is True
    ready = dag.get_ready_steps(completed)
    assert len(ready) == 0
