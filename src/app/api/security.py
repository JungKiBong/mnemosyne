"""
Security API — RBAC + Encryption Management

Endpoints:
  # RBAC
  POST   /api/security/principals          — Register principal
  GET    /api/security/principals          — List principals
  POST   /api/security/check               — Check permission
  GET    /api/security/roles               — Get role-permission matrix

  # API Keys
  POST   /api/security/keys                — Generate API key
  GET    /api/security/keys                — List API keys
  DELETE /api/security/keys/<hash>         — Revoke API key

  # Encryption
  POST   /api/security/encrypt             — Encrypt a memory
  POST   /api/security/decrypt             — Decrypt a memory (returns plaintext)
  POST   /api/security/encrypt/remove      — Remove encryption permanently
  POST   /api/security/encrypt/scope       — Encrypt all memories in scope
  GET    /api/security/encrypt/status      — Encryption statistics
  POST   /api/security/rotate              — Key rotation (planned)
"""

import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger('mirofish.api.security')

security_bp = Blueprint('security', __name__, url_prefix='/api/security')


def _get_rbac():
    from ..security.memory_rbac import get_rbac
    return get_rbac()


def _get_encryption():
    from ..security.memory_encryption import get_encryption
    return get_encryption()


# ──────────────────────────────────────────
# RBAC: Principals
# ──────────────────────────────────────────

@security_bp.route('/principals', methods=['POST'])
def register_principal():
    """Register a new principal (user/agent/team)."""
    data = request.get_json(force=True)
    rbac = _get_rbac()
    result = rbac.register_principal(
        principal_id=data.get('principal_id', ''),
        name=data.get('name', ''),
        principal_type=data.get('type', 'user'),
        roles=data.get('roles', ['reader']),
        team_id=data.get('team_id', ''),
    )
    return jsonify(result)


@security_bp.route('/principals', methods=['GET'])
def list_principals():
    """List all principals."""
    rbac = _get_rbac()
    ptype = request.args.get('type')
    return jsonify({"principals": rbac.list_principals(ptype)})


# ──────────────────────────────────────────
# RBAC: Permission Check
# ──────────────────────────────────────────

@security_bp.route('/check', methods=['POST'])
def check_permission():
    """Check if a principal has permission for an action."""
    data = request.get_json(force=True)
    rbac = _get_rbac()
    result = rbac.check_permission(
        principal_id=data.get('principal_id', ''),
        action=data.get('action', ''),
        memory_scope=data.get('scope', 'personal'),
        memory_owner=data.get('owner', ''),
    )
    return jsonify(result)


@security_bp.route('/roles', methods=['GET'])
def role_matrix():
    """Get the role-permission matrix."""
    rbac = _get_rbac()
    return jsonify({"roles": rbac.get_role_matrix()})


# ──────────────────────────────────────────
# API Keys
# ──────────────────────────────────────────

@security_bp.route('/keys', methods=['POST'])
def generate_key():
    """Generate a new API key."""
    data = request.get_json(force=True)
    rbac = _get_rbac()
    try:
        result = rbac.generate_api_key(
            owner_id=data.get('owner_id', 'admin'),
            name=data.get('name', 'New Key'),
            roles=data.get('roles', ['writer']),
            allowed_scopes=data.get('allowed_scopes', ['personal', 'tribal']),
            rate_limit=data.get('rate_limit', 100),
            expires_in_days=int(data.get('expires_in_days', 30)),
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@security_bp.route('/keys', methods=['GET'])
def list_keys():
    """List API keys (hashes only, not actual keys)."""
    rbac = _get_rbac()
    owner_id = request.args.get('owner_id')
    return jsonify({"keys": rbac.list_api_keys(owner_id)})


@security_bp.route('/keys/verify', methods=['POST'])
def verify_key():
    """Verify an API key and return its metadata (scopes, roles, etc)."""
    data = request.get_json(force=True)
    raw_key = data.get('api_key', '')
    if not raw_key:
        return jsonify({"valid": False, "error": "api_key missing"}), 400
    
    rbac = _get_rbac()
    from ..security.memory_rbac import RateLimitExceeded, ApiKeyExpired
    
    try:
        principal = rbac.validate_api_key(raw_key)
        if principal:
            return jsonify({"valid": True, "principal": principal})
    except ApiKeyExpired as e:
        return jsonify({"valid": False, "error": str(e)}), 403
    except RateLimitExceeded as e:
        return jsonify({"valid": False, "error": str(e)}), 429
    
    return jsonify({"valid": False, "error": "Invalid or revoked API key"}), 401


@security_bp.route('/keys/<key_hash>', methods=['DELETE'])
def revoke_key(key_hash):
    """Revoke an API key."""
    rbac = _get_rbac()
    return jsonify(rbac.revoke_api_key(key_hash))


@security_bp.route('/keys/<key_hash>/extend', methods=['POST'])
def extend_key(key_hash):
    """Extend an API key's expiration."""
    data = request.get_json(force=True, silent=True) or {}
    days_to_extend = int(data.get('days', 30))
    rbac = _get_rbac()
    res = rbac.extend_api_key(key_hash, additional_days=days_to_extend)
    if res.get("status") == "error":
        return jsonify(res), 400
    return jsonify(res)


# ──────────────────────────────────────────
# Security Audit & Admin
# ──────────────────────────────────────────

@security_bp.route('/events', methods=['GET'])
def list_security_events():
    """Retrieve security audit events (Audit Trail Feed)."""
    rbac = _get_rbac()
    limit = int(request.args.get('limit', 50))
    events = rbac.get_security_events(limit=limit)
    return jsonify({"events": events})

@security_bp.route('/keys/<key_hash>/rate_limit', methods=['PUT'])
def update_key_rate_limit(key_hash):
    """Dynamically update rate limit for an API key."""
    data = request.get_json(force=True, silent=True) or {}
    new_limit = data.get('rate_limit')
    if new_limit is None:
        return jsonify({"error": "rate_limit is required"}), 400
    
    rbac = _get_rbac()
    res = rbac.update_api_key_rate_limit(key_hash, int(new_limit))
    if res.get("status") == "error":
        return jsonify(res), 400
    return jsonify(res)


# ──────────────────────────────────────────
# Encryption
# ──────────────────────────────────────────

@security_bp.route('/encrypt', methods=['POST'])
def encrypt_memory():
    """Encrypt a specific memory."""
    data = request.get_json(force=True)
    enc = _get_encryption()
    result = enc.encrypt_memory(
        memory_uuid=data.get('uuid', ''),
        fields=data.get('fields'),  # None = all encryptable
        encrypted_by=data.get('encrypted_by', 'admin'),
    )
    return jsonify(result)


@security_bp.route('/decrypt', methods=['POST'])
def decrypt_memory():
    """Decrypt a memory (returns plaintext, does NOT persist)."""
    data = request.get_json(force=True)
    enc = _get_encryption()
    result = enc.decrypt_memory(
        memory_uuid=data.get('uuid', ''),
        requesting_principal=data.get('principal', 'admin'),
    )
    return jsonify(result)


@security_bp.route('/encrypt/remove', methods=['POST'])
def remove_encryption():
    """Remove encryption from a memory permanently."""
    data = request.get_json(force=True)
    enc = _get_encryption()
    result = enc.remove_encryption(
        memory_uuid=data.get('uuid', ''),
        removed_by=data.get('removed_by', 'admin'),
    )
    return jsonify(result)


@security_bp.route('/encrypt/scope', methods=['POST'])
def encrypt_scope():
    """Encrypt all memories in a scope."""
    data = request.get_json(force=True)
    scope = data.get('scope', '')
    if not scope:
        return jsonify({"error": "scope is required"}), 400

    enc = _get_encryption()
    result = enc.encrypt_scope(
        scope=scope,
        encrypted_by=data.get('encrypted_by', 'admin'),
    )
    return jsonify(result)


@security_bp.route('/encrypt/status', methods=['GET'])
def encryption_status():
    """Get encryption statistics."""
    enc = _get_encryption()
    return jsonify(enc.get_encryption_status())


@security_bp.route('/rotate', methods=['POST'])
def key_rotation():
    """Plan or execute key rotation."""
    data = request.get_json(force=True)
    enc = _get_encryption()
    scope = data.get('scope')
    result = enc.rotate_keys(scope)
    return jsonify(result)
