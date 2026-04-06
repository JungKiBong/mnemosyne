from flask import Blueprint, jsonify, request
import os
import logging
from app.utils.auth import require_auth
from app.utils.limiter import limiter

logger = logging.getLogger(__name__)

# Define an API v1 Blueprint
api_v1_bp = Blueprint('api_v1', __name__)

@api_v1_bp.route('/info', methods=['GET'])
@limiter.exempt
def get_v1_info():
    """Returns information about the API v1."""
    return jsonify({
        "version": "1.0",
        "status": "active",
        "description": "Mories API v1 endpoint."
    }), 200

@api_v1_bp.route('/search', methods=['POST'])
@require_auth()
@limiter.limit("50 per minute")
def search_api():
    """Direct REST search endpoint (secured)."""
    import sys
    mcp_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    if mcp_path not in sys.path:
        sys.path.insert(0, mcp_path)

    from mcp_server.tools import mories_search
    data = request.get_json(silent=True) or {}
    query = data.get('query', '')
    graph_id = data.get('graph_id', '')
    limit = data.get('limit', 10)

    from ..utils.errors import ValidationError
    if not query:
        raise ValidationError("query parameter is required")

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

@api_v1_bp.route('/query', methods=['POST'])
@require_auth()
@limiter.limit("20 per minute")
def query_api():
    """Direct REST Cypher query endpoint (read-only, secured)."""
    import sys
    mcp_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    if mcp_path not in sys.path:
        sys.path.insert(0, mcp_path)

    from mcp_server.tools import mories_graph_query
    data = request.get_json(silent=True) or {}
    cypher = data.get('cypher', '')
    params = data.get('params', {})
    limit = data.get('limit', 50)

    from ..utils.errors import ValidationError
    if not cypher:
        raise ValidationError("cypher parameter is required")

    result = mories_graph_query(cypher=cypher, params=params, limit=limit)
    return jsonify(result)
