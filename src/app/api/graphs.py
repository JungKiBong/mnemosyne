import logging
from flask import Blueprint, jsonify, request, current_app
from neo4j import GraphDatabase

logger = logging.getLogger('mirofish.api.graphs')
graphs_bp = Blueprint('graphs', __name__, url_prefix='/api/graphs')

def get_driver():
    return GraphDatabase.driver(
        current_app.config.get('NEO4J_URI'),
        auth=(current_app.config.get('NEO4J_USER'), current_app.config.get('NEO4J_PASSWORD'))
    )

@graphs_bp.route('', methods=['GET'])
def list_graphs():
    """List all unique graph_ids (Projects) and their public/private status."""
    try:
        driver = get_driver()
        with driver.session() as session:
            # Extract distinct graph_ids
            res = session.run("MATCH (n) WHERE n.graph_id IS NOT NULL RETURN DISTINCT n.graph_id AS graph_id")
            graph_ids = [r['graph_id'] for r in res]
            
            # Count elements per graph_id
            counts_res = session.run("MATCH (n) WHERE n.graph_id IS NOT NULL RETURN n.graph_id AS graph_id, count(n) AS count")
            counts = {r['graph_id']: r['count'] for r in counts_res}

            # Fetch visibility status from GraphMeta
            meta_res = session.run("MATCH (g:GraphMeta) RETURN g.graph_id AS graph_id, g.is_public AS is_public")
            meta = {r['graph_id']: r['is_public'] for r in meta_res}
            
            result = []
            for gid in graph_ids:
                if not gid: continue
                result.append({
                    "graph_id": gid,
                    "count": counts.get(gid, 0),
                    "is_public": meta.get(gid, False) # Default is private
                })
        driver.close()
        return jsonify({"graphs": result})
    except Exception as e:
        logger.error(f"Error listing graphs: {e}")
        return jsonify({"error": str(e)}), 500

@graphs_bp.route('/<graph_id>/visibility', methods=['POST'])
def set_visibility(graph_id):
    """Set public/private visibility securely for a specific graph_id."""
    data = request.json or {}
    is_public = data.get('is_public', False)
    
    try:
        driver = get_driver()
        with driver.session() as session:
            session.run('''
                MERGE (g:GraphMeta {graph_id: $graph_id})
                ON CREATE SET g.created_at = timestamp()
                SET g.is_public = $is_public
            ''', graph_id=graph_id, is_public=is_public)
        driver.close()
        return jsonify({"graph_id": graph_id, "is_public": is_public})
    except Exception as e:
        logger.error(f"Error setting visibility: {e}")
        return jsonify({"error": str(e)}), 500
