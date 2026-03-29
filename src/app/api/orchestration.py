"""
Orchestration Blackboard Router
REST APIs for multi-agent Mories state management.
"""

import logging
from flask import Blueprint, request, jsonify

from ..services.orchestrator_service import OrchestratorService

logger = logging.getLogger("mirofish.api.orchestration")
orchestration_bp = Blueprint('orchestration', __name__)

def get_orchestrator() -> OrchestratorService:
    return OrchestratorService()

@orchestration_bp.route("/session", methods=["POST"])
def start_session():
    """Starts a new orchestration session."""
    data = request.get_json(silent=True) or {}
    graph_id = data.get("graph_id")
    name = data.get("name")
    goal = data.get("goal")
    
    if not all([graph_id, name, goal]):
        return jsonify({"error": "Missing required fields"}), 400
        
    svc = get_orchestrator()
    session_id = svc.start_session(graph_id, name, goal)
    return jsonify({"session_id": session_id, "status": "active"})

@orchestration_bp.route("/session/<session_id>/task", methods=["POST"])
def queue_task(session_id: str):
    """Manager agent creates a sub-task."""
    data = request.get_json(silent=True) or {}
    graph_id = data.get("graph_id")
    name = data.get("name")
    description = data.get("description")
    context_uuids = data.get("context_uuids", [])
    
    if not all([graph_id, name, description]):
        return jsonify({"error": "Missing required fields"}), 400
        
    svc = get_orchestrator()
    task_id = svc.queue_task(graph_id, session_id, name, description, context_uuids)
    return jsonify({"task_id": task_id, "status": "pending"})

@orchestration_bp.route("/task/<graph_id>/<task_id>/status", methods=["PATCH"])
def update_task_status(graph_id: str, task_id: str):
    """Update task state (e.g. processing, completed)."""
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    message = data.get("message", "")
    agent_id = data.get("agent_id", "")
    
    if not status:
        return jsonify({"error": "Status is required"}), 400

    svc = get_orchestrator()
    if status == "processing":
        svc.mark_task_in_progress(graph_id, task_id, agent_id)
    elif status == "completed":
        svc.complete_task(graph_id, task_id, message)
    else:
        svc.storage.update_task_status(graph_id, task_id, status, message)
        
    return jsonify({"status": "success"})

@orchestration_bp.route("/task/<graph_id>/<task_id>/error", methods=["POST"])
def log_task_error(graph_id: str, task_id: str):
    """Log an execution error block for this task."""
    data = request.get_json(silent=True) or {}
    error_msg = data.get("error_msg")
    traceback = data.get("traceback", "")
    
    if not error_msg:
        return jsonify({"error": "error_msg is required"}), 400
        
    svc = get_orchestrator()
    error_id = svc.block_task_with_error(graph_id, task_id, error_msg, traceback)
    return jsonify({"error_id": error_id, "task_status": "failed"})

@orchestration_bp.route("/task/<graph_id>/<task_id>/context", methods=["GET"])
def get_task_context(graph_id: str, task_id: str):
    """Retrieve exactly what an agent needs relative to this task."""
    svc = get_orchestrator()
    ctx = svc.get_task_execution_context(graph_id, task_id)
    if not ctx:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(ctx)

@orchestration_bp.route("/board/<graph_id>", methods=["GET"])
def get_board(graph_id: str):
    """Dashboard view of active sessions and tasks."""
    svc = get_orchestrator()
    tasks = svc.get_board(graph_id)
    return jsonify({"tasks": tasks})
