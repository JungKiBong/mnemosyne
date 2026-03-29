"""
Orchestration Blackboard Router
REST APIs for multi-agent Mories state management.

Production-grade: try/except on all handlers, input validation,
shared storage singleton via app.extensions.
"""

import logging
from flask import Blueprint, request, jsonify, current_app

from ..services.orchestrator_service import OrchestratorService
from ..storage.orchestration_storage import VALID_TASK_STATUSES

logger = logging.getLogger("mirofish.api.orchestration")
orchestration_bp = Blueprint('orchestration', __name__)

MAX_NAME_LEN = 256
MAX_DESC_LEN = 10000


def _get_service() -> OrchestratorService:
    """Get OrchestratorService backed by the shared storage singleton."""
    storage = current_app.extensions.get('orchestration_storage')
    return OrchestratorService(storage=storage)


@orchestration_bp.route("/session", methods=["POST"])
def start_session():
    """Starts a new orchestration session."""
    try:
        data = request.get_json(silent=True) or {}
        graph_id = (data.get("graph_id") or "").strip()
        name = (data.get("name") or "").strip()
        goal = (data.get("goal") or "").strip()

        if not all([graph_id, name, goal]):
            return jsonify({"error": "graph_id, name, and goal are required"}), 400
        if len(name) > MAX_NAME_LEN:
            return jsonify({"error": f"name must be <= {MAX_NAME_LEN} chars"}), 400

        svc = _get_service()
        session_id = svc.create_session(graph_id, name, goal)
        return jsonify({"session_id": session_id, "status": "active"})
    except Exception as e:
        logger.exception("Failed to create session")
        return jsonify({"error": str(e)}), 500


@orchestration_bp.route("/session/<session_id>/end", methods=["POST"])
def end_session(session_id: str):
    """Ends an orchestration session."""
    try:
        data = request.get_json(silent=True) or {}
        graph_id = (data.get("graph_id") or "").strip()
        status = (data.get("status") or "completed").strip()

        if not graph_id:
            return jsonify({"error": "graph_id is required"}), 400

        svc = _get_service()
        svc.end_session(graph_id, session_id, status)
        return jsonify({"status": "success"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to end session %s", session_id)
        return jsonify({"error": str(e)}), 500


@orchestration_bp.route("/session/<session_id>/task", methods=["POST"])
def queue_task(session_id: str):
    """Manager agent creates a sub-task."""
    try:
        data = request.get_json(silent=True) or {}
        graph_id = (data.get("graph_id") or "").strip()
        name = (data.get("name") or "").strip()
        description = (data.get("description") or "").strip()
        context_uuids = data.get("context_uuids", [])

        if not all([graph_id, name, description]):
            return jsonify({"error": "graph_id, name, and description are required"}), 400
        if len(name) > MAX_NAME_LEN:
            return jsonify({"error": f"name must be <= {MAX_NAME_LEN} chars"}), 400
        if len(description) > MAX_DESC_LEN:
            return jsonify({"error": f"description must be <= {MAX_DESC_LEN} chars"}), 400

        svc = _get_service()
        task_id = svc.queue_task(graph_id, session_id, name, description, context_uuids)
        return jsonify({"task_id": task_id, "status": "pending"})
    except Exception as e:
        logger.exception("Failed to queue task")
        return jsonify({"error": str(e)}), 500


@orchestration_bp.route("/task/<graph_id>/<task_id>/status", methods=["PATCH"])
def update_task_status(graph_id: str, task_id: str):
    """Update task state (e.g. processing, completed)."""
    try:
        data = request.get_json(silent=True) or {}
        status = (data.get("status") or "").strip()
        message = data.get("message", "")
        agent_id = data.get("agent_id", "")

        if not status:
            return jsonify({"error": "status is required"}), 400
        if status not in VALID_TASK_STATUSES:
            return jsonify({"error": f"Invalid status. Must be one of: {sorted(VALID_TASK_STATUSES)}"}), 400

        svc = _get_service()
        if status == "processing":
            svc.mark_task_in_progress(graph_id, task_id, agent_id)
        elif status == "completed":
            svc.complete_task(graph_id, task_id, message)
        else:
            svc.storage.update_task_status(graph_id, task_id, status, message)

        return jsonify({"status": "success"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Failed to update task %s", task_id)
        return jsonify({"error": str(e)}), 500


@orchestration_bp.route("/task/<graph_id>/<task_id>/error", methods=["POST"])
def log_task_error(graph_id: str, task_id: str):
    """Log an execution error block for this task."""
    try:
        data = request.get_json(silent=True) or {}
        error_msg = (data.get("error_msg") or "").strip()
        traceback_text = data.get("traceback", "")

        if not error_msg:
            return jsonify({"error": "error_msg is required"}), 400

        svc = _get_service()
        error_id = svc.block_task_with_error(graph_id, task_id, error_msg, traceback_text)
        return jsonify({"error_id": error_id, "task_status": "failed"})
    except Exception as e:
        logger.exception("Failed to log error for task %s", task_id)
        return jsonify({"error": str(e)}), 500


@orchestration_bp.route("/task/<graph_id>/<task_id>/context", methods=["GET"])
def get_task_context(graph_id: str, task_id: str):
    """Retrieve exactly what an agent needs relative to this task."""
    try:
        svc = _get_service()
        ctx = svc.get_task_execution_context(graph_id, task_id)
        if not ctx:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(ctx)
    except Exception as e:
        logger.exception("Failed to get context for task %s", task_id)
        return jsonify({"error": str(e)}), 500


@orchestration_bp.route("/board/<graph_id>", methods=["GET"])
def get_board(graph_id: str):
    """Dashboard view of all sessions and tasks (Kanban board)."""
    try:
        svc = _get_service()
        tasks = svc.get_board(graph_id)
        return jsonify({"tasks": tasks})
    except Exception as e:
        logger.exception("Failed to get board for graph %s", graph_id)
        return jsonify({"error": str(e), "tasks": []}), 500
