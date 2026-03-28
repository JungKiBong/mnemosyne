"""
Memory Scopes API — Phase 8

REST endpoints for hierarchical memory scopes and promotions.
"""

import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger('mirofish.api.scopes')

scopes_bp = Blueprint('scopes', __name__, url_prefix='/api/memory/scopes')


def _get_scope_manager():
    from ..storage.memory_scopes import MemoryScopeManager
    return MemoryScopeManager()


# ──────────────────────────────────────────
# Query
# ──────────────────────────────────────────

@scopes_bp.route('/summary', methods=['GET'])
def get_summary():
    """Get scope summary stats (counts per scope, source types, candidates)."""
    mgr = _get_scope_manager()
    try:
        summary = mgr.get_scope_summary()
        return jsonify(summary)
    finally:
        mgr.close()


@scopes_bp.route('/list/<scope>', methods=['GET'])
def list_by_scope(scope: str):
    """
    List memories in a specific scope.

    Query params:
      - limit: max results (default 50)
      - sort: 'salience' or 'access' (default salience)
    """
    limit = request.args.get('limit', 50, type=int)
    sort_by = request.args.get('sort', 'salience')

    mgr = _get_scope_manager()
    try:
        memories = mgr.get_by_scope(scope, limit=limit, sort_by=sort_by)
        return jsonify(memories)
    finally:
        mgr.close()


@scopes_bp.route('/candidates', methods=['GET'])
def get_candidates():
    """
    Find memories eligible for promotion.

    Query params:
      - scope: source scope (default 'personal')
    """
    scope = request.args.get('scope', 'personal')

    mgr = _get_scope_manager()
    try:
        candidates = mgr.find_promotion_candidates(scope)
        return jsonify(candidates)
    finally:
        mgr.close()


# ──────────────────────────────────────────
# Actions
# ──────────────────────────────────────────

@scopes_bp.route('/promote', methods=['POST'])
def promote():
    """
    Promote a memory to a higher scope.

    Body: {
        "uuid": "...",
        "target_scope": "tribal|social|global",
        "reason": "optional reason"
    }
    """
    data = request.get_json(force=True)
    memory_uuid = data.get('uuid')
    target_scope = data.get('target_scope')

    if not memory_uuid or not target_scope:
        return jsonify({"error": "uuid and target_scope are required"}), 400

    reason = data.get('reason', '')
    promoted_by = data.get('promoted_by', 'admin')

    mgr = _get_scope_manager()
    try:
        result = mgr.promote_memory(memory_uuid, target_scope, promoted_by, reason)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)
    finally:
        mgr.close()


@scopes_bp.route('/source-type', methods=['POST'])
def set_source_type():
    """
    Set the source type for a memory.

    Body: {"uuid": "...", "source_type": "conversation|document|code|note|..."}
    """
    data = request.get_json(force=True)
    memory_uuid = data.get('uuid')
    source_type = data.get('source_type')

    if not memory_uuid or not source_type:
        return jsonify({"error": "uuid and source_type are required"}), 400

    mgr = _get_scope_manager()
    try:
        result = mgr.set_source_type(memory_uuid, source_type)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    finally:
        mgr.close()
