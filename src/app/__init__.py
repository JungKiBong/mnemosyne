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

import uuid
import time
from prometheus_client import make_wsgi_app, Counter, Histogram
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from prometheus_client import REGISTRY

def _get_or_create_metric(MetricClass, name, desc, labels):
    try:
        return MetricClass(name, desc, labels)
    except ValueError:
        # Metric already exists (e.g. during pytest collection)
        return REGISTRY._names_to_collectors[name.replace('_total', '') if '_total' in name and MetricClass == Counter else name]

# Metrics definitions
request_count = _get_or_create_metric(Counter, 'http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'http_status'])
request_latency = _get_or_create_metric(Histogram, 'http_request_duration_seconds', 'HTTP Request Duration', ['endpoint'])
neo4j_query_latency = _get_or_create_metric(Histogram, 'neo4j_query_duration_seconds', 'Neo4j Query Duration', ['operation', 'status'])
cache_hits = _get_or_create_metric(Counter, 'memory_cache_hits_total', 'Memory Cache Hits', ['entity_type'])
cache_misses = _get_or_create_metric(Counter, 'memory_cache_misses_total', 'Memory Cache Misses', ['entity_type'])


def create_app(config_class=Config):
    """Flask application factory function"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure JSON encoding: ensure Chinese displays directly (not as \uXXXX)
    # Flask >= 2.3 uses app.json.ensure_ascii, older versions use JSON_AS_ASCII config
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Custom JSON provider: handle Neo4j DateTime and Python datetime objects
    from flask.json.provider import DefaultJSONProvider
    import json
    from datetime import datetime as _dt, date as _date

    class MirofishJSONProvider(DefaultJSONProvider):
        ensure_ascii = False

        @staticmethod
        def default(o):
            # Neo4j DateTime / Date / Time / Duration
            try:
                import neo4j.time
                if isinstance(o, (neo4j.time.DateTime, neo4j.time.Date, neo4j.time.Time)):
                    return o.iso_format()
                if isinstance(o, neo4j.time.Duration):
                    return str(o)
            except ImportError:
                pass
            # Standard Python datetime / date
            if isinstance(o, _dt):
                return o.isoformat()
            if isinstance(o, _date):
                return o.isoformat()
            return super().default(o)

    app.json_provider_class = MirofishJSONProvider
    app.json = MirofishJSONProvider(app)

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
    cors_origins = app.config.get('CORS_ORIGINS', ['*'])
    CORS(app, resources={r"/api/*": {"origins": cors_origins}})

    # Initialize Rate Limiter
    from .utils.limiter import limiter
    limiter.init_app(app)

    # Register Global Error Handlers
    from .utils.error_handlers import register_error_handlers
    register_error_handlers(app)

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

    # --- Initialize shared Neo4j driver (DI singleton) ---
    try:
        from neo4j import GraphDatabase
        neo4j_driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
        )
        app.extensions['neo4j_driver'] = neo4j_driver

        # Initialize MemoryManager singleton with shared driver
        from .storage.memory_manager import MemoryManager
        mm = MemoryManager.get_instance(driver=neo4j_driver)
        app.extensions['memory_manager'] = mm

        # Initialize RBAC singleton with shared driver
        from .security.memory_rbac import get_rbac
        rbac = get_rbac(driver=neo4j_driver)
        app.extensions['rbac'] = rbac

        if should_log_startup:
            logger.info("MemoryManager + RBAC singletons initialized (shared Neo4j driver)")
    except Exception as e:
        logger.warning(f"Neo4j driver/MemoryManager init failed: {e}")
        app.extensions['neo4j_driver'] = None
        app.extensions['memory_manager'] = None

    # The neo4j driver manages its own connection pool and should live as long as the application.
    # Closing it inside teardown_appcontext destroys it after the first request.
    # Teardown logic handled at the application level.
    # Register simulation process cleanup function (ensure all simulation processes terminate on server shutdown)
    try:
        from .plugins.oasis.simulation_runner import SimulationRunner
        SimulationRunner.register_cleanup()
        if should_log_startup:
            logger.info("Simulation process cleanup function registered")
    except ImportError:
        logger.info("OASIS plugin not installed. Skipping simulation cleanup registration.")

    # Request tracking middleware
    @app.before_request
    def set_request_tracking():
        request.correlation_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))
        request.start_time = time.time()

    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Request: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Request body: {request.get_json(silent=True)}")

    @app.after_request
    def log_response_and_metrics(response):
        # Set correlation ID
        if hasattr(request, 'correlation_id'):
            response.headers['X-Correlation-ID'] = request.correlation_id
            
        logger = get_logger('mirofish.request')
        logger.debug(f"Response: {response.status_code}")
        
        # Record metrics (except for /metrics endpoint itself to avoid noise)
        if request.path != '/metrics':
            latency = time.time() - getattr(request, 'start_time', time.time())
            request_latency.labels(endpoint=request.path).observe(latency)
            request_count.labels(
                method=request.method,
                endpoint=request.path,
                http_status=response.status_code
            ).inc()
            
        return response

    # Register blueprints
    from .api import graph_bp, terminology_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(terminology_bp, url_prefix='/api/terminology')

    try:
        from .plugins.oasis import simulation_bp
        app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
        if should_log_startup:
            logger.info("OASIS simulation blueprint registered")
    except ImportError:
        logger.info("OASIS plugin not installed. Skipping simulation blueprint registration.")

    # API v1 Versioning (Phase 2.3)
    from .api.v1 import api_v1_bp
    app.register_blueprint(api_v1_bp, url_prefix='/api/v1')

    # Cognitive Memory API (Phase 7)
    from .api.memory import memory_bp
    app.register_blueprint(memory_bp, url_prefix='/api/v1/memory')

    # Ingest API (Ingestion, Pipeline, Gateway)
    from .api.ingest import ingest_bp
    app.register_blueprint(ingest_bp, url_prefix='/api/v1/ingest')
    # Analytics API (Maturity, Reconciliation, Reports, Data Products)
    from .api.analytics import analytics_bp
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
    # Harness Analytics API (v4: Execution Trends, Tool Reliability)
    from .api.harness_analytics import harness_analytics_bp
    app.register_blueprint(harness_analytics_bp, url_prefix='/api')
    # Admin API (Security, Settings, Tools)
    from .api.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

    # Start Memory Scheduler (background thread)
    try:
        from .services.memory_scheduler import start_scheduler
        scheduler = start_scheduler()
        app.extensions['memory_scheduler'] = scheduler
        logger.info("Memory Scheduler started (daily decay, STM cleanup, scope promotion)")
    except Exception as e:
        logger.warning(f"Memory Scheduler failed to start: {e}")

    # Core/UI Routes (Dashboard, n8n, MCP, Health)
    from .api.core import core_bp
    app.register_blueprint(core_bp)
    
    if should_log_startup:
        logger.info("MiroFish-Offline Backend startup complete")
        logger.info("Dashboard: http://localhost:5001/")
        logger.info("Health API: http://localhost:5001/api/health")
        logger.info("MCP Endpoint: http://localhost:5001/api/mcp")
        logger.info("Metrics: http://localhost:5001/metrics")

    # Mount prometheus WSGI app on /metrics
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        '/metrics': make_wsgi_app()
    })

    return app

