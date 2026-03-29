"""
Orchestrator Service
Manages long-running multi-agent execution loops (Phase 3 Blackboard).
"""

import logging
from typing import Dict, Any, List, Optional
from ..storage.orchestration_storage import OrchestrationStorage

logger = logging.getLogger("mirofish.orchestrator_service")


class OrchestratorService:
    """Business logic for the Mories execution Blackboard."""

    def __init__(self, storage: Optional[OrchestrationStorage] = None):
        self._owns_storage = storage is None
        self.storage = storage or OrchestrationStorage()

    def close(self):
        if self._owns_storage and self.storage:
            self.storage.close()
            self.storage = None

    def create_session(self, graph_id: str, name: str, goal: str) -> str:
        logger.info("Starting session '%s' in graph %s", name, graph_id)
        return self.storage.create_session(graph_id, name, goal)

    start_session = create_session

    def end_session(self, graph_id: str, session_id: str, status: str = "completed"):
        logger.info("Ending session %s with status %s", session_id, status)
        self.storage.finish_session(graph_id, session_id, status)

    def complete_session(self, graph_id: str, session_id: str):
        self.end_session(graph_id, session_id, "completed")

    def queue_task(self, graph_id: str, session_id: str, name: str,
                   description: str, context_uuids: List[str] = None) -> str:
        logger.info("Queueing task '%s' for session %s", name, session_id)
        return self.storage.create_task(graph_id, session_id, name, description, context_uuids)

    def mark_task_in_progress(self, graph_id: str, task_id: str, agent_id: str):
        self.storage.update_task_status(graph_id, task_id, "processing", f"Picked up by {agent_id}")

    def complete_task(self, graph_id: str, task_id: str, message: str = ""):
        self.storage.update_task_status(graph_id, task_id, "completed", message)

    def block_task_with_error(self, graph_id: str, task_id: str,
                              error_msg: str, traceback_text: str = "") -> str:
        logger.error("Task %s blocked: %s", task_id, error_msg)
        self.storage.update_task_status(graph_id, task_id, "failed", error_msg)
        return self.storage.log_error(graph_id, task_id, error_msg, traceback_text)

    def get_task_execution_context(self, graph_id: str, task_id: str) -> Dict[str, Any]:
        return self.storage.get_task_context(graph_id, task_id)

    def get_pending_tasks(self, graph_id: str) -> List[Dict]:
        return self.storage.get_active_tasks(graph_id)

    def get_board(self, graph_id: str) -> List[Dict]:
        return self.storage.get_all_tasks(graph_id)
