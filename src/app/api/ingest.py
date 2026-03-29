"""
REST API for data ingestion.

POST /api/ingest              — one-shot ingestion from any source (NER pipeline)
POST /api/ingest/batch        — batch ingestion from multiple sources
POST /api/ingest/hybrid       — 2-Phase hybrid pipeline (structural + semantic enrichment)
POST /api/ingest/stream       — start stream ingestion
DELETE /api/ingest/stream     — stop stream ingestion
GET /api/ingest/streams       — list active streams
GET /api/ingest/fingerprints  — list stored fingerprints
DELETE /api/ingest/fingerprint — delete a fingerprint
"""
import os
import logging
from flask import Blueprint, request, jsonify, current_app

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
def ingest():
    """
    One-shot data ingestion (classic NER pipeline).

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


@ingest_bp.route('/hybrid', methods=['POST'])
def ingest_hybrid():
    """
    2-Phase Hybrid Pipeline ingestion (UA-inspired).

    Phase 1: Structural extraction (deterministic, no LLM)
    Phase 2: Semantic enrichment (LLM-based nodes/edges)
    + Fingerprint-based incremental updates

    Request JSON:
    {
        "graph_id": "my_graph",
        "source_ref": "/path/to/file.pdf",
        "incremental": true,
        "enrich": true,
        "also_run_ner": true,
        "options": {}
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

    incremental = data.get('incremental', True)
    enrich = data.get('enrich', True)
    also_run_ner = data.get('also_run_ner', True)
    options = data.get('options', {})

    try:
        result = svc.ingest_with_knowledge_graph(
            graph_id=graph_id,
            source_ref=source_ref,
            incremental=incremental,
            enrich=enrich,
            also_run_ner=also_run_ner,
            **options,
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Hybrid ingestion failed: %s", e, exc_info=True)
        return jsonify({"error": f"Hybrid ingestion failed: {e}"}), 500


@ingest_bp.route('/fingerprints', methods=['GET'])
def list_fingerprints():
    """List all stored content fingerprints for incremental update tracking."""
    try:
        from app.utils.fingerprint import ContentFingerprint
        fp = ContentFingerprint()
        results = fp.list_all()
        fp.close()
        return jsonify({"fingerprints": results, "count": len(results)}), 200
    except Exception as e:
        logger.error("Failed to list fingerprints: %s", e)
        return jsonify({"error": str(e)}), 500


@ingest_bp.route('/fingerprint', methods=['DELETE'])
def delete_fingerprint():
    """
    Delete a stored fingerprint to force full re-processing.
    Query param: source_ref
    """
    source_ref = request.args.get('source_ref')
    if not source_ref:
        return jsonify({"error": "source_ref query param required"}), 400

    try:
        from app.utils.fingerprint import ContentFingerprint
        fp = ContentFingerprint()
        fp.delete(source_ref)
        fp.close()
        return jsonify({"status": "deleted", "source_ref": source_ref}), 200
    except Exception as e:
        logger.error("Failed to delete fingerprint: %s", e)
        return jsonify({"error": str(e)}), 500


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

