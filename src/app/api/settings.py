"""
Settings API — Runtime LLM / Embedding / Ingestion configuration.

Persists settings to .env file and hot-reloads into Config class.
"""

import os
import logging
from flask import Blueprint, request, jsonify

from ..config import Config

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')
logger = logging.getLogger('mirofish.settings')

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


@settings_bp.route('', methods=['GET'])
@settings_bp.route('/', methods=['GET'])
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


@settings_bp.route('', methods=['PUT'])
@settings_bp.route('/', methods=['PUT'])
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


@settings_bp.route('/test/llm', methods=['POST'])
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


@settings_bp.route('/test/embedding', methods=['POST'])
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
