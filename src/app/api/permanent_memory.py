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

from flask import Blueprint, request, jsonify

permanent_bp = Blueprint('permanent_memory', __name__)

# ──────────────────────────────────────────────
# Lazy Singletons
# ──────────────────────────────────────────────

_pm_manager = None
_cat_manager = None


def _get_pm():
    global _pm_manager
    if _pm_manager is None:
        from ..storage.permanent_memory import PermanentMemoryManager
        _pm_manager = PermanentMemoryManager()
    return _pm_manager


def _get_cat():
    global _cat_manager
    if _cat_manager is None:
        from ..storage.memory_categories import MemoryCategoryManager
        _cat_manager = MemoryCategoryManager()
    return _cat_manager


# ══════════════════════════════════════════════
# IMPRINT (각인)
# ══════════════════════════════════════════════

@permanent_bp.route('/permanent/imprint', methods=['POST'])
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


@permanent_bp.route('/permanent/imprints', methods=['GET'])
def list_imprints():
    """List all imprints, optionally filtered by scope/tags."""
    scope = request.args.get('scope')
    tags = request.args.getlist('tags')
    limit = request.args.get('limit', 100, type=int)
    return jsonify(_get_pm().list_imprints(scope=scope, tags=tags or None, limit=limit))


@permanent_bp.route('/permanent/imprint/<pm_uuid>', methods=['DELETE'])
def delete_imprint(pm_uuid):
    """Delete an imprint (admin-only)."""
    data = request.get_json(silent=True) or {}
    result = _get_pm().delete_imprint(pm_uuid, deleted_by=data.get('deleted_by', 'admin'))
    status = 200 if result.get('status') == 'deleted' else 404
    return jsonify(result), status


# ══════════════════════════════════════════════
# FREEZE / UNFREEZE
# ══════════════════════════════════════════════

@permanent_bp.route('/permanent/freeze', methods=['POST'])
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


@permanent_bp.route('/permanent/unfreeze', methods=['POST'])
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


@permanent_bp.route('/permanent/frozen', methods=['GET'])
def list_frozen():
    """List all frozen memories."""
    limit = request.args.get('limit', 100, type=int)
    return jsonify(_get_pm().list_frozen(limit=limit))


# ══════════════════════════════════════════════
# INHERITANCE
# ══════════════════════════════════════════════

@permanent_bp.route('/permanent/inherit', methods=['POST'])
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


@permanent_bp.route('/permanent/chain/<agent_id>', methods=['GET'])
def get_chain(agent_id):
    """Get the full inheritance chain for an agent."""
    return jsonify(_get_pm().get_inheritance_chain(agent_id))


@permanent_bp.route('/permanent/sync', methods=['POST'])
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

@permanent_bp.route('/permanent/priority/<agent_id>', methods=['GET'])
def get_priority_stack(agent_id):
    """Get priority-resolved memory stack for an agent."""
    include_ltm = request.args.get('include_ltm', 'false').lower() == 'true'
    return jsonify(_get_pm().get_priority_stack(agent_id, include_ltm=include_ltm))


@permanent_bp.route('/permanent/priority/adjust', methods=['POST'])
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


@permanent_bp.route('/permanent/priority/pin', methods=['POST'])
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


@permanent_bp.route('/permanent/priority/unpin', methods=['POST'])
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

@permanent_bp.route('/permanent/overrides', methods=['GET'])
def get_overrides():
    """Get priority override history."""
    agent_id = request.args.get('agent_id')
    limit = request.args.get('limit', 50, type=int)
    return jsonify(_get_pm().detect_priority_overrides(agent_id=agent_id, limit=limit))


@permanent_bp.route('/permanent/alerts', methods=['GET'])
def get_alerts():
    """Get active (unacknowledged) override alerts."""
    limit = request.args.get('limit', 20, type=int)
    return jsonify(_get_pm().get_override_alerts(limit=limit))


@permanent_bp.route('/permanent/alerts/ack', methods=['POST'])
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


@permanent_bp.route('/permanent/stats', methods=['GET'])
def get_pm_stats():
    """Get permanent memory statistics."""
    return jsonify(_get_pm().get_stats())


@permanent_bp.route('/permanent/dashboard-data', methods=['GET'])
def get_dashboard_data():
    """Combined dashboard data (stats + alerts + top PMs)."""
    return jsonify(_get_pm().get_dashboard_data())


# ══════════════════════════════════════════════
# MEMORY CATEGORIES (Procedural + Observational)
# ══════════════════════════════════════════════

@permanent_bp.route('/category/tool-use', methods=['POST'])
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


@permanent_bp.route('/category/observation', methods=['POST'])
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


@permanent_bp.route('/category/observation/outcome', methods=['POST'])
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


@permanent_bp.route('/category/search', methods=['GET'])
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


@permanent_bp.route('/category/stale', methods=['GET'])
def detect_stale():
    """Detect stale procedural memories."""
    max_age = request.args.get('max_age_days', 90, type=int)
    return jsonify(_get_cat().detect_stale_procedures(max_age_days=max_age))


@permanent_bp.route('/category/stale/decay', methods=['POST'])
def apply_stale_decay():
    """Apply accelerated decay to stale procedural memories."""
    data = request.get_json(silent=True) or {}
    max_age = data.get('max_age_days', 90)
    return jsonify(_get_cat().apply_staleness_decay(max_age_days=max_age))


@permanent_bp.route('/category/stats', methods=['GET'])
def get_category_stats():
    """Get statistics per memory category."""
    return jsonify(_get_cat().get_category_stats())
