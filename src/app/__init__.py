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

    @app.teardown_appcontext
    def close_neo4j_driver(exception):
        driver = app.extensions.get('neo4j_driver')
        if driver:
            try:
                driver.close()
            except Exception:
                pass

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
    from .api import graph_bp, simulation_bp, terminology_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(terminology_bp, url_prefix='/api/terminology')

    # Data Ingestion API (Phase 1.5)

    # Cognitive Memory API (Phase 7)
    from .api.memory import memory_bp
    app.register_blueprint(memory_bp, url_prefix='/api/memory')

    # Ingest API (Ingestion, Pipeline, Gateway)
    from .api.ingest import ingest_bp
    app.register_blueprint(ingest_bp, url_prefix='/api/ingest')
    # Analytics API (Maturity, Reconciliation, Reports, Data Products)
    from .api.analytics import analytics_bp
    app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
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

    return app

