"""
Orchestrator Service
Manages long-running multi-agent execution loops (Phase 3 Blackboard)
"""

import logging
from typing import Dict, Any, List, Optional
from ..storage.orchestration_storage import OrchestrationStorage

logger = logging.getLogger("mirofish.orchestrator_service")


class OrchestratorService:
    """Business logic for interacting with the Mories execution Blackboard."""

    def __init__(self, storage: Optional[OrchestrationStorage] = None):
        self.storage = storage or OrchestrationStorage()

    def start_session(self, graph_id: str, name: str, goal: str) -> str:
        """Starts a new Multi-Agent Orchestration Session."""
        logger.info(f"Starting orchestration session '{name}' in graph {graph_id}")
        return self.storage.create_session(graph_id, name, goal)

    def end_session(self, graph_id: str, session_id: str, status: str = "completed"):
        """Ends a session."""
        logger.info(f"Ending session {session_id} with status {status}")
        self.storage.finish_session(graph_id, session_id, status)

    def queue_task(self, graph_id: str, session_id: str, name: str, description: str, context_uuids: List[str] = None) -> str:
        """Manager Agent creates a task on the blackboard."""
        logger.info(f"Queueing task '{name}' for session {session_id}")
        return self.storage.create_task(graph_id, session_id, name, description, context_uuids)

    def mark_task_in_progress(self, graph_id: str, task_id: str, agent_id: str):
        """Builder Agent picks up a task."""
        msg = f"Picked up by {agent_id}"
        self.storage.update_task_status(graph_id, task_id, "processing", msg)

    def complete_task(self, graph_id: str, task_id: str, review_message: str = ""):
        """Expert Agent marks task as done."""
        self.storage.update_task_status(graph_id, task_id, "completed", review_message)

    def block_task_with_error(self, graph_id: str, task_id: str, error_msg: str, traceback: str = "") -> str:
        """Logs an error block on a task."""
        logger.error(f"Task {task_id} blocked: {error_msg}")
        self.storage.update_task_status(graph_id, task_id, "failed", error_msg)
        return self.storage.log_error(graph_id, task_id, error_msg, traceback)

    def get_task_execution_context(self, graph_id: str, task_id: str) -> Dict[str, Any]:
        """Task-Driven Context Retrieval for Agents to read before executing."""
        return self.storage.get_task_context(graph_id, task_id)

    def get_board(self, graph_id: str) -> List[Dict]:
        """Provides a dashboard view of active tasks."""
        return self.storage.get_active_tasks(graph_id)
