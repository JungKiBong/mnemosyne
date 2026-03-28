"""
Memory Audit API — Phase 10

REST endpoints for memory change history, rollback, and activity feed.
"""

import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger('mirofish.api.audit')

audit_bp = Blueprint('audit', __name__, url_prefix='/api/memory/audit')


def _get_audit():
    """Get or create MemoryAudit instance."""
    from ..storage.memory_audit import MemoryAudit
    return MemoryAudit()


# ──────────────────────────────────────────
# History & Activity
# ──────────────────────────────────────────

@audit_bp.route('/history/<memory_uuid>', methods=['GET'])
def get_history(memory_uuid: str):
    """
    Get revision history for a specific memory.

    Query params:
      - limit: max results (default 50)
      - field: filter by field name (e.g., 'salience')
    """
    limit = request.args.get('limit', 50, type=int)
    field = request.args.get('field', None)

    audit = _get_audit()
    try:
        history = audit.get_history(memory_uuid, limit=limit, field=field)
        return jsonify(history)
    finally:
        audit.close()


@audit_bp.route('/activity', methods=['GET'])
def get_activity():
    """
    Get recent activity feed across all memories.

    Query params:
      - limit: max results (default 30)
    """
    limit = request.args.get('limit', 30, type=int)

    audit = _get_audit()
    try:
        activity = audit.get_recent_activity(limit=limit)
        return jsonify(activity)
    finally:
        audit.close()


@audit_bp.route('/revision/<revision_id>', methods=['GET'])
def get_revision(revision_id: str):
    """Get a single revision by ID."""
    audit = _get_audit()
    try:
        rev = audit.get_revision(revision_id)
        if not rev:
            return jsonify({"error": "Revision not found"}), 404
        return jsonify(rev)
    finally:
        audit.close()


@audit_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get audit trail statistics."""
    audit = _get_audit()
    try:
        stats = audit.get_stats()
        return jsonify(stats)
    finally:
        audit.close()


@audit_bp.route('/decay-cycles', methods=['GET'])
def get_decay_cycles():
    """Get summary of recent decay cycles."""
    limit = request.args.get('limit', 10, type=int)

    audit = _get_audit()
    try:
        cycles = audit.get_decay_cycles(limit=limit)
        return jsonify(cycles)
    finally:
        audit.close()


# ──────────────────────────────────────────
# Rollback
# ──────────────────────────────────────────

@audit_bp.route('/rollback', methods=['POST'])
def rollback():
    """
    Rollback a memory to a previous revision state.

    Body: {"revision_id": "...", "rolled_back_by": "admin"}
    """
    data = request.get_json(force=True)
    revision_id = data.get('revision_id')
    if not revision_id:
        return jsonify({"error": "revision_id is required"}), 400

    rolled_back_by = data.get('rolled_back_by', 'admin')

    audit = _get_audit()
    try:
        result = audit.rollback_to_revision(revision_id, rolled_back_by)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    finally:
        audit.close()


@audit_bp.route('/rollback-cycle', methods=['POST'])
def rollback_cycle():
    """
    Rollback an entire decay cycle.

    Body: {"cycle_timestamp": "2026-03-28T00:00:00+00:00", "rolled_back_by": "admin"}
    """
    data = request.get_json(force=True)
    cycle_ts = data.get('cycle_timestamp')
    if not cycle_ts:
        return jsonify({"error": "cycle_timestamp is required"}), 400

    rolled_back_by = data.get('rolled_back_by', 'admin')

    audit = _get_audit()
    try:
        result = audit.rollback_decay_cycle(cycle_ts, rolled_back_by)
        return jsonify(result)
    finally:
        audit.close()
