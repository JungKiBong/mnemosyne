import os
import json as _json
import glob as _glob
import logging
from flask import Blueprint, send_from_directory, jsonify, request, current_app

logger = logging.getLogger(__name__)

core_bp = Blueprint('core', __name__)

def get_dashboard_dir():
    # Because this file is in src/app/api, dashboard is in src/dashboard
    # __file__ = src/app/api/core.py
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../dashboard'))

# --- Dashboard & Frontend Views ---
@core_bp.route('/')
@core_bp.route('/dashboard')
def serve_dashboard():
    return send_from_directory(get_dashboard_dir(), 'index.html')

@core_bp.route('/dashboard/<path:filename>')
def serve_dashboard_static(filename):
    return send_from_directory(get_dashboard_dir(), filename)

@core_bp.route('/memory')
def serve_memory_dashboard():
    return send_from_directory(get_dashboard_dir(), 'memory.html')

@core_bp.route('/memory/history')
def serve_memory_history():
    return send_from_directory(get_dashboard_dir(), 'memory_history.html')

@core_bp.route('/memory/synaptic')
def serve_synaptic_path():
    return send_from_directory(get_dashboard_dir(), 'synaptic.html')

@core_bp.route('/api-docs')
@core_bp.route('/api-explorer')
def serve_api_explorer():
    return send_from_directory(get_dashboard_dir(), 'api-docs.html')

@core_bp.route('/workflows')
@core_bp.route('/n8n-workflows')
def serve_workflow_catalog():
    return send_from_directory(get_dashboard_dir(), 'workflows.html')

@core_bp.route('/graph')
def serve_graph_explorer():
    return send_from_directory(get_dashboard_dir(), 'graph.html')

@core_bp.route('/maturity')
def serve_maturity_dashboard():
    return send_from_directory(get_dashboard_dir(), 'maturity.html')

@core_bp.route('/guide')
def serve_guide():
    return send_from_directory(get_dashboard_dir(), 'guide.html')

@core_bp.route('/synaptic')
def serve_synaptic_alias():
    return send_from_directory(get_dashboard_dir(), 'synaptic.html')

@core_bp.route('/terminology')
def serve_terminology():
    return send_from_directory(get_dashboard_dir(), 'terminology.html')

@core_bp.route('/harness')
@core_bp.route('/harness.html')
def serve_harness():
    return send_from_directory(get_dashboard_dir(), 'harness.html')


# --- n8n Workflow Catalog API ---
def _detect_trigger(wf):
    for node in wf.get('nodes', []):
        ntype = node.get('type', '')
        if 'scheduleTrigger' in ntype:
            params = node.get('parameters', {}).get('rule', {}).get('interval', [{}])
            if params:
                p = params[0]
                if 'hoursInterval' in p:
                    return f"⏰ {p['hoursInterval']}시간"
                elif 'minutesInterval' in p:
                    return f"⏰ {p['minutesInterval']}분"
            return '⏰ Schedule'
        elif 'webhook' in ntype:
            return '🔗 Webhook'
        elif 'manualTrigger' in ntype:
            return '👆 Manual'
    return '❓ Unknown'

@core_bp.route('/api/workflows')
def list_n8n_workflows():
    """List all available n8n workflow templates."""
    wf_dir = os.path.join(os.path.dirname(get_dashboard_dir()), 'n8n_workflows')
    workflows = []
    for fpath in sorted(_glob.glob(os.path.join(wf_dir, '*.json'))):
        fname = os.path.basename(fpath)
        try:
            with open(fpath, 'r') as f:
                wf = _json.load(f)
            workflows.append({
                'file': fname,
                'name': wf.get('name', fname),
                'nodes': len(wf.get('nodes', [])),
                'trigger': _detect_trigger(wf),
                'size': os.path.getsize(fpath),
            })
        except Exception:
            workflows.append({'file': fname, 'name': fname, 'error': 'parse_failed'})
    return jsonify({'workflows': workflows, 'total': len(workflows)})

@core_bp.route('/api/workflows/<filename>')
def get_n8n_workflow(filename):
    """Download a specific n8n workflow JSON."""
    wf_dir = os.path.join(os.path.dirname(get_dashboard_dir()), 'n8n_workflows')
    if not filename.endswith('.json'):
        filename += '.json'
    fpath = os.path.join(wf_dir, filename)
    if not os.path.isfile(fpath):
        return jsonify({'error': 'Workflow not found'}), 404
    return send_from_directory(os.path.abspath(wf_dir), filename, mimetype='application/json')

@core_bp.route('/api/workflows/executions')
def list_workflow_executions():
    """List recent n8n workflow executions from Neo4j."""
    storage = current_app.extensions.get('neo4j_storage')
    if storage is None:
        return jsonify({"executions": []}), 503

    try:
        driver = current_app.extensions.get('neo4j_driver')
        if driver is None:
            return jsonify({"executions": [], "error": "Neo4j driver not initialized"}), 503
        with driver.session() as session:
            result = session.run('''
                MATCH (e:ExecutionLog)
                RETURN e.source AS source, e.status AS status, 
                       e.timestamp AS timestamp, e.details AS details
                ORDER BY e.timestamp DESC LIMIT 50
            ''')
            executions = []
            for record in result:
                try:
                    details = _json.loads(record['details']) if record['details'] else {}
                except:
                    details = {}
                if hasattr(record['timestamp'], 'iso_format'):
                    ts = record['timestamp'].iso_format()
                else:
                    ts = str(record['timestamp'])
                executions.append({
                    'source': record['source'],
                    'status': record['status'],
                    'timestamp': ts,
                    'details': details
                })
        return jsonify({"executions": executions})
    except Exception as e:
        logger.error(f"Failed to fetch execution logs: {e}")
        return jsonify({"executions": [], "error": str(e)}), 500


# --- Health / Status API ---
@core_bp.route('/health')
@core_bp.route('/api/health')
def health():
    """
    표준화된 헬스체크 엔드포인트.
    - 모든 구성 요소가 정상이면 200 OK
    - 핵심 구성 요소(neo4j)가 비정상이면 503 Service Unavailable
    """
    storage = current_app.extensions.get('neo4j_storage')
    neo4j_status = 'disconnected'
    node_count = 0

    if storage is not None:
        try:
            driver = current_app.extensions.get('neo4j_driver')
            if driver is None:
                neo4j_status = 'not_initialized'
                raise RuntimeError('Shared Neo4j driver not available')
            with driver.session() as session:
                result = session.run('MATCH (n) RETURN count(n) AS cnt')
                node_count = result.single()['cnt']
                neo4j_status = 'connected'
        except Exception:
            neo4j_status = 'error'

    backend = current_app.config.get('STORAGE_BACKEND', 'neo4j')
    llm_url = os.environ.get('LLM_BASE_URL', 'not configured')
    llm_model = os.environ.get('LLM_MODEL_NAME', 'not configured')

    # Embedding health (quick check based on config)
    embed_provider = os.environ.get('EMBEDDING_PROVIDER', 'auto')
    embed_base_url = os.environ.get('EMBEDDING_BASE_URL', '')
    embedding_status = 'configured' if embed_base_url else 'not configured'

    # Webhook status
    webhook_enabled = os.environ.get('WEBHOOK_ENABLED', 'false').lower() == 'true'
    webhook_urls = [u for u in os.environ.get('WEBHOOK_URL', '').split(',') if u.strip()]

    overall = 'healthy' if neo4j_status == 'connected' else 'degraded'

    body = {
        'status': overall,
        'service': 'Mories (MiroFish × Supermemory)',
        'backend': backend,
        'neo4j': {
            'status': neo4j_status,
            'node_count': node_count,
        },
        'llm': {
            'provider': os.environ.get('LLM_PROVIDER', 'ollama'),
            'base_url': llm_url,
            'model': llm_model,
        },
        'embedding': {
            'provider': embed_provider,
            'base_url': embed_base_url or 'not configured',
            'status': embedding_status,
        },
        'harness': {
            'webhook_enabled': webhook_enabled,
            'webhook_targets': len(webhook_urls),
            'supermemory': 'configured' if os.environ.get('SUPERMEMORY_API_KEY') else 'not configured',
        },
        'components': {
            'neo4j': neo4j_status,
            'scheduler': 'running' if current_app.extensions.get('memory_scheduler') else 'stopped',
            'supermemory': 'configured' if os.environ.get('SUPERMEMORY_API_KEY') else 'not configured',
        },
        'adapters': 11,
        'observers': 3,
        'search_agents': 3,
    }

    http_status = 200 if overall == 'healthy' else 503
    return jsonify(body), http_status


# --- Harness Actions ---
@core_bp.route('/api/harness/hitl/pending', methods=['GET'])
def get_pending_hitl():
    """
    Returns a list of all currently suspended state files that await HITL resolution.
    """
    state_dir = "./harness_state"
    pending = []
    if os.path.exists(state_dir):
        for fname in os.listdir(state_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(state_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        state = _json.load(f)
                        if state.get("run_status") == "suspended":
                            suspension_point = state.get("run_suspension_point")
                            run_id = state.get("id", state.get("run_id", fname.replace(".json", "")))
                            step_id = suspension_point.get("step_id") if suspension_point else None
                            if step_id:
                                pending.append({
                                    "run_id": run_id,
                                    "step_id": step_id,
                                    "harness_uuid": state.get("harness_uuid", ""),
                                    "suspended_at": state.get("updated_at", ""),
                                    "context_preview": state.get("context", {}).get("trigger", "N/A")
                                })
                except Exception:
                    pass
    return jsonify({"status": "success", "pending": pending}), 200


@core_bp.route('/api/harness/hitl/resolve', methods=['POST'])
def resolve_hitl():
    """
    Resolve a Human-In-The-Loop gate by providing an answer (approved/rejected).
    Body: {"run_id": "...", "step_id": "...", "approved": true, "feedback": "looks good"}
    """
    data = request.get_json(silent=True) or {}
    run_id = data.get('run_id')
    step_id = data.get('step_id')
    
    if not run_id or not step_id:
        return jsonify({"error": "run_id and step_id are required"}), 400
        
    state_file = os.path.join("./harness_state", f"{run_id}.json")
    if not os.path.exists(state_file):
        return jsonify({"error": f"Target state file not found for run_id {run_id}"}), 404
        
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            state = _json.load(f)
            
        context = state.get('context', {})
        hitl_responses = context.get('_hitl_responses', {})
        
        hitl_responses[step_id] = {
            "approved": data.get("approved", True),
            "feedback": data.get("feedback", ""),
            "metadata": data.get("metadata", {})
        }
        
        context['_hitl_responses'] = hitl_responses
        state['context'] = context
        
        with open(state_file, 'w', encoding='utf-8') as f:
            _json.dump(state, f, ensure_ascii=False, indent=2)
            
        # Optional: auto-resume the workflow process here by submitting to a background worker
        # Currently, just updates the state file.
        return jsonify({"status": "ok", "message": f"HITL for {step_id} resolved."})
        
    except Exception as e:
        logger.error(f"Error resolving HITL: {e}")
        return jsonify({"error": str(e)}), 500


# --- MCP Tools via REST (for n8n / external agents) ---
@core_bp.route('/api/mcp', methods=['POST'])
def mcp_proxy():
    """MCP JSON-RPC endpoint embedded in Flask for network accessibility."""
    import sys
    # Add root dir to sys path to import mcp_server
    mcp_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    if mcp_path not in sys.path:
        sys.path.insert(0, mcp_path)

    from mcp_server.server import handle_jsonrpc
    from mcp_server.config import MCPConfig

    allowed_scopes = ['*']
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    
    if MCPConfig.MCP_API_KEY and token == MCPConfig.MCP_API_KEY:
        allowed_scopes = ['*']  # Admin bypass
    elif token:
        import httpx
        try:
            resp = httpx.post(
                f"{MCPConfig.API_BASE_URL}/api/security/keys/verify",
                json={"api_key": token},
                timeout=5.0
            )
            if resp.status_code == 200 and resp.json().get("valid"):
                allowed_scopes = resp.json().get("principal", {}).get("allowed_scopes", [])
            else:
                return jsonify({"error": "Unauthorized / Revoked key"}), 401
        except Exception as e:
            logger.error(f"Auth verification failed: {e}")
            return jsonify({"error": "Auth verification failed"}), 500
    elif MCPConfig.MCP_API_KEY and not token:
        return jsonify({"error": "Unauthorized: API Key required"}), 401

    if request.content_type != 'application/json':
        return jsonify({"error": "Content-Type must be application/json"}), 415

    message = request.get_json(silent=True)
    if not message:
        return jsonify({"error": "Invalid JSON"}), 400

    response = handle_jsonrpc(message, allowed_scopes)
    if response is None:
        return '', 204
    return jsonify(response)


@core_bp.route('/api/search', methods=['POST'])
def search_api():
    """Direct REST search endpoint (simpler than MCP JSON-RPC)."""
    import sys
    mcp_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    if mcp_path not in sys.path:
        sys.path.insert(0, mcp_path)

    from mcp_server.tools import mories_search
    data = request.get_json(silent=True) or {}
    query = data.get('query', '')
    graph_id = data.get('graph_id', '')
    limit = data.get('limit', 10)

    if not query:
        return jsonify({"error": "query is required"}), 400

    result = mories_search(query=query, graph_id=graph_id, limit=limit)

    # Auto-boost retrieved memories
    try:
        from ..storage.memory_manager import MemoryManager
        mgr = MemoryManager.get_instance()
        uuids = []
        if isinstance(result, dict):
            for item in result.get('results', result.get('entities', [])):
                if isinstance(item, dict) and item.get('uuid'):
                    uuids.append(item['uuid'])
        if uuids:
            boosted = mgr.boost_on_retrieval(uuids)
            if isinstance(result, dict):
                result['retrieval_boosted'] = boosted
    except Exception as e:
        logger.debug(f"Retrieval boost on search: {e}")

    return jsonify(result)


@core_bp.route('/api/query', methods=['POST'])
def query_api():
    """Direct REST Cypher query endpoint (read-only)."""
    import sys
    mcp_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    if mcp_path not in sys.path:
        sys.path.insert(0, mcp_path)

    from mcp_server.tools import mories_graph_query
    data = request.get_json(silent=True) or {}
    cypher = data.get('cypher', '')
    params = data.get('params', {})
    limit = data.get('limit', 50)

    if not cypher:
        return jsonify({"error": "cypher is required"}), 400

    result = mories_graph_query(cypher=cypher, params=params, limit=limit)
    return jsonify(result)
