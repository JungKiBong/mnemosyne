import logging
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger('mirofish.api.admin')
admin_bp = Blueprint('admin', __name__)


# --- Merged from security.py ---
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





def _get_rbac():
    from ..security.memory_rbac import get_rbac
    return get_rbac()


def _get_encryption():
    from ..security.memory_encryption import get_encryption
    return get_encryption()


# ──────────────────────────────────────────
# RBAC: Principals
# ──────────────────────────────────────────

@admin_bp.route('/security/principals', methods=['POST'])
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


@admin_bp.route('/security/principals', methods=['GET'])
def list_principals():
    """List all principals."""
    rbac = _get_rbac()
    ptype = request.args.get('type')
    return jsonify({"principals": rbac.list_principals(ptype)})


# ──────────────────────────────────────────
# RBAC: Permission Check
# ──────────────────────────────────────────

@admin_bp.route('/security/check', methods=['POST'])
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


@admin_bp.route('/security/roles', methods=['GET'])
def role_matrix():
    """Get the role-permission matrix."""
    rbac = _get_rbac()
    return jsonify({"roles": rbac.get_role_matrix()})


# ──────────────────────────────────────────
# API Keys
# ──────────────────────────────────────────

@admin_bp.route('/security/keys', methods=['POST'])
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


@admin_bp.route('/security/keys', methods=['GET'])
def list_keys():
    """List API keys (hashes only, not actual keys)."""
    rbac = _get_rbac()
    owner_id = request.args.get('owner_id')
    return jsonify({"keys": rbac.list_api_keys(owner_id)})


@admin_bp.route('/security/keys/verify', methods=['POST'])
def verify_key():
    """Verify an API key and return its metadata (scopes, roles, etc)."""
    data = request.get_json(force=True)
    raw_key = data.get('api_key', '')
    if not raw_key:
        return jsonify({"valid": False, "error": "api_key missing"}), 400
    
    rbac = _get_rbac()
    principal = rbac.validate_api_key(raw_key)
    if principal:
        return jsonify({"valid": True, "principal": principal})
    
    return jsonify({"valid": False, "error": "Invalid or revoked API key"}), 401


@admin_bp.route('/security/keys/<key_hash>', methods=['DELETE'])
def revoke_key(key_hash):
    """Revoke an API key."""
    rbac = _get_rbac()
    return jsonify(rbac.revoke_api_key(key_hash))


# ──────────────────────────────────────────
# Encryption
# ──────────────────────────────────────────

@admin_bp.route('/security/encrypt', methods=['POST'])
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


@admin_bp.route('/security/decrypt', methods=['POST'])
def decrypt_memory():
    """Decrypt a memory (returns plaintext, does NOT persist)."""
    data = request.get_json(force=True)
    enc = _get_encryption()
    result = enc.decrypt_memory(
        memory_uuid=data.get('uuid', ''),
        requesting_principal=data.get('principal', 'admin'),
    )
    return jsonify(result)


@admin_bp.route('/security/encrypt/remove', methods=['POST'])
def remove_encryption():
    """Remove encryption from a memory permanently."""
    data = request.get_json(force=True)
    enc = _get_encryption()
    result = enc.remove_encryption(
        memory_uuid=data.get('uuid', ''),
        removed_by=data.get('removed_by', 'admin'),
    )
    return jsonify(result)


@admin_bp.route('/security/encrypt/scope', methods=['POST'])
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


@admin_bp.route('/security/encrypt/status', methods=['GET'])
def encryption_status():
    """Get encryption statistics."""
    enc = _get_encryption()
    return jsonify(enc.get_encryption_status())


@admin_bp.route('/security/rotate', methods=['POST'])
def key_rotation():
    """Plan or execute key rotation."""
    data = request.get_json(force=True)
    enc = _get_encryption()
    scope = data.get('scope')
    result = enc.rotate_keys(scope)
    return jsonify(result)


# --- Merged from settings.py ---
"""
Settings API — Runtime LLM / Embedding / Ingestion configuration.

Persists settings to .env file and hot-reloads into Config class.
"""

import os

from ..config import Config


# Path to project-root .env
_ENV_PATH = os.path.join(os.path.dirname(__file__), '../../../.env')


def _read_env_dict() -> dict:
    """Parse .env file into {key: value} dict."""
    env = {}
    if not os.path.exists(_ENV_PATH):
        return env
    with open(_ENV_PATH, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, val = line.partition('=')
                env[key.strip()] = val.strip()
    return env


def _write_env_dict(env: dict):
    """Write {key: value} dict back to .env file, preserving comments."""
    lines = []
    existing_keys = set()

    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and '=' in stripped:
                    key = stripped.split('=', 1)[0].strip()
                    if key in env:
                        lines.append(f"{key}={env[key]}\n")
                        existing_keys.add(key)
                    else:
                        lines.append(line)
                else:
                    lines.append(line)

    # Append new keys not already in file
    for key, val in env.items():
        if key not in existing_keys:
            lines.append(f"{key}={val}\n")

    with open(_ENV_PATH, 'w') as f:
        f.writelines(lines)


def _apply_to_runtime(env: dict):
    """Hot-apply env vars to os.environ and Config class."""
    key_map = {
        'LLM_PROVIDER': None,
        'LLM_API_KEY': 'LLM_API_KEY',
        'LLM_BASE_URL': 'LLM_BASE_URL',
        'LLM_MODEL_NAME': 'LLM_MODEL_NAME',
        'EMBEDDING_MODEL': 'EMBEDDING_MODEL',
        'EMBEDDING_BASE_URL': 'EMBEDDING_BASE_URL',
        'EMBEDDING_PROVIDER': None,
        'OLLAMA_NUM_CTX': None,
    }
    for env_key, config_attr in key_map.items():
        if env_key in env:
            os.environ[env_key] = env[env_key]
            if config_attr:
                setattr(Config, config_attr, env[env_key])


@admin_bp.route('/settings', methods=['GET'])
def get_settings():
    """Return current runtime settings (masking sensitive values)."""
    api_key = os.environ.get('LLM_API_KEY', '')
    masked_key = ''
    if api_key:
        if len(api_key) > 8:
            masked_key = api_key[:4] + '•' * (len(api_key) - 8) + api_key[-4:]
        else:
            masked_key = '•' * len(api_key)

    emb_provider = os.environ.get('EMBEDDING_PROVIDER', 'ollama')
    return jsonify({
        'llm': {
            'provider': os.environ.get('LLM_PROVIDER', 'ollama'),
            'api_key_masked': masked_key,
            'api_key_set': bool(api_key),
            'base_url': os.environ.get('LLM_BASE_URL', Config.LLM_BASE_URL),
            'model': os.environ.get('LLM_MODEL_NAME', Config.LLM_MODEL_NAME),
            'num_ctx': int(os.environ.get('OLLAMA_NUM_CTX', '8192')),
        },
        'embedding': {
            'provider': emb_provider,
            'model': os.environ.get('EMBEDDING_MODEL', Config.EMBEDDING_MODEL),
            'base_url': os.environ.get('EMBEDDING_BASE_URL', Config.EMBEDDING_BASE_URL),
        },
    })


@admin_bp.route('/settings', methods=['PUT'])
def update_settings():
    """
    Update LLM / Embedding settings.
    Changes are persisted to .env and hot-reloaded into runtime.
    """
    data = request.get_json(silent=True) or {}
    env = _read_env_dict()
    changed = []

    llm = data.get('llm', {})
    if llm:
        for key, env_key in [
            ('provider', 'LLM_PROVIDER'),
            ('api_key', 'LLM_API_KEY'),
            ('base_url', 'LLM_BASE_URL'),
            ('model', 'LLM_MODEL_NAME'),
            ('num_ctx', 'OLLAMA_NUM_CTX'),
        ]:
            if key in llm and llm[key] is not None:
                val = str(llm[key])
                if val != env.get(env_key, ''):
                    env[env_key] = val
                    changed.append(env_key)

    emb = data.get('embedding', {})
    if emb:
        for key, env_key in [
            ('provider', 'EMBEDDING_PROVIDER'),
            ('model', 'EMBEDDING_MODEL'),
            ('base_url', 'EMBEDDING_BASE_URL'),
        ]:
            if key in emb and emb[key] is not None:
                val = str(emb[key])
                if val != env.get(env_key, ''):
                    env[env_key] = val
                    changed.append(env_key)

    if changed:
        _write_env_dict(env)
        _apply_to_runtime(env)
        logger.info("Settings updated: %s", changed)

    return jsonify({
        'status': 'ok',
        'changed': changed,
        'message': f'{len(changed)} setting(s) updated' if changed else 'No changes',
    })


@admin_bp.route('/settings/test/llm', methods=['POST'])
def test_llm_connection():
    """Test LLM connectivity with a simple chat request."""
    data = request.get_json(silent=True) or {}

    base_url = data.get('base_url', os.environ.get('LLM_BASE_URL', Config.LLM_BASE_URL))
    api_key = data.get('api_key', os.environ.get('LLM_API_KEY', Config.LLM_API_KEY))
    model = data.get('model', os.environ.get('LLM_MODEL_NAME', Config.LLM_MODEL_NAME))

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=15.0)

        import time
        start = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'OK' in one word."}],
            max_tokens=5,
            temperature=0,
        )
        latency_ms = int((time.time() - start) * 1000)
        content = resp.choices[0].message.content.strip()

        return jsonify({
            'status': 'connected',
            'model': model,
            'base_url': base_url,
            'response': content,
            'latency_ms': latency_ms,
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'model': model,
            'base_url': base_url,
            'error': str(e),
        }), 400


@admin_bp.route('/settings/test/embedding', methods=['POST'])
def test_embedding_connection():
    """Test Embedding service by generating a single vector."""
    data = request.get_json(silent=True) or {}

    provider = data.get('provider', os.environ.get('EMBEDDING_PROVIDER', 'ollama'))
    base_url = data.get('base_url', os.environ.get('EMBEDDING_BASE_URL', Config.EMBEDDING_BASE_URL))
    model = data.get('model', os.environ.get('EMBEDDING_MODEL', Config.EMBEDDING_MODEL))

    try:
        from ..storage.embedding_service import EmbeddingService
        import time

        svc = EmbeddingService(model=model, base_url=base_url, provider=provider)
        start = time.time()
        vec = svc.embed("connection test")
        latency_ms = int((time.time() - start) * 1000)

        return jsonify({
            'status': 'connected',
            'provider': provider,
            'model': model,
            'dimensions': len(vec),
            'latency_ms': latency_ms,
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'provider': provider,
            'model': model,
            'error': str(e),
        }), 400


# --- Merged from tools.py ---
"""
MCP Tools API — Agent-facing tool execution endpoint

Endpoints:
  GET  /api/tools/list          — List all available memory tools (schemas)
  POST /api/tools/execute       — Execute a tool by name
  GET  /api/tools/schemas/openai — Export OpenAI Function Calling schemas
  GET  /api/tools/schemas/mcp   — Export MCP-compatible schemas
"""




# Singleton toolkit
_toolkit = None

def _get_toolkit():
    global _toolkit
    if _toolkit is None:
        from ..tools.memory_tools import MoriesToolkit
        _toolkit = MoriesToolkit()
    return _toolkit


@admin_bp.route('/tools/list', methods=['GET'])
def list_tools():
    """List all available memory tools with descriptions."""
    tk = _get_toolkit()
    tools = []
    for name in tk.get_tool_names():
        desc = tk.get_tool_description(name)
        tools.append({
            "name": desc["name"],
            "description": desc["description"],
            "category": desc["category"],
            "parameter_count": len(desc["parameters"]),
        })
    return jsonify({"tools": tools, "count": len(tools)})


@admin_bp.route('/tools/execute', methods=['POST'])
def execute_tool():
    """
    Execute a memory tool.

    Body: {"tool": "memory_store", "arguments": {"content": "...", "source": "agent"}}
    """
    data = request.get_json(force=True)
    tool_name = data.get('tool')
    arguments = data.get('arguments', {})

    if not tool_name:
        return jsonify({"error": "tool name is required"}), 400

    tk = _get_toolkit()
    result = tk.execute(tool_name, arguments)

    if result.get("status") == "error":
        return jsonify(result), 500

    return jsonify(result)


@admin_bp.route('/tools/schemas/openai', methods=['GET'])
def openai_schemas():
    """Export all tools as OpenAI Function Calling schemas."""
    tk = _get_toolkit()
    schemas = tk.get_all_schemas("openai")
    return jsonify({"tools": schemas, "format": "openai_function_calling"})


@admin_bp.route('/tools/schemas/mcp', methods=['GET'])
def mcp_schemas():
    """Export all tools as MCP-compatible schemas."""
    tk = _get_toolkit()
    schemas = tk.get_all_schemas("mcp")
    return jsonify({"tools": schemas, "format": "mcp"})
