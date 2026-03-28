"""
MiroFish Backend - Flask Application Factory
"""

import os
import warnings

# Suppress multiprocessing resource_tracker warnings (from third-party libraries like transformers)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Flask application factory function"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure JSON encoding: ensure Chinese displays directly (not as \uXXXX)
    # Flask >= 2.3 uses app.json.ensure_ascii, older versions use JSON_AS_ASCII config
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Setup logging
    logger = setup_logger('mirofish')

    # Only print startup info in reloader subprocess (avoid printing twice in debug mode)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish-Offline Backend starting...")
        logger.info("=" * 50)

    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # --- Initialize Storage singleton (DI via app.extensions) ---
    storage_backend = app.config.get('STORAGE_BACKEND', 'neo4j').lower()
    
    try:
        if storage_backend == 'hybrid':
            from .storage.neo4j_storage import Neo4jStorage
            from .storage.hybrid_storage import HybridStorage
            from .storage.supermemory_client import SupermemoryClientWrapper
            
            neo4j_storage = Neo4jStorage()
            sm_client = SupermemoryClientWrapper()
            storage_instance = HybridStorage(neo4j_storage, sm_client)
            
            app.extensions['neo4j_storage'] = storage_instance
            if should_log_startup:
                logger.info("HybridStorage initialized (Neo4j: %s, Supermemory Fallback/Async)", Config.NEO4J_URI)
        else:
            from .storage.neo4j_storage import Neo4jStorage
            storage_instance = Neo4jStorage()
            app.extensions['neo4j_storage'] = storage_instance
            if should_log_startup:
                logger.info("Neo4jStorage initialized (connected to %s)", Config.NEO4J_URI)
                
    except Exception as e:
        logger.error("Storage initialization failed: %s", e)
        # Store None so endpoints can return 503 gracefully
        app.extensions['neo4j_storage'] = None


    # Register simulation process cleanup function (ensure all simulation processes terminate on server shutdown)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Simulation process cleanup function registered")

    # Request logging middleware
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Request: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Request body: {request.get_json(silent=True)}")

    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"Response: {response.status_code}")
        return response

    # Register blueprints
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')

    # Data Ingestion API (Phase 1.5)
    from .api.ingest import ingest_bp
    app.register_blueprint(ingest_bp, url_prefix='/api/ingest')

    # Cognitive Memory API (Phase 7)
    from .api.memory import memory_bp
    app.register_blueprint(memory_bp, url_prefix='/api/memory')

    # Memory Audit Trail API (Phase 10)
    from .api.memory_audit import audit_bp
    app.register_blueprint(audit_bp)

    # Memory Scopes API (Phase 8)
    from .api.memory_scopes import scopes_bp
    app.register_blueprint(scopes_bp)

    # Synaptic Bridge API (Phase 9)
    from .api.synaptic import synaptic_bp
    app.register_blueprint(synaptic_bp)

    # Data Product API (Phase 11)
    from .api.data_product import data_product_bp
    app.register_blueprint(data_product_bp)

    # MCP Tools API (Agent-callable tools)
    from .api.tools import tools_bp
    app.register_blueprint(tools_bp)

    # Pipeline API (Ingest → STM auto-flow)
    from .api.pipeline import pipeline_bp
    app.register_blueprint(pipeline_bp)

    # External Data Gateway (n8n, NiFi, Spark, API)
    from .api.gateway import gateway_bp
    app.register_blueprint(gateway_bp)

    # Security API (RBAC + Encryption)
    from .api.security import security_bp
    app.register_blueprint(security_bp)

    # Maturity API (Knowledge Lifecycle)
    from .api.maturity import maturity_bp
    app.register_blueprint(maturity_bp)

    # Reconciliation API (Data Consistency)
    from .api.reconciliation import reconciliation_bp
    app.register_blueprint(reconciliation_bp)

    # Permanent Memory & Category Extension API (Phase 16)
    from .api.permanent_memory import permanent_bp
    app.register_blueprint(permanent_bp, url_prefix='/api/memory')

    # Graph (Project/Scope) Visibility API
    from .api.graphs import graphs_bp
    app.register_blueprint(graphs_bp)

    # Settings API (Runtime LLM/Embedding configuration)
    from .api.settings import settings_bp
    app.register_blueprint(settings_bp)

    # Workflow Gallery API (n8n workflow JSON serving)
    from .api.workflows import workflow_bp
    app.register_blueprint(workflow_bp, url_prefix='/api/workflows')

    # Start Memory Scheduler (background thread)
    try:
        from .services.memory_scheduler import start_scheduler
        scheduler = start_scheduler()
        app.extensions['memory_scheduler'] = scheduler
        logger.info("Memory Scheduler started (daily decay, STM cleanup, scope promotion)")
    except Exception as e:
        logger.warning(f"Memory Scheduler failed to start: {e}")

    dashboard_dir = os.path.join(os.path.dirname(__file__), '../../dashboard')
    if os.path.isdir(dashboard_dir):
        from flask import send_from_directory
        @app.route('/')
        @app.route('/dashboard')
        def serve_dashboard():
            return send_from_directory(os.path.abspath(dashboard_dir), 'index.html')

        @app.route('/dashboard/<path:filename>')
        def serve_dashboard_static(filename):
            return send_from_directory(os.path.abspath(dashboard_dir), filename)

        @app.route('/memory')
        def serve_memory_dashboard():
            return send_from_directory(os.path.abspath(dashboard_dir), 'memory.html')

        @app.route('/memory/history')
        def serve_memory_history():
            return send_from_directory(os.path.abspath(dashboard_dir), 'memory_history.html')

        @app.route('/memory/synaptic')
        def serve_synaptic():
            return send_from_directory(os.path.abspath(dashboard_dir), 'synaptic.html')

        @app.route('/api-docs')
        @app.route('/api-explorer')
        def serve_api_explorer():
            return send_from_directory(os.path.abspath(dashboard_dir), 'api.html')

        @app.route('/workflows')
        @app.route('/n8n-workflows')
        def serve_workflow_catalog():
            return send_from_directory(os.path.abspath(dashboard_dir), 'workflows.html')

        # --- n8n Workflow Catalog API ---
        import json as _json
        import glob as _glob

        @app.route('/api/workflows')
        def list_n8n_workflows():
            """List all available n8n workflow templates."""
            wf_dir = os.path.join(os.path.dirname(dashboard_dir), 'n8n_workflows')
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
            from flask import jsonify as _jf
            return _jf({'workflows': workflows, 'total': len(workflows)})

        @app.route('/api/workflows/<filename>')
        def get_n8n_workflow(filename):
            """Download a specific n8n workflow JSON."""
            wf_dir = os.path.join(os.path.dirname(dashboard_dir), 'n8n_workflows')
            if not filename.endswith('.json'):
                filename += '.json'
            fpath = os.path.join(wf_dir, filename)
            if not os.path.isfile(fpath):
                from flask import jsonify as _jf
                return _jf({'error': 'Workflow not found'}), 404
            return send_from_directory(os.path.abspath(wf_dir), filename,
                                       mimetype='application/json')

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

        @app.route('/api/workflows/executions')
        def list_workflow_executions():
            """List recent n8n workflow executions from Neo4j."""
            storage = app.extensions.get('neo4j_storage')
            if storage is None:
                from flask import jsonify as _jf
                return _jf({"executions": []}), 503

            try:
                from neo4j import GraphDatabase
                from .config import Config
                driver = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD))
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
                driver.close()
                from flask import jsonify as _jf
                return _jf({"executions": executions})
            except Exception as e:
                logger.error(f"Failed to fetch execution logs: {e}")
                from flask import jsonify as _jf
                return _jf({"executions": [], "error": str(e)}), 500

    # --- Health / Status API ---
    @app.route('/health')
    @app.route('/api/health')
    def health():
        storage = app.extensions.get('neo4j_storage')
        neo4j_status = 'disconnected'
        node_count = 0

        if storage is not None:
            try:
                from neo4j import GraphDatabase
                driver = GraphDatabase.driver(
                    Config.NEO4J_URI,
                    auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
                )
                with driver.session() as session:
                    result = session.run('MATCH (n) RETURN count(n) AS cnt')
                    node_count = result.single()['cnt']
                    neo4j_status = 'connected'
                driver.close()
            except Exception:
                neo4j_status = 'error'

        backend = app.config.get('STORAGE_BACKEND', 'neo4j')
        llm_url = Config.LLM_BASE_URL or 'not configured'
        llm_model = Config.LLM_MODEL_NAME or 'not configured'

        return {
            'status': 'healthy',
            'service': 'Mories (MiroFish × Supermemory)',
            'backend': backend,
            'neo4j': neo4j_status,
            'neo4j_nodes': node_count,
            'supermemory': 'configured' if os.environ.get('SUPERMEMORY_API_KEY') else 'not configured',
            'llm': {
                'provider': os.environ.get('LLM_PROVIDER', 'ollama'),
                'base_url': llm_url,
                'model': llm_model,
            },
            'adapters': 11,
            'observers': 3,
            'search_agents': 3,
            'components': {
                'neo4j': neo4j_status,
                'scheduler': 'running' if app.extensions.get('memory_scheduler') else 'stopped',
                'supermemory': 'configured' if os.environ.get('SUPERMEMORY_API_KEY') else 'not configured',
            },
        }

    # --- MCP Tools via REST (for n8n / external agents) ---
    @app.route('/api/mcp', methods=['POST'])
    def mcp_proxy():
        """MCP JSON-RPC endpoint embedded in Flask for network accessibility."""
        import sys
        mcp_path = os.path.join(os.path.dirname(__file__), '../..')
        if mcp_path not in sys.path:
            sys.path.insert(0, mcp_path)

        from flask import request as flask_request, jsonify as flask_jsonify
        from mcp_server.server import handle_jsonrpc

        message = flask_request.get_json(silent=True)
        if not message:
            return flask_jsonify({"error": "Invalid JSON"}), 400

        response = handle_jsonrpc(message)
        if response is None:
            return '', 204
        return flask_jsonify(response)

    @app.route('/api/search', methods=['POST'])
    def search_api():
        """Direct REST search endpoint (simpler than MCP JSON-RPC)."""
        from flask import request as flask_request, jsonify as flask_jsonify
        import sys
        mcp_path = os.path.join(os.path.dirname(__file__), '../..')
        if mcp_path not in sys.path:
            sys.path.insert(0, mcp_path)

        from mcp_server.tools import mories_search
        data = flask_request.get_json(silent=True) or {}
        query = data.get('query', '')
        graph_id = data.get('graph_id', '')
        limit = data.get('limit', 10)

        if not query:
            return flask_jsonify({"error": "query is required"}), 400

        result = mories_search(query=query, graph_id=graph_id, limit=limit)

        # Auto-boost retrieved memories (Retrieval Boost)
        try:
            from .storage.memory_manager import MemoryManager
            mgr = MemoryManager()
            uuids = []
            if isinstance(result, dict):
                for item in result.get('results', result.get('entities', [])):
                    if isinstance(item, dict) and item.get('uuid'):
                        uuids.append(item['uuid'])
            if uuids:
                boosted = mgr.boost_on_retrieval(uuids)
                if isinstance(result, dict):
                    result['retrieval_boosted'] = boosted
            mgr.close()
        except Exception as e:
            logger.debug(f"Retrieval boost on search: {e}")

        return flask_jsonify(result)


    @app.route('/api/query', methods=['POST'])
    def query_api():
        """Direct REST Cypher query endpoint (read-only)."""
        from flask import request as flask_request, jsonify as flask_jsonify
        import sys
        mcp_path = os.path.join(os.path.dirname(__file__), '../..')
        if mcp_path not in sys.path:
            sys.path.insert(0, mcp_path)

        from mcp_server.tools import mories_graph_query
        data = flask_request.get_json(silent=True) or {}
        cypher = data.get('cypher', '')
        params = data.get('params', {})
        limit = data.get('limit', 50)

        if not cypher:
            return flask_jsonify({"error": "cypher is required"}), 400

        result = mories_graph_query(cypher=cypher, params=params, limit=limit)
        return flask_jsonify(result)

    if should_log_startup:
        logger.info("MiroFish-Offline Backend startup complete")
        logger.info("Dashboard: http://localhost:5001/")
        logger.info("Health API: http://localhost:5001/api/health")
        logger.info("MCP Endpoint: http://localhost:5001/api/mcp")

    return app

