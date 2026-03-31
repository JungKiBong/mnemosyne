"""
REST API for data ingestion.

POST /api/ingest         — one-shot ingestion from any source
POST /api/ingest/batch   — batch ingestion from multiple sources
POST /api/ingest/stream  — start stream ingestion
DELETE /api/ingest/stream — stop stream ingestion
GET /api/ingest/streams  — list active streams
"""
import os
import logging
from flask import Blueprint, request, jsonify, current_app
from ..utils.limiter import limiter

logger = logging.getLogger(__name__)

ingest_bp = Blueprint('ingest', __name__)


def _get_ingestion_service():
    """Lazy-init DataIngestionService from app context."""
    svc = current_app.extensions.get('ingestion_service')
    if svc is None:
        from app.services.ingestion_service import DataIngestionService
        storage = current_app.extensions.get('neo4j_storage')
        if storage is None:
            return None
        svc = DataIngestionService(storage)
        current_app.extensions['ingestion_service'] = svc
    return svc


@ingest_bp.route('', methods=['POST'])
@limiter.limit("50 per minute")
def ingest():
    """
    One-shot data ingestion.

    Request JSON:
    {
        "graph_id": "my_graph",
        "source_ref": "/path/to/file.csv",
        "options": {}  // adapter-specific options
    }
    """
    data = request.get_json(silent=True) or {}
    graph_id = data.get('graph_id')
    source_ref = data.get('source_ref')

    if not graph_id or not source_ref:
        return jsonify({"error": "graph_id and source_ref are required"}), 400

    svc = _get_ingestion_service()
    if svc is None:
        return jsonify({"error": "Storage backend not initialized"}), 503

    options = data.get('options', {})

    try:
        result = svc.ingest(graph_id, source_ref, **options)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Ingestion failed: %s", e, exc_info=True)
        return jsonify({"error": f"Ingestion failed: {e}"}), 500


@ingest_bp.route('/batch', methods=['POST'])
def ingest_batch():
    """
    Batch ingestion from multiple sources.

    Request JSON:
    {
        "graph_id": "my_graph",
        "source_refs": ["/path/a.csv", "/path/b.json"],
        "options": {}
    }
    """
    data = request.get_json(silent=True) or {}
    graph_id = data.get('graph_id')
    source_refs = data.get('source_refs', [])

    if not graph_id or not source_refs:
        return jsonify({"error": "graph_id and source_refs[] are required"}), 400

    svc = _get_ingestion_service()
    if svc is None:
        return jsonify({"error": "Storage backend not initialized"}), 503

    options = data.get('options', {})

    results = svc.ingest_batch(graph_id, source_refs, **options)
    return jsonify({"results": results}), 200


def _get_task_manager():
    """Lazy-init Background IngestionTaskManager."""
    svc = _get_ingestion_service()
    if svc is None:
        return None
    from app.services.ingestion_task_manager import IngestionTaskManager
    return IngestionTaskManager.get_instance(svc)


@ingest_bp.route('/batch/async', methods=['POST'])
@limiter.limit("10 per minute")
def ingest_batch_async():
    """
    Asynchronous batch ingestion from multiple sources.

    Request JSON:
    {
        "graph_id": "my_graph",
        "source_refs": ["/path/a.csv", "/path/b.json"],
        "options": {}
    }
    """
    data = request.get_json(silent=True) or {}
    graph_id = data.get('graph_id')
    source_refs = data.get('source_refs', [])

    if not graph_id or not source_refs:
        return jsonify({"error": "graph_id and source_refs[] are required"}), 400

    mgr = _get_task_manager()
    if mgr is None:
        return jsonify({"error": "Storage backend not initialized"}), 503

    options = data.get('options', {})
    job_id = mgr.submit_batch(graph_id, source_refs, options)
    
    return jsonify({
        "job_id": job_id,
        "status": "queued"
    }), 202


@ingest_bp.route('/batch/status/<job_id>', methods=['GET'])
def get_batch_status(job_id):
    """
    Get the status of an asynchronous batch job.
    """
    mgr = _get_task_manager()
    if mgr is None:
        return jsonify({"error": "Storage backend not initialized"}), 503

    status = mgr.get_status(job_id)
    if status.get("error"):
        return jsonify(status), 404
        
    return jsonify(status), 200


@ingest_bp.route('/stream', methods=['POST'])
def start_stream():
    """
    Start stream ingestion.

    Request JSON:
    {
        "graph_id": "my_graph",
        "source_ref": "kafka://broker:9092",
        "config": { "topics": ["news"], "bootstrap_servers": "broker:9092" }
    }
    """
    data = request.get_json(silent=True) or {}
    graph_id = data.get('graph_id')
    source_ref = data.get('source_ref')

    if not graph_id or not source_ref:
        return jsonify({"error": "graph_id and source_ref are required"}), 400

    svc = _get_ingestion_service()
    if svc is None:
        return jsonify({"error": "Storage backend not initialized"}), 503

    config = data.get('config', {})
    stream_id = svc.start_stream(graph_id, source_ref, config=config)
    return jsonify({"stream_id": stream_id, "status": "started"}), 202


@ingest_bp.route('/stream', methods=['DELETE'])
def stop_stream():
    """Stop a running stream. Query param: source_ref"""
    source_ref = request.args.get('source_ref')
    if not source_ref:
        return jsonify({"error": "source_ref query param required"}), 400

    svc = _get_ingestion_service()
    if svc is None:
        return jsonify({"error": "Storage backend not initialized"}), 503

    svc.stop_stream(source_ref)
    return jsonify({"status": "stopped", "source_ref": source_ref}), 200


@ingest_bp.route('/streams', methods=['GET'])
def list_streams():
    """List currently active stream sources."""
    svc = _get_ingestion_service()
    if svc is None:
        return jsonify({"error": "Storage backend not initialized"}), 503

    return jsonify({"active_streams": svc.active_streams()}), 200


# --- Merged from pipeline.py ---
"""
Pipeline API — Ingest→STM→LTM auto-flow + Scheduler control

Endpoints:
  POST /api/pipeline/process       — Process raw content through memory pipeline
  POST /api/pipeline/ingest-auto   — Ingest + auto-flow to cognitive memory
  GET  /api/pipeline/scheduler     — Get scheduler status
  POST /api/pipeline/scheduler/decay — Trigger manual decay
"""




_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from ..services.memory_pipeline import MemoryPipeline
        _pipeline = MemoryPipeline()
    return _pipeline


@ingest_bp.route('/pipeline/process', methods=['POST'])
def process_content():
    """
    Process content through memory pipeline.

    Body:
    {
      "content": "Raw text to process...",
      "source": "user_note",
      "graph_id": "default",
      "scope": "personal",
      "auto_promote": true
    }
    """
    data = request.get_json(force=True)
    content = data.get('content', '')
    source = data.get('source', 'api')
    graph_id = data.get('graph_id', 'default')
    scope = data.get('scope')
    auto_promote = data.get('auto_promote', True)

    if not content:
        return jsonify({"error": "content is required"}), 400

    pipeline = _get_pipeline()
    metadata = {"scope": scope} if scope else {}

    result = pipeline.process_ingestion_result(
        graph_id=graph_id,
        source_ref=source,
        text=content,
        metadata=metadata,
        auto_promote=auto_promote,
    )
    return jsonify(result)


@ingest_bp.route('/pipeline/ingest-auto', methods=['POST'])
def ingest_auto():
    """
    Ingest from source AND automatically flow through cognitive memory pipeline.

    Body:
    {
      "graph_id": "my_graph",
      "source_ref": "/path/to/file.pdf",
      "auto_promote": true,
      "options": {}
    }
    """
    data = request.get_json(force=True)
    graph_id = data.get('graph_id')
    source_ref = data.get('source_ref')
    auto_promote = data.get('auto_promote', True)
    options = data.get('options', {})

    if not graph_id or not source_ref:
        return jsonify({"error": "graph_id and source_ref are required"}), 400

    # Step 1: Ingest via normal adapter
    svc = current_app.extensions.get('ingestion_service')
    if svc is None:
        try:
            from ..services.ingestion_service import DataIngestionService
            storage = current_app.extensions.get('neo4j_storage')
            if storage is None:
                return jsonify({"error": "Storage not initialized"}), 503
            svc = DataIngestionService(storage)
            current_app.extensions['ingestion_service'] = svc
        except Exception as e:
            return jsonify({"error": f"Service init failed: {e}"}), 503

    try:
        adapter = svc.find_adapter(source_ref)
        from ..adapters.base import IngestionResult
        result: IngestionResult = adapter.ingest(source_ref, **options)
    except Exception as e:
        return jsonify({"error": f"Ingestion failed: {e}"}), 500

    # Step 2: Flow through memory pipeline
    pipeline = _get_pipeline()
    pipeline_result = pipeline.process_ingestion_result(
        graph_id=graph_id,
        source_ref=source_ref,
        text=result.text or "",
        entities=result.entities or [],
        metadata=result.metadata or {},
        auto_promote=auto_promote,
    )

    # Combine both results
    return jsonify({
        "ingestion": {
            "source": source_ref,
            "adapter": type(adapter).__name__,
            "text_length": len(result.text) if result.text else 0,
            "entities": len(result.entities or []),
        },
        "pipeline": pipeline_result,
    })


@ingest_bp.route('/pipeline/scheduler', methods=['GET'])
def scheduler_status():
    """Get memory scheduler status."""
    from ..services.memory_scheduler import get_scheduler
    scheduler = get_scheduler()
    return jsonify(scheduler.get_status())


@ingest_bp.route('/pipeline/scheduler/decay', methods=['POST'])
def trigger_decay():
    """Manually trigger decay cycle."""
    data = request.get_json(silent=True) or {}
    dry_run = data.get('dry_run', False)

    from ..storage.memory_manager import MemoryManager
    mgr = MemoryManager.get_instance()
    result = mgr.run_decay(dry_run=dry_run)
    return jsonify(result)


# --- Merged from gateway.py ---
"""
External Data Gateway — Phase 12

Webhook/REST endpoints for external systems to push data into memory:
  - n8n workflows → POST /api/gateway/webhook
  - Apache NiFi → POST /api/gateway/nifi
  - Spark jobs → POST /api/gateway/spark
  - Generic API → POST /api/gateway/ingest
  - Bulk/batch → POST /api/gateway/batch

Each gateway normalizes incoming data and routes through MemoryPipeline
for automatic STM→evaluation→LTM flow.

Authentication: API Key or Bearer token (via MemoryRBAC).
"""

import hashlib
import hmac
import time
from functools import wraps
from datetime import datetime, timezone
import json


def log_execution(source: str, status: str, details: dict):
    """Log external workflow executions (e.g., n8n, NiFi) to Neo4j."""
    try:
        from flask import current_app
        driver = current_app.extensions.get('neo4j_driver')
        if driver is None:
            logger.warning("Shared Neo4j driver not available — skipping execution log")
            return
        with driver.session() as session:
            session.run(
                "CREATE (e:ExecutionLog {source: $source, status: $status, timestamp: datetime(), details: $details})",
                source=source, status=status, details=json.dumps(details, ensure_ascii=False)
            )
    except Exception as e:
        logger.error(f"Failed to log execution: {e}")



_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from ..services.memory_pipeline import MemoryPipeline
        _pipeline = MemoryPipeline()
    return _pipeline


def _get_rbac():
    from ..security.memory_rbac import get_rbac
    return get_rbac()


def require_api_key(f):
    """Decorator: validate API key in Authorization header or query param."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = (
            request.headers.get('X-API-Key')
            or request.headers.get('Authorization', '').replace('Bearer ', '')
            or request.args.get('api_key')
        )
        if not api_key:
            return jsonify({"error": "API key required (X-API-Key header or api_key param)"}), 401

        rbac = _get_rbac()
        principal = rbac.validate_api_key(api_key)
        if not principal:
            return jsonify({"error": "Invalid API key"}), 403

        # Attach principal to request context
        request._gateway_principal = principal
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────
# n8n Webhook Gateway
# ──────────────────────────────────────────

@ingest_bp.route('/gateway/webhook', methods=['POST'])
@ingest_bp.route('/gateway/n8n', methods=['POST'])
def n8n_webhook():
    """
    n8n Webhook endpoint — accepts data from n8n workflows.

    Body: {
      "api_key": "...",
      "content": "Text or structured data",
      "source": "n8n:workflow-name",
      "graph_id": "default",
      "scope": "tribal",
      "metadata": { "workflow_id": "...", "execution_id": "..." }
    }
    """
    data = request.get_json(force=True)

    # Auth check (inline for webhook flexibility)
    api_key = data.get('api_key') or request.headers.get('X-API-Key', '')
    if api_key:
        rbac = _get_rbac()
        principal = rbac.validate_api_key(api_key)
        if not principal:
            return jsonify({"error": "Invalid API key"}), 403
    # Allow unauthenticated if RBAC is not enforced (dev mode)

    content = data.get('content', '')
    if not content:
        return jsonify({"error": "content is required"}), 400

    pipeline = _get_pipeline()
    result = pipeline.process_ingestion_result(
        graph_id=data.get('graph_id', 'default'),
        source_ref=data.get('source', 'n8n:webhook'),
        text=content if isinstance(content, str) else str(content),
        entities=data.get('entities', []),
        metadata=data.get('metadata', {}),
        auto_promote=data.get('auto_promote', True),
    )

    logger.info(f"n8n webhook processed: {result.get('stm_created', 0)} STM, {result.get('auto_promoted', 0)} promoted")
    
    # + Execute execution logging
    log_execution("n8n", "success", {
        "workflow_id": data.get("metadata", {}).get("workflow_id"),
        "execution_id": data.get("metadata", {}).get("execution_id"),
        "source": data.get("source", "n8n:webhook"),
        "stm_created": result.get("stm_created", 0),
        "auto_promoted": result.get("auto_promoted", 0)
    })
    
    return jsonify({"gateway": "n8n", **result})


# ──────────────────────────────────────────
# Apache NiFi Gateway
# ──────────────────────────────────────────

@ingest_bp.route('/gateway/nifi', methods=['POST'])
def nifi_gateway():
    """
    Apache NiFi endpoint — accepts FlowFile content.

    Headers:
      X-NiFi-FlowFile-UUID: ...
      X-NiFi-Source: processor name

    Body: raw text or JSON
    """
    api_key = request.headers.get('X-API-Key', '')
    if api_key:
        rbac = _get_rbac()
        if not rbac.validate_api_key(api_key):
            return jsonify({"error": "Invalid API key"}), 403

    # Extract NiFi metadata from headers
    nifi_uuid = request.headers.get('X-NiFi-FlowFile-UUID', '')
    nifi_source = request.headers.get('X-NiFi-Source', 'nifi')

    data = request.get_json(silent=True)
    if data:
        content = data.get('content', str(data))
    else:
        content = request.get_data(as_text=True)

    if not content:
        return jsonify({"error": "No content received"}), 400

    pipeline = _get_pipeline()
    result = pipeline.process_ingestion_result(
        graph_id=request.args.get('graph_id', 'default'),
        source_ref=f'nifi:{nifi_source}',
        text=content,
        metadata={
            'nifi_uuid': nifi_uuid,
            'nifi_source': nifi_source,
            'content_type': request.content_type,
        },
        auto_promote=True,
    )

    return jsonify({"gateway": "nifi", **result})


# ──────────────────────────────────────────
# Spark Gateway
# ──────────────────────────────────────────

@ingest_bp.route('/gateway/spark', methods=['POST'])
def spark_gateway():
    """
    Spark Job output endpoint — accepts batch results.

    Body: {
      "api_key": "...",
      "job_id": "spark-job-123",
      "records": [
        {"content": "...", "entity_type": "...", "salience": 0.8},
        ...
      ],
      "graph_id": "analytics",
      "scope": "social"
    }
    """
    data = request.get_json(force=True)

    api_key = data.get('api_key') or request.headers.get('X-API-Key', '')
    if api_key:
        rbac = _get_rbac()
        if not rbac.validate_api_key(api_key):
            return jsonify({"error": "Invalid API key"}), 403

    records = data.get('records', [])
    if not records:
        return jsonify({"error": "records array is required"}), 400

    graph_id = data.get('graph_id', 'default')
    scope = data.get('scope', 'social')
    job_id = data.get('job_id', 'spark-unknown')

    pipeline = _get_pipeline()
    total_result = {
        "gateway": "spark",
        "job_id": job_id,
        "total_records": len(records),
        "stm_created": 0,
        "auto_promoted": 0,
        "discarded": 0,
    }

    # Process each record
    for rec in records[:500]:  # cap at 500
        content = rec.get('content', '')
        if not content:
            continue

        result = pipeline.process_ingestion_result(
            graph_id=graph_id,
            source_ref=f'spark:{job_id}',
            text=content,
            entities=rec.get('entities', []),
            metadata={'scope': scope, 'spark_job': job_id},
            auto_promote=True,
        )
        for key in ['stm_created', 'auto_promoted', 'discarded']:
            total_result[key] += result.get(key, 0)

    logger.info(f"Spark gateway: {job_id} → {total_result['total_records']} records processed")
    return jsonify(total_result)


# ──────────────────────────────────────────
# Generic API Gateway
# ──────────────────────────────────────────

@ingest_bp.route('/gateway/ingest', methods=['POST'])
@require_api_key
def generic_ingest():
    """
    Generic authenticated ingest endpoint.

    Body: {
      "content": "...",
      "source": "external-api",
      "graph_id": "default",
      "scope": "personal",
      "entities": [...],
      "auto_promote": true
    }
    """
    data = request.get_json(force=True)
    content = data.get('content', '')

    if not content:
        return jsonify({"error": "content is required"}), 400

    pipeline = _get_pipeline()
    result = pipeline.process_ingestion_result(
        graph_id=data.get('graph_id', 'default'),
        source_ref=data.get('source', 'api:external'),
        text=content,
        entities=data.get('entities', []),
        metadata=data.get('metadata', {}),
        auto_promote=data.get('auto_promote', True),
    )

    return jsonify({"gateway": "api", "principal": request._gateway_principal.get('name', ''), **result})


# ──────────────────────────────────────────
# Batch Gateway
# ──────────────────────────────────────────

@ingest_bp.route('/gateway/batch', methods=['POST'])
@require_api_key
def batch_ingest():
    """
    Batch ingest multiple items in one call.

    Body: {
      "items": [
        {"content": "...", "source": "...", "scope": "personal"},
        ...
      ],
      "graph_id": "default"
    }
    """
    data = request.get_json(force=True)
    items = data.get('items', [])
    graph_id = data.get('graph_id', 'default')

    if not items:
        return jsonify({"error": "items array is required"}), 400

    pipeline = _get_pipeline()
    totals = {"gateway": "batch", "total": len(items), "stm_created": 0,
              "auto_promoted": 0, "discarded": 0, "errors": 0}

    for item in items[:200]:  # cap
        try:
            result = pipeline.process_ingestion_result(
                graph_id=graph_id,
                source_ref=item.get('source', 'batch'),
                text=item.get('content', ''),
                metadata={'scope': item.get('scope', 'personal')},
                auto_promote=item.get('auto_promote', True),
            )
            for k in ['stm_created', 'auto_promoted', 'discarded']:
                totals[k] += result.get(k, 0)
        except Exception:
            totals["errors"] += 1

    return jsonify(totals)


# ──────────────────────────────────────────
# Gateway Status
# ──────────────────────────────────────────

@ingest_bp.route('/gateway/status', methods=['GET'])
def gateway_status():
    """Get gateway health and supported endpoints."""
    return jsonify({
        "status": "active",
        "endpoints": [
            {"path": "/api/gateway/webhook", "method": "POST", "auth": "optional", "description": "n8n webhook"},
            {"path": "/api/gateway/n8n", "method": "POST", "auth": "optional", "description": "n8n alias"},
            {"path": "/api/gateway/nifi", "method": "POST", "auth": "optional", "description": "Apache NiFi"},
            {"path": "/api/gateway/spark", "method": "POST", "auth": "optional", "description": "Spark batch"},
            {"path": "/api/gateway/ingest", "method": "POST", "auth": "api_key", "description": "Generic API"},
            {"path": "/api/gateway/batch", "method": "POST", "auth": "api_key", "description": "Batch ingest"},
        ],
    })
