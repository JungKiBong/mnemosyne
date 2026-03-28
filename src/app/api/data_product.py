"""
Data Product API — Phase 11: AI-Ready Memory Export

REST endpoints for exporting memories as AI-consumable data products.
"""

import logging
from flask import Blueprint, jsonify, request, Response

logger = logging.getLogger('mirofish.api.data_product')

data_product_bp = Blueprint('data_product', __name__, url_prefix='/api/memory/data')


def _get_dp():
    from ..storage.data_product import MemoryDataProduct
    return MemoryDataProduct()


# ── RAG Corpus ──

@data_product_bp.route('/rag', methods=['GET'])
def export_rag():
    """
    Export RAG-ready corpus.
    Query: scope, min_salience, format(json|jsonl), include_relations(true|false)
    """
    scope = request.args.get('scope', None)
    min_sal = request.args.get('min_salience', 0.3, type=float)
    fmt = request.args.get('format', 'jsonl')
    include_rels = request.args.get('include_relations', 'true') == 'true'

    dp = _get_dp()
    try:
        result = dp.export_rag_corpus(scope, min_sal, include_rels, fmt)
        return jsonify(result)
    finally:
        dp.close()


@data_product_bp.route('/rag/download', methods=['GET'])
def download_rag():
    """Download RAG corpus as a file."""
    scope = request.args.get('scope', None)
    min_sal = request.args.get('min_salience', 0.3, type=float)

    dp = _get_dp()
    try:
        result = dp.export_rag_corpus(scope, min_sal, True, 'jsonl')
        return Response(
            result["content"],
            mimetype='application/x-jsonlines',
            headers={"Content-Disposition": "attachment; filename=mnemosyne_rag_corpus.jsonl"},
        )
    finally:
        dp.close()


# ── Knowledge Snapshot ──

@data_product_bp.route('/snapshot', methods=['GET'])
def export_snapshot():
    """Export full knowledge graph snapshot."""
    scope = request.args.get('scope', None)
    min_sal = request.args.get('min_salience', 0.0, type=float)

    dp = _get_dp()
    try:
        result = dp.export_knowledge_snapshot(scope, min_sal)
        return jsonify(result)
    finally:
        dp.close()


# ── Training Dataset ──

@data_product_bp.route('/training', methods=['GET'])
def export_training():
    """
    Export Q&A training pairs.
    Query: format(json|jsonl), min_salience
    """
    fmt = request.args.get('format', 'jsonl')
    min_sal = request.args.get('min_salience', 0.5, type=float)

    dp = _get_dp()
    try:
        result = dp.export_training_dataset(fmt, min_sal)
        return jsonify(result)
    finally:
        dp.close()


@data_product_bp.route('/training/download', methods=['GET'])
def download_training():
    """Download training dataset as file."""
    min_sal = request.args.get('min_salience', 0.5, type=float)

    dp = _get_dp()
    try:
        result = dp.export_training_dataset('jsonl', min_sal)
        return Response(
            result["content"],
            mimetype='application/x-jsonlines',
            headers={"Content-Disposition": "attachment; filename=mnemosyne_training.jsonl"},
        )
    finally:
        dp.close()


# ── Memory Manifest ──

@data_product_bp.route('/manifest', methods=['POST'])
def create_manifest():
    """
    Create a versioned Memory Manifest package.
    Body: {"name": "...", "description": "...", "scope": "tribal", "include_audit": true}
    """
    data = request.get_json(force=True)
    name = data.get('name')
    if not name:
        return jsonify({"error": "name is required"}), 400

    dp = _get_dp()
    try:
        manifest = dp.create_manifest(
            name=name,
            description=data.get('description', ''),
            scope=data.get('scope', None),
            include_audit=data.get('include_audit', True),
        )
        return jsonify(manifest)
    finally:
        dp.close()


@data_product_bp.route('/manifest/list', methods=['GET'])
def list_manifests():
    """List all created manifests."""
    dp = _get_dp()
    try:
        return jsonify(dp.list_manifests())
    finally:
        dp.close()


# ── Analytics CSV ──

@data_product_bp.route('/analytics/csv', methods=['GET'])
def export_csv():
    """Export analytics as CSV file."""
    dp = _get_dp()
    try:
        csv_content = dp.export_analytics_csv()
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={"Content-Disposition": "attachment; filename=mnemosyne_analytics.csv"},
        )
    finally:
        dp.close()


# ── Summary ──

@data_product_bp.route('/catalog', methods=['GET'])
def catalog():
    """List all available data products and their descriptions."""
    return jsonify({
        "products": [
            {
                "id": "rag_corpus",
                "name": "RAG Corpus",
                "description": "Embedding-ready documents for Retrieval-Augmented Generation",
                "endpoint": "/api/memory/data/rag",
                "formats": ["json", "jsonl"],
                "download": "/api/memory/data/rag/download",
            },
            {
                "id": "knowledge_snapshot",
                "name": "Knowledge Graph Snapshot",
                "description": "Full graph export (nodes, edges, agents) for visualization or import",
                "endpoint": "/api/memory/data/snapshot",
                "formats": ["json"],
            },
            {
                "id": "training_dataset",
                "name": "Training Dataset",
                "description": "Q&A pairs for LLM fine-tuning from knowledge relationships",
                "endpoint": "/api/memory/data/training",
                "formats": ["json", "jsonl"],
                "download": "/api/memory/data/training/download",
            },
            {
                "id": "memory_manifest",
                "name": "Memory Manifest",
                "description": "Versioned, shareable knowledge package with lineage metadata",
                "endpoint": "/api/memory/data/manifest",
                "method": "POST",
            },
            {
                "id": "analytics_csv",
                "name": "Analytics Export",
                "description": "Memory analytics as CSV for dashboards and spreadsheets",
                "endpoint": "/api/memory/data/analytics/csv",
                "formats": ["csv"],
            },
        ],
        "version": "1.0.0",
    })
