import logging
from typing import List, Dict, Any, Set

logger = logging.getLogger(__name__)

class TaskNode:
    def __init__(self, step_definition: Dict[str, Any]):
        self.step_definition = step_definition
        self.step_id = step_definition["id"]
        # Determine dependencies from explicit 'requires' list or dynamically if needed in future
        self.requires: List[str] = step_definition.get("requires", [])
        self.children: List[str] = []

    def __repr__(self) -> str:
        return f"TaskNode(id={self.step_id}, requires={self.requires}, children={self.children})"


class TaskDAG:
    """
    Directed Acyclic Graph (DAG) representation of workflow steps.
    Used for dependency resolution and execution planning.
    """
    def __init__(self):
        self.nodes: Dict[str, TaskNode] = {}
        
    def add_step(self, step: Dict[str, Any]):
        node = TaskNode(step)
        if node.step_id in self.nodes:
            logger.warning(f"Step {node.step_id} already exists in DAG. Overwriting.")
        self.nodes[node.step_id] = node
        
    def build_edges(self):
        """Rebuild child relationships based on node requirements."""
        # Reset children
        for node in self.nodes.values():
            node.children = []
            
        for node in self.nodes.values():
            for req in node.requires:
                if req in self.nodes:
                    self.nodes[req].children.append(node.step_id)
                else:
                    logger.warning(f"Step {node.step_id} requires missing step: {req}")
                    
    def get_ready_steps(self, completed_steps: Set[str]) -> List[Dict[str, Any]]:
        """Return steps that have all prerequisites met and are not completed."""
        ready = []
        for node in self.nodes.values():
            if node.step_id not in completed_steps:
                if all(req in completed_steps for req in node.requires):
                    ready.append(node.step_definition)
        return ready

    def is_complete(self, completed_steps: Set[str]) -> bool:
        """Check if all nodes in the DAG have been completed."""
        return len(completed_steps) >= len(self.nodes)
