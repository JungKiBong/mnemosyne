"""
Memory Management API — REST endpoints for Cognitive Memory (Phase 7)

Endpoints:
  GET  /api/memory/overview       — Dashboard overview data
  GET  /api/memory/top            — Top memories by salience
  GET  /api/memory/weakest        — Memories closest to forgetting
  GET  /api/memory/:uuid          — Single memory detail
  POST /api/memory/stm/add        — Add to short-term memory
  GET  /api/memory/stm/list       — List STM buffer
  POST /api/memory/stm/evaluate   — Set salience for STM item
  POST /api/memory/stm/promote    — Promote STM → LTM
  POST /api/memory/stm/discard    — Discard STM item
  POST /api/memory/boost          — Manual salience boost
  POST /api/memory/decay          — Run decay cycle
  POST /api/memory/config         — Update config
"""

from flask import Blueprint, request, jsonify
from ..storage.memory_manager import MemoryManager, MemoryConfig

memory_bp = Blueprint('memory', __name__)

# Singleton — initialized on first request
_manager: MemoryManager = None


def _get_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager()
    return _manager


# ──────────────────────────────────────────────
# Dashboard Data
# ──────────────────────────────────────────────

@memory_bp.route('/overview', methods=['GET'])
def memory_overview():
    """Get full memory system overview for dashboard."""
    mgr = _get_manager()
    return jsonify(mgr.get_memory_overview())


@memory_bp.route('/top', methods=['GET'])
def top_memories():
    """Get top memories by salience or access."""
    mgr = _get_manager()
    limit = request.args.get('limit', 20, type=int)
    sort_by = request.args.get('sort', 'salience')
    return jsonify(mgr.get_top_memories(limit=limit, sort_by=sort_by))


@memory_bp.route('/weakest', methods=['GET'])
def weakest_memories():
    """Get memories closest to being forgotten."""
    mgr = _get_manager()
    limit = request.args.get('limit', 20, type=int)
    return jsonify(mgr.get_weakest_memories(limit=limit))


@memory_bp.route('/<uuid>', methods=['GET'])
def memory_detail(uuid):
    """Get detail for a single memory."""
    mgr = _get_manager()
    return jsonify(mgr.get_salience_timeline(uuid))


# ──────────────────────────────────────────────
# STM Operations
# ──────────────────────────────────────────────

@memory_bp.route('/stm/add', methods=['POST'])
def stm_add():
    """Add item to short-term memory."""
    mgr = _get_manager()
    data = request.get_json(silent=True) or {}
    content = data.get('content', '')
    source = data.get('source', 'api')
    metadata = data.get('metadata', {})
    ttl = data.get('ttl')

    if not content:
        return jsonify({"error": "content is required"}), 400

    item = mgr.stm_add(content=content, source=source,
                        metadata=metadata, ttl=ttl)
    return jsonify(item.to_dict()), 201


@memory_bp.route('/stm/list', methods=['GET'])
def stm_list():
    """List all STM items."""
    mgr = _get_manager()
    return jsonify(mgr.stm_list())


@memory_bp.route('/stm/evaluate', methods=['POST'])
def stm_evaluate():
    """Evaluate salience for an STM item."""
    mgr = _get_manager()
    data = request.get_json(silent=True) or {}
    item_id = data.get('id', '')
    salience = data.get('salience', 0.5)

    if not item_id:
        return jsonify({"error": "id is required"}), 400

    result = mgr.stm_evaluate(item_id, salience)
    return jsonify(result)


@memory_bp.route('/stm/promote', methods=['POST'])
def stm_promote():
    """Promote STM item to LTM."""
    mgr = _get_manager()
    data = request.get_json(silent=True) or {}
    item_id = data.get('id', '')
    graph_id = data.get('graph_id', '')

    if not item_id:
        return jsonify({"error": "id is required"}), 400

    result = mgr.stm_promote(item_id, graph_id=graph_id)
    return jsonify(result)


@memory_bp.route('/stm/discard', methods=['POST'])
def stm_discard():
    """Discard STM item (explicit forgetting)."""
    mgr = _get_manager()
    data = request.get_json(silent=True) or {}
    item_id = data.get('id', '')

    if not item_id:
        return jsonify({"error": "id is required"}), 400

    result = mgr.stm_discard(item_id)
    return jsonify(result)


# ──────────────────────────────────────────────
# Memory Management
# ──────────────────────────────────────────────

@memory_bp.route('/boost', methods=['POST'])
def boost_memory():
    """Manually boost/reduce salience for a memory."""
    mgr = _get_manager()
    data = request.get_json(silent=True) or {}
    uuid = data.get('uuid', '')
    amount = data.get('amount', 0.1)

    if not uuid:
        return jsonify({"error": "uuid is required"}), 400

    result = mgr.manual_boost(uuid, amount)
    return jsonify(result)


@memory_bp.route('/decay', methods=['POST'])
def run_decay():
    """Run Ebbinghaus decay cycle."""
    mgr = _get_manager()
    data = request.get_json(silent=True) or {}
    dry_run = data.get('dry_run', False)
    result = mgr.run_decay(dry_run=dry_run)
    return jsonify(result)


@memory_bp.route('/config', methods=['GET', 'POST'])
def manage_config():
    """Get or update memory config."""
    mgr = _get_manager()
    if request.method == 'GET':
        return jsonify(mgr.config.to_dict())

    data = request.get_json(silent=True) or {}
    result = mgr.update_config(data)
    return jsonify(result)
