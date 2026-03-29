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

import logging
import hashlib
import hmac
import time
from functools import wraps
from datetime import datetime, timezone
import json
from flask import Blueprint, request, jsonify

logger = logging.getLogger('mirofish.gateway')

def log_execution(source: str, status: str, details: dict):
    """Log external workflow executions (e.g., n8n, NiFi) to Neo4j."""
    try:
        from ..config import Config
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD))
        with driver.session() as session:
            session.run(
                "CREATE (e:ExecutionLog {source: $source, status: $status, timestamp: datetime(), details: $details})",
                source=source, status=status, details=json.dumps(details, ensure_ascii=False)
            )
        driver.close()
    except Exception as e:
        logger.error(f"Failed to log execution: {e}")


gateway_bp = Blueprint('gateway', __name__, url_prefix='/api/gateway')

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

@gateway_bp.route('/webhook', methods=['POST'])
@gateway_bp.route('/n8n', methods=['POST'])
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

@gateway_bp.route('/nifi', methods=['POST'])
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

@gateway_bp.route('/spark', methods=['POST'])
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

@gateway_bp.route('/ingest', methods=['POST'])
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

@gateway_bp.route('/batch', methods=['POST'])
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

@gateway_bp.route('/status', methods=['GET'])
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
