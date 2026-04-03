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

from flask import Blueprint, request, jsonify, current_app
from ..storage.memory_manager import MemoryManager, MemoryConfig

memory_bp = Blueprint('memory', __name__)

# Singleton — initialized on first request
_manager: MemoryManager = None


def _get_manager() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager.get_instance()
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


# --- Merged from memory_scopes.py ---
"""
Memory Scopes API — Phase 8

REST endpoints for hierarchical memory scopes and promotions.
"""

import logging

logger = logging.getLogger('mirofish.api.scopes')



def _get_scope_manager():
    from flask import current_app
    from ..storage.memory_scopes import MemoryScopeManager
    driver = current_app.extensions.get('neo4j_driver')
    return MemoryScopeManager(driver=driver)


# ──────────────────────────────────────────
# Query
# ──────────────────────────────────────────

@memory_bp.route('/scopes/summary', methods=['GET'])
def get_summary():
    """Get scope summary stats (counts per scope, source types, candidates)."""
    mgr = _get_scope_manager()
    try:
        summary = mgr.get_scope_summary()
        return jsonify(summary)
    finally:
        mgr.close()


@memory_bp.route('/scopes/list/<scope>', methods=['GET'])
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


@memory_bp.route('/scopes/candidates', methods=['GET'])
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

@memory_bp.route('/scopes/promote', methods=['POST'])
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


@memory_bp.route('/scopes/source-type', methods=['POST'])
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


# --- Merged from synaptic.py ---
"""
Synaptic Bridge API — Phase 9

REST endpoints for multi-agent memory sharing and synchronization.
"""

import logging

logger = logging.getLogger('mirofish.api.synaptic')



def _get_bridge():
    from flask import current_app
    from ..storage.synaptic_bridge import SynapticBridge
    driver = current_app.extensions.get('neo4j_driver')
    return SynapticBridge(driver=driver)


# ── Agent Registry ──

@memory_bp.route('/synaptic/agents', methods=['GET'])
def list_agents():
    bridge = _get_bridge()
    return jsonify(bridge.list_agents())


@memory_bp.route('/synaptic/agents/register', methods=['POST'])
def register_agent():
    data = request.get_json(force=True)
    agent_id = data.get('agent_id') or __import__('uuid').uuid4().hex[:12]
    name = data.get('name', f'Agent-{agent_id[:6]}')
    role = data.get('role', 'observer')
    capabilities = data.get('capabilities', [])
    scopes = data.get('subscribed_scopes', ['personal'])

    bridge = _get_bridge()
    result = bridge.register_agent(agent_id, name, role, capabilities, scopes)
    return jsonify(result)


# ── Memory Sharing ──

@memory_bp.route('/synaptic/share', methods=['POST'])
def share_memory():
    """
    Share memory to a scope.
    Body: {"from_agent": "...", "memory_uuid": "...", "target_scope": "tribal", "message": ""}
    """
    data = request.get_json(force=True)
    from_agent = data.get('from_agent')
    memory_uuid = data.get('memory_uuid')
    if not from_agent or not memory_uuid:
        return jsonify({"error": "from_agent and memory_uuid required"}), 400

    bridge = _get_bridge()
    result = bridge.share_memory(
        from_agent, memory_uuid,
        data.get('target_scope', 'tribal'),
        data.get('message', ''),
    )
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@memory_bp.route('/synaptic/empathy-boost', methods=['POST'])
def empathy_boost():
    """
    Empathy boost — confirm/reinforce a shared memory.
    Body: {"from_agent": "...", "memory_uuid": "...", "boost_amount": 0.1, "reason": ""}
    """
    data = request.get_json(force=True)
    from_agent = data.get('from_agent')
    memory_uuid = data.get('memory_uuid')
    if not from_agent or not memory_uuid:
        return jsonify({"error": "from_agent and memory_uuid required"}), 400

    bridge = _get_bridge()
    result = bridge.empathy_boost(
        from_agent, memory_uuid,
        data.get('boost_amount', 0.1),
        data.get('reason', ''),
    )
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


# ── Events & Stats ──

@memory_bp.route('/synaptic/events', methods=['GET'])
def get_events():
    limit = request.args.get('limit', 50, type=int)
    bridge = _get_bridge()
    return jsonify(bridge.get_events(limit))


@memory_bp.route('/synaptic/stats', methods=['GET'])
def get_synaptic_stats():
    bridge = _get_bridge()
    return jsonify(bridge.get_network_stats())



# --- Merged from memory_audit.py ---
"""
Memory Audit API — Phase 10

REST endpoints for memory change history, rollback, and activity feed.
"""

import logging

logger = logging.getLogger('mirofish.api.audit')



def _get_audit():
    """Get MemoryAudit instance with shared Neo4j driver."""
    from flask import current_app
    from ..storage.memory_audit import MemoryAudit
    driver = current_app.extensions.get('neo4j_driver')
    return MemoryAudit(driver=driver)


# ──────────────────────────────────────────
# History & Activity
# ──────────────────────────────────────────

@memory_bp.route('/audit/history/<memory_uuid>', methods=['GET'])
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
    history = audit.get_history(memory_uuid, limit=limit, field=field)
    return jsonify(history)


@memory_bp.route('/audit/activity', methods=['GET'])
def get_activity():
    """
    Get recent activity feed across all memories.

    Query params:
      - limit: max results (default 30)
    """
    limit = request.args.get('limit', 30, type=int)

    audit = _get_audit()
    activity = audit.get_recent_activity(limit=limit)
    return jsonify(activity)


@memory_bp.route('/audit/revision/<revision_id>', methods=['GET'])
def get_revision(revision_id: str):
    """Get a single revision by ID."""
    audit = _get_audit()
    rev = audit.get_revision(revision_id)
    if not rev:
        return jsonify({"error": "Revision not found"}), 404
    return jsonify(rev)


@memory_bp.route('/audit/stats', methods=['GET'])
def get_audit_stats():
    """Get audit trail statistics."""
    audit = _get_audit()
    stats = audit.get_stats()
    return jsonify(stats)


@memory_bp.route('/audit/decay-cycles', methods=['GET'])
def get_decay_cycles():
    """Get summary of recent decay cycles."""
    limit = request.args.get('limit', 10, type=int)

    audit = _get_audit()
    cycles = audit.get_decay_cycles(limit=limit)
    return jsonify(cycles)


# ──────────────────────────────────────────
# Rollback
# ──────────────────────────────────────────

@memory_bp.route('/audit/rollback', methods=['POST'])
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
    result = audit.rollback_to_revision(revision_id, rolled_back_by)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@memory_bp.route('/audit/rollback-cycle', methods=['POST'])
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
    result = audit.rollback_decay_cycle(cycle_ts, rolled_back_by)
    return jsonify(result)



# --- Merged from permanent_memory.py ---
"""
Permanent Memory & Category API — Phase 16 REST endpoints

Imprint (각인):
  POST   /api/memory/permanent/imprint           — Create imprint
  GET    /api/memory/permanent/imprints           — List imprints
  DELETE /api/memory/permanent/imprint/<uuid>      — Delete imprint (admin)

Freeze / Unfreeze:
  POST   /api/memory/permanent/freeze             — Freeze LTM → PM
  POST   /api/memory/permanent/unfreeze           — Unfreeze PM → LTM
  GET    /api/memory/permanent/frozen             — List frozen memories

Inheritance:
  POST   /api/memory/permanent/inherit            — Inherit PMs for agent
  GET    /api/memory/permanent/chain/<agent_id>   — Inheritance chain
  POST   /api/memory/permanent/sync               — Sync inheritance

Priority:
  GET    /api/memory/permanent/priority/<agent_id> — Priority stack
  POST   /api/memory/permanent/priority/adjust     — Adjust priority
  POST   /api/memory/permanent/priority/pin        — Admin pin priority
  POST   /api/memory/permanent/priority/unpin      — Unpin priority

Monitoring:
  GET    /api/memory/permanent/overrides           — Override history
  GET    /api/memory/permanent/alerts              — Active alerts
  POST   /api/memory/permanent/alerts/ack          — Acknowledge alert
  GET    /api/memory/permanent/stats               — PM statistics
  GET    /api/memory/permanent/dashboard-data      — Combined dashboard

Categories:
  POST   /api/memory/category/tool-use             — Record tool use
  POST   /api/memory/category/observation          — Record observation
  POST   /api/memory/category/observation/outcome  — Record observation outcome
  GET    /api/memory/category/search               — Category-filtered search
  GET    /api/memory/category/stale                — Detect stale procedures
  POST   /api/memory/category/stale/decay          — Apply staleness decay
  GET    /api/memory/category/stats                — Category statistics
"""



# ──────────────────────────────────────────────
# Lazy Singletons
# ──────────────────────────────────────────────

_pm_manager = None
_cat_manager = None


def _get_pm():
    global _pm_manager
    if _pm_manager is None:
        from flask import current_app
        from ..storage.permanent_memory import PermanentMemoryManager
        driver = current_app.extensions.get('neo4j_driver')
        _pm_manager = PermanentMemoryManager(driver=driver)
    return _pm_manager


def _get_cat():
    global _cat_manager
    if _cat_manager is None:
        from flask import current_app
        from ..storage.memory_categories import MemoryCategoryManager
        driver = current_app.extensions.get('neo4j_driver')
        _cat_manager = MemoryCategoryManager(driver=driver)
    return _cat_manager


# ══════════════════════════════════════════════
# IMPRINT (각인)
# ══════════════════════════════════════════════

@memory_bp.route('/permanent/imprint', methods=['POST'])
def create_imprint():
    """Create a new imprint (admin-injected permanent memory)."""
    data = request.get_json(silent=True) or {}
    content = data.get('content')
    if not content:
        return jsonify({"error": "content is required"}), 400

    result = _get_pm().create_imprint(
        content=content,
        scope=data.get('scope', 'global'),
        tags=data.get('tags', []),
        created_by=data.get('created_by', 'admin'),
        reason=data.get('reason', ''),
        memory_category=data.get('memory_category', 'declarative'),
        metadata=data.get('metadata'),
    )
    return jsonify(result), 201


@memory_bp.route('/permanent/imprints', methods=['GET'])
def list_imprints():
    """List all imprints, optionally filtered by scope/tags."""
    scope = request.args.get('scope')
    tags = request.args.getlist('tags')
    limit = request.args.get('limit', 100, type=int)
    return jsonify(_get_pm().list_imprints(scope=scope, tags=tags or None, limit=limit))


@memory_bp.route('/permanent/imprint/<pm_uuid>', methods=['DELETE'])
def delete_imprint(pm_uuid):
    """Delete an imprint (admin-only)."""
    data = request.get_json(silent=True) or {}
    result = _get_pm().delete_imprint(pm_uuid, deleted_by=data.get('deleted_by', 'admin'))
    status = 200 if result.get('status') == 'deleted' else 404
    return jsonify(result), status


# ══════════════════════════════════════════════
# FREEZE / UNFREEZE
# ══════════════════════════════════════════════

@memory_bp.route('/permanent/freeze', methods=['POST'])
def freeze_memory():
    """Freeze an existing LTM memory to permanent."""
    data = request.get_json(silent=True) or {}
    memory_uuid = data.get('memory_uuid')
    if not memory_uuid:
        return jsonify({"error": "memory_uuid is required"}), 400

    result = _get_pm().freeze_memory(
        memory_uuid=memory_uuid,
        reason=data.get('reason', ''),
        frozen_by=data.get('frozen_by', 'admin'),
    )
    status = 201 if result.get('status') == 'frozen' else 404
    return jsonify(result), status


@memory_bp.route('/permanent/unfreeze', methods=['POST'])
def unfreeze_memory():
    """Unfreeze a frozen PM back to normal LTM (admin-only)."""
    data = request.get_json(silent=True) or {}
    pm_uuid = data.get('pm_uuid')
    if not pm_uuid:
        return jsonify({"error": "pm_uuid is required"}), 400

    result = _get_pm().unfreeze_memory(
        pm_uuid=pm_uuid,
        unfrozen_by=data.get('unfrozen_by', 'admin'),
    )
    status = 200 if result.get('status') == 'unfrozen' else 404
    return jsonify(result), status


@memory_bp.route('/permanent/frozen', methods=['GET'])
def list_frozen():
    """List all frozen memories."""
    limit = request.args.get('limit', 100, type=int)
    return jsonify(_get_pm().list_frozen(limit=limit))


# ══════════════════════════════════════════════
# INHERITANCE
# ══════════════════════════════════════════════

@memory_bp.route('/permanent/inherit', methods=['POST'])
def inherit_for_agent():
    """Inherit permanent memories for an agent from higher scopes."""
    data = request.get_json(silent=True) or {}
    agent_id = data.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id is required"}), 400

    result = _get_pm().inherit_for_agent(
        agent_id=agent_id,
        scopes=data.get('scopes'),
    )
    return jsonify(result)


@memory_bp.route('/permanent/chain/<agent_id>', methods=['GET'])
def get_chain(agent_id):
    """Get the full inheritance chain for an agent."""
    return jsonify(_get_pm().get_inheritance_chain(agent_id))


@memory_bp.route('/permanent/sync', methods=['POST'])
def sync_inheritance():
    """Sync an agent's inherited PMs with upstream changes."""
    data = request.get_json(silent=True) or {}
    agent_id = data.get('agent_id')
    if not agent_id:
        return jsonify({"error": "agent_id is required"}), 400

    return jsonify(_get_pm().sync_inheritance(agent_id))


# ══════════════════════════════════════════════
# PRIORITY RESOLUTION
# ══════════════════════════════════════════════

@memory_bp.route('/permanent/priority/<agent_id>', methods=['GET'])
def get_priority_stack(agent_id):
    """Get priority-resolved memory stack for an agent."""
    include_ltm = request.args.get('include_ltm', 'false').lower() == 'true'
    return jsonify(_get_pm().get_priority_stack(agent_id, include_ltm=include_ltm))


@memory_bp.route('/permanent/priority/adjust', methods=['POST'])
def adjust_priority():
    """Adjust priority via agent interaction weight."""
    data = request.get_json(silent=True) or {}
    pm_uuid = data.get('pm_uuid')
    agent_id = data.get('agent_id')
    delta = data.get('delta', 0)

    if not pm_uuid or not agent_id:
        return jsonify({"error": "pm_uuid and agent_id are required"}), 400

    result = _get_pm().adjust_priority(
        pm_uuid=pm_uuid,
        agent_id=agent_id,
        delta=float(delta),
        reason=data.get('reason', ''),
    )
    status = 200 if result.get('status') == 'adjusted' else 400
    return jsonify(result), status


@memory_bp.route('/permanent/priority/pin', methods=['POST'])
def pin_priority():
    """Admin-lock a priority value."""
    data = request.get_json(silent=True) or {}
    pm_uuid = data.get('pm_uuid')
    priority = data.get('priority')

    if not pm_uuid or priority is None:
        return jsonify({"error": "pm_uuid and priority are required"}), 400

    result = _get_pm().pin_priority(
        pm_uuid=pm_uuid,
        priority=int(priority),
        pinned_by=data.get('pinned_by', 'admin'),
    )
    status = 200 if result.get('status') == 'pinned' else 404
    return jsonify(result), status


@memory_bp.route('/permanent/priority/unpin', methods=['POST'])
def unpin_priority():
    """Remove admin priority lock."""
    data = request.get_json(silent=True) or {}
    pm_uuid = data.get('pm_uuid')
    if not pm_uuid:
        return jsonify({"error": "pm_uuid is required"}), 400

    result = _get_pm().unpin_priority(
        pm_uuid=pm_uuid,
        unpinned_by=data.get('unpinned_by', 'admin'),
    )
    status = 200 if result.get('status') == 'unpinned' else 404
    return jsonify(result), status


# ══════════════════════════════════════════════
# MONITORING & ALERTS
# ══════════════════════════════════════════════

@memory_bp.route('/permanent/overrides', methods=['GET'])
def get_overrides():
    """Get priority override history."""
    agent_id = request.args.get('agent_id')
    limit = request.args.get('limit', 50, type=int)
    return jsonify(_get_pm().detect_priority_overrides(agent_id=agent_id, limit=limit))


@memory_bp.route('/permanent/alerts', methods=['GET'])
def get_alerts():
    """Get active (unacknowledged) override alerts."""
    limit = request.args.get('limit', 20, type=int)
    return jsonify(_get_pm().get_override_alerts(limit=limit))


@memory_bp.route('/permanent/alerts/ack', methods=['POST'])
def acknowledge_alert():
    """Acknowledge an override alert."""
    data = request.get_json(silent=True) or {}
    alert_id = data.get('alert_id')
    if not alert_id:
        return jsonify({"error": "alert_id is required"}), 400

    result = _get_pm().acknowledge_alert(
        alert_id=alert_id,
        acknowledged_by=data.get('acknowledged_by', 'admin'),
    )
    status = 200 if result.get('status') == 'acknowledged' else 404
    return jsonify(result), status


@memory_bp.route('/permanent/stats', methods=['GET'])
def get_pm_stats():
    """Get permanent memory statistics."""
    return jsonify(_get_pm().get_stats())


@memory_bp.route('/permanent/dashboard-data', methods=['GET'])
def get_dashboard_data():
    """Combined dashboard data (stats + alerts + top PMs)."""
    return jsonify(_get_pm().get_dashboard_data())


# ══════════════════════════════════════════════
# MEMORY CATEGORIES (Procedural + Observational)
# ══════════════════════════════════════════════

@memory_bp.route('/category/tool-use', methods=['POST'])
def record_tool_use():
    """Record a tool-use experience as procedural memory."""
    data = request.get_json(silent=True) or {}
    tool_name = data.get('tool_name')
    if not tool_name:
        return jsonify({"error": "tool_name is required"}), 400

    result = _get_cat().record_tool_use(
        tool_name=tool_name,
        tool_type=data.get('tool_type', 'api'),
        description=data.get('description', ''),
        input_data=data.get('input_data'),
        output_data=data.get('output_data'),
        success=data.get('success', True),
        execution_time_ms=data.get('execution_time_ms', 0),
        agent_id=data.get('agent_id', 'system'),
        tool_version=data.get('tool_version', ''),
    )
    status = 201 if result.get('status') == 'created' else 200
    return jsonify(result), status


@memory_bp.route('/category/observation', methods=['POST'])
def record_observation():
    """Record an observation of user/agent behavior."""
    data = request.get_json(silent=True) or {}
    observed_from = data.get('observed_from')
    context = data.get('context')
    steps = data.get('steps', [])

    if not observed_from or not context:
        return jsonify({"error": "observed_from and context are required"}), 400

    result = _get_cat().record_observation(
        observed_from=observed_from,
        context=context,
        steps=steps,
        description=data.get('description', context),
        outcome=data.get('outcome', 'positive'),
        confidence=float(data.get('confidence', 0.5)),
        agent_id=data.get('agent_id', 'system'),
    )
    return jsonify(result), 201


@memory_bp.route('/category/observation/outcome', methods=['POST'])
def observation_outcome():
    """Record whether applying an observational memory was successful."""
    data = request.get_json(silent=True) or {}
    memory_uuid = data.get('memory_uuid')
    if not memory_uuid:
        return jsonify({"error": "memory_uuid is required"}), 400

    result = _get_cat().record_observation_outcome(
        memory_uuid=memory_uuid,
        success=data.get('success', True),
    )
    status = 200 if result.get('status') == 'updated' else 404
    return jsonify(result), status


@memory_bp.route('/category/search', methods=['GET'])
def search_by_category():
    """Search memories by category with category-specific ranking."""
    category = request.args.get('category', 'procedural')
    query = request.args.get('q', '')
    tool_type = request.args.get('tool_type')
    min_salience = request.args.get('min_salience', 0.0, type=float)
    limit = request.args.get('limit', 20, type=int)

    return jsonify(_get_cat().search_by_category(
        category=category,
        query=query,
        tool_type=tool_type,
        min_salience=min_salience,
        limit=limit,
    ))


# ──────────────────────────────────────────
# COGNITIVE CATEGORIES API (Phase 16-C+)
# ──────────────────────────────────────────

@memory_bp.route('/category/preference', methods=['POST'])
def record_preference():
    """Record a user preference."""
    data = request.get_json(silent=True) or {}
    domain = data.get('domain')
    preference_key = data.get('preference_key')
    preference_value = data.get('preference_value')
    if not domain or not preference_key or preference_value is None:
        return jsonify({"error": "domain, preference_key, and preference_value are required"}), 400

    result = _get_cat().record_preference(
        domain=domain,
        preference_key=preference_key,
        preference_value=preference_value,
        description=data.get('description', ''),
        weight=float(data.get('weight', 1.0)),
        is_negative=bool(data.get('is_negative', False)),
        agent_id=data.get('agent_id', 'system'),
    )
    return jsonify(result), 201


@memory_bp.route('/category/preference', methods=['GET'])
def recall_preferences():
    """Recall user preferences."""
    domain = request.args.get('domain')
    agent_id = request.args.get('agent_id', 'system')
    return jsonify(_get_cat().recall_preferences(domain=domain, agent_id=agent_id))


@memory_bp.route('/category/instruction', methods=['POST'])
def record_instruction():
    """Record an instructional rule."""
    data = request.get_json(silent=True) or {}
    rule = data.get('rule')
    if not rule:
        return jsonify({"error": "rule is required"}), 400

    result = _get_cat().record_instruction(
        rule=rule,
        category=data.get('category', 'general'),
        strictness=data.get('strictness', 'should'),
        description=data.get('description', ''),
        agent_id=data.get('agent_id', 'system'),
    )
    return jsonify(result), 201


@memory_bp.route('/category/instruction', methods=['GET'])
def recall_instructions():
    """Recall instructional rules."""
    category = request.args.get('category')
    agent_id = request.args.get('agent_id', 'system')
    return jsonify(_get_cat().recall_instructions(category=category, agent_id=agent_id))


@memory_bp.route('/category/reflection', methods=['POST'])
def record_reflection():
    """Record a reflection on a past event."""
    data = request.get_json(silent=True) or {}
    event = data.get('event')
    lesson = data.get('lesson')
    if not event or not lesson:
        return jsonify({"error": "event and lesson are required"}), 400

    result = _get_cat().record_reflection(
        event=event,
        lesson=lesson,
        domain=data.get('domain', 'general'),
        severity=data.get('severity', 'low'),
        description=data.get('description', ''),
        agent_id=data.get('agent_id', 'system'),
    )
    return jsonify(result), 201


@memory_bp.route('/category/reflection', methods=['GET'])
def recall_reflections():
    """Recall reflections."""
    domain = request.args.get('domain')
    severity = request.args.get('severity')
    agent_id = request.args.get('agent_id', 'system')
    return jsonify(_get_cat().recall_reflections(domain=domain, severity=severity, agent_id=agent_id))


@memory_bp.route('/category/conditional', methods=['POST'])
def record_conditional():
    """Record a conditional knowledge rule."""
    data = request.get_json(silent=True) or {}
    condition = data.get('condition')
    then_action = data.get('then_action')
    if not condition or not then_action:
        return jsonify({"error": "condition and then_action are required"}), 400

    result = _get_cat().record_conditional(
        condition=condition,
        then_action=then_action,
        else_action=data.get('else_action'),
        description=data.get('description', ''),
        subcategory=data.get('subcategory', 'contextual'),
        confidence=float(data.get('confidence', 0.9)),
        valid_from=data.get('valid_from'),
        valid_until=data.get('valid_until'),
        agent_id=data.get('agent_id', 'system'),
    )
    return jsonify(result), 201


@memory_bp.route('/category/conditional/search', methods=['POST'])
def recall_conditionals():
    """Recall conditional rules matching a context context (using POST to pass body)."""
    data = request.get_json(silent=True) or {}
    context = data.get('context')
    subcategory = data.get('subcategory')
    agent_id = data.get('agent_id', 'system')
    return jsonify(_get_cat().recall_conditionals(context=context, subcategory=subcategory, agent_id=agent_id))


@memory_bp.route('/category/orchestration/handoff', methods=['POST'])
def record_handoff():
    """Record a multi-agent task handoff/delegation."""
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    task_desc = data.get('task_description')
    from_agent = data.get('from_agent')
    to_agent = data.get('to_agent')
    if not all([task_id, task_desc, from_agent, to_agent]):
         return jsonify({"error": "Missing required orchestration fields"}), 400
    
    result = _get_cat().record_task_handoff(
        task_id=task_id,
        task_description=task_desc,
        from_agent=from_agent,
        to_agent=to_agent,
        context=data.get('context'),
        parent_task_id=data.get('parent_task_id'),
        task_type=data.get('task_type', 'handoff')
    )
    return jsonify(result), 201

@memory_bp.route('/category/orchestration/status', methods=['POST'])
def update_task_status():
    """Update status of a multi-agent task."""
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    status = data.get('status')
    if not task_id or not status:
        return jsonify({"error": "task_id and status required"}), 400
    return jsonify(_get_cat().update_task_status(task_id, status))


@memory_bp.route('/category/harness', methods=['POST'])
def record_harness():
    """Record the registration of a new computational harness."""
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    tools = data.get('tools')
    process = data.get('process')
    if not all([name, tools, process]):
        return jsonify({"error": "name, tools, and process are required for harness"}), 400

    result = _get_cat().record_harness(
        name=name,
        description=data.get('description', ''),
        version=data.get('version', '1.0.0'),
        tools=tools,
        process=process,
        success_criteria=data.get('success_criteria'),
        agent_id=data.get('agent_id', 'system'),
    )
    return jsonify(result), 201

@memory_bp.route('/category/harness/<name>', methods=['GET'])
def recall_harness(name):
    """Recall a specific computational harness by name."""
    agent_id = request.args.get('agent_id', 'system')
    return jsonify(_get_cat().recall_harness(name=name, agent_id=agent_id))

@memory_bp.route('/category/harness/list', methods=['GET'])
def list_harnesses():
    """List all available computational harnesses."""
    agent_id = request.args.get('agent_id', 'system')
    return jsonify(_get_cat().list_harnesses(agent_id=agent_id))

@memory_bp.route('/category/harness/extract', methods=['POST'])
def extract_harness():
    """Extract a structural harness definition from unstructured project logs/events."""
    data = request.get_json(silent=True) or {}
    events = data.get('events')
    prompt = data.get('prompt')
    if not events:
        return jsonify({"error": "events payload required for harness extraction"}), 400
    
    result = _get_cat().extract_harness_from_log(
        events=events,
        prompt=prompt,
        agent_id=data.get('agent_id', 'system')
    )
    return jsonify(result), 200


def detect_stale():
    """Detect stale procedural memories."""
    max_age = request.args.get('max_age_days', 90, type=int)
    return jsonify(_get_cat().detect_stale_procedures(max_age_days=max_age))


@memory_bp.route('/category/stale/decay', methods=['POST'])
def apply_stale_decay():
    """Apply accelerated decay to stale procedural memories."""
    data = request.get_json(silent=True) or {}
    max_age = data.get('max_age_days', 90)
    return jsonify(_get_cat().apply_staleness_decay(max_age_days=max_age))


@memory_bp.route('/category/stats', methods=['GET'])
def get_category_stats():
    """Get statistics per memory category."""
    return jsonify(_get_cat().get_category_stats())
