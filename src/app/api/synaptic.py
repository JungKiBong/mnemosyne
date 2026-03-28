"""
Synaptic Bridge API — Phase 9

REST endpoints for multi-agent memory sharing and synchronization.
"""

import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger('mirofish.api.synaptic')

synaptic_bp = Blueprint('synaptic', __name__, url_prefix='/api/memory/synaptic')


def _get_bridge():
    from ..storage.synaptic_bridge import SynapticBridge
    return SynapticBridge()


# ── Agent Registry ──

@synaptic_bp.route('/agents', methods=['GET'])
def list_agents():
    bridge = _get_bridge()
    try:
        return jsonify(bridge.list_agents())
    finally:
        bridge.close()


@synaptic_bp.route('/agents/register', methods=['POST'])
def register_agent():
    data = request.get_json(force=True)
    agent_id = data.get('agent_id') or __import__('uuid').uuid4().hex[:12]
    name = data.get('name', f'Agent-{agent_id[:6]}')
    role = data.get('role', 'observer')
    capabilities = data.get('capabilities', [])
    scopes = data.get('subscribed_scopes', ['personal'])

    bridge = _get_bridge()
    try:
        result = bridge.register_agent(agent_id, name, role, capabilities, scopes)
        return jsonify(result)
    finally:
        bridge.close()


# ── Memory Sharing ──

@synaptic_bp.route('/share', methods=['POST'])
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
    try:
        result = bridge.share_memory(
            from_agent, memory_uuid,
            data.get('target_scope', 'tribal'),
            data.get('message', ''),
        )
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    finally:
        bridge.close()


@synaptic_bp.route('/empathy-boost', methods=['POST'])
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
    try:
        result = bridge.empathy_boost(
            from_agent, memory_uuid,
            data.get('boost_amount', 0.1),
            data.get('reason', ''),
        )
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    finally:
        bridge.close()


# ── Events & Stats ──

@synaptic_bp.route('/events', methods=['GET'])
def get_events():
    limit = request.args.get('limit', 50, type=int)
    bridge = _get_bridge()
    try:
        return jsonify(bridge.get_events(limit))
    finally:
        bridge.close()


@synaptic_bp.route('/stats', methods=['GET'])
def get_stats():
    bridge = _get_bridge()
    try:
        return jsonify(bridge.get_network_stats())
    finally:
        bridge.close()
