"""
Pipeline API — Ingest→STM→LTM auto-flow + Scheduler control

Endpoints:
  POST /api/pipeline/process       — Process raw content through memory pipeline
  POST /api/pipeline/ingest-auto   — Ingest + auto-flow to cognitive memory
  GET  /api/pipeline/scheduler     — Get scheduler status
  POST /api/pipeline/scheduler/decay — Trigger manual decay
"""

import logging
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger('mirofish.api.pipeline')

pipeline_bp = Blueprint('pipeline', __name__, url_prefix='/api/pipeline')

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from ..services.memory_pipeline import MemoryPipeline
        _pipeline = MemoryPipeline()
    return _pipeline


@pipeline_bp.route('/process', methods=['POST'])
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


@pipeline_bp.route('/ingest-auto', methods=['POST'])
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


@pipeline_bp.route('/scheduler', methods=['GET'])
def scheduler_status():
    """Get memory scheduler status."""
    from ..services.memory_scheduler import get_scheduler
    scheduler = get_scheduler()
    return jsonify(scheduler.get_status())


@pipeline_bp.route('/scheduler/decay', methods=['POST'])
def trigger_decay():
    """Manually trigger decay cycle."""
    data = request.get_json(silent=True) or {}
    dry_run = data.get('dry_run', False)

    from ..storage.memory_manager import MemoryManager
    mgr = MemoryManager()
    try:
        result = mgr.run_decay(dry_run=dry_run)
        return jsonify(result)
    finally:
        mgr.close()
