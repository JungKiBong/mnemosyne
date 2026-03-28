"""
Workflow Gallery API — n8n 워크플로우 JSON 파일 서빙, 검색, 다운로드
"""
import os
import json
import glob
import logging
from flask import Blueprint, jsonify, request, send_file

logger = logging.getLogger('mirofish.workflows')

workflow_bp = Blueprint('workflow', __name__)

# ── Workflow directory (container path or local) ──
WORKFLOW_DIR = os.environ.get(
    'WORKFLOW_DIR',
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'n8n_workflows')
)


def _parse_workflow(filepath):
    """Parse a single n8n workflow JSON and extract metadata."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    filename = os.path.basename(filepath)
    nodes = data.get('nodes', [])
    node_types = [n.get('type', '') for n in nodes]

    # Detect trigger type
    trigger = 'Manual'
    for nt in node_types:
        if 'webhook' in nt.lower():
            trigger = 'Webhook'
            break
        elif 'cron' in nt.lower() or 'schedule' in nt.lower():
            trigger = 'Schedule'
            break

    return {
        'file': filename,
        'name': data.get('name', filename.replace('.json', '')),
        'nodes': len(nodes),
        'node_types': list(set(nt.split('.')[-1] for nt in node_types if nt)),
        'trigger': trigger,
        'connections': len(data.get('connections', {})),
        'tags': [t.get('name', '') for t in data.get('tags', [])],
        'size_bytes': os.path.getsize(filepath),
    }


def _safe_filepath(filename):
    """Resolve filename within WORKFLOW_DIR; reject path traversal."""
    abs_dir = os.path.abspath(WORKFLOW_DIR)
    if not filename.endswith('.json'):
        filename += '.json'
    # Strip any path separators to prevent traversal
    safe_name = os.path.basename(filename)
    filepath = os.path.join(abs_dir, safe_name)
    # Double-check resolved path is still inside target directory
    if not os.path.commonpath([abs_dir]) == os.path.commonpath([abs_dir, os.path.abspath(filepath)]):
        return None, abs_dir
    return filepath, abs_dir


@workflow_bp.route('/list')
def list_workflows():
    """List all available n8n workflows with metadata."""
    abs_dir = os.path.abspath(WORKFLOW_DIR)
    if not os.path.isdir(abs_dir):
        logger.warning(f'Workflow directory not found: {abs_dir}')
        return jsonify({'error': 'Workflow directory not available', 'workflows': []}), 404

    files = sorted(glob.glob(os.path.join(abs_dir, '*.json')))
    workflows = []
    for f in files:
        parsed = _parse_workflow(f)
        if parsed:
            workflows.append(parsed)

    return jsonify({
        'workflows': workflows,
        'total': len(workflows),
    })


@workflow_bp.route('/search')
def search_workflows():
    """Search workflows by name, tag, or node type."""
    q = request.args.get('q', '').lower().strip()
    scope = request.args.get('scope', '').lower().strip()

    abs_dir = os.path.abspath(WORKFLOW_DIR)
    if not os.path.isdir(abs_dir):
        return jsonify({'workflows': [], 'total': 0})

    files = sorted(glob.glob(os.path.join(abs_dir, '*.json')))
    results = []
    for f in files:
        parsed = _parse_workflow(f)
        if not parsed:
            continue

        # Text search
        if q:
            searchable = f"{parsed['file']} {parsed['name']} {' '.join(parsed['tags'])} {' '.join(parsed['node_types'])} {parsed['trigger']}".lower()
            if q not in searchable:
                continue

        results.append(parsed)

    return jsonify({'workflows': results, 'total': len(results), 'query': q})


@workflow_bp.route('/<filename>')
def get_workflow(filename):
    """Get a single workflow JSON by filename."""
    filepath, _ = _safe_filepath(filename)
    if not filepath or not os.path.isfile(filepath):
        return jsonify({'error': 'Workflow not found'}), 404

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return jsonify(data)


@workflow_bp.route('/<filename>/download')
def download_workflow(filename):
    """Download a workflow JSON file."""
    filepath, _ = _safe_filepath(filename)
    if not filepath or not os.path.isfile(filepath):
        return jsonify({'error': 'Workflow not found'}), 404

    return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))


@workflow_bp.route('/executions')
def list_executions():
    """Return recent workflow execution log (placeholder — real data from n8n API)."""
    return jsonify({
        'executions': [],
        'message': 'Connect n8n API for live execution logs'
    })
