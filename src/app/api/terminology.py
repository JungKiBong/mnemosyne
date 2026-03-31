"""
Terminology Management API Routes
Handles terminology normalization mappings across personal/tribal/global scopes.
"""

from flask import Blueprint, request, jsonify, current_app, g
from typing import Dict, Any

from ..utils.logger import get_logger
from . import terminology_bp

logger = get_logger('mirofish.api.terminology')



def _get_service():
    """Get TerminologyService instance, cached per-request via Flask g."""
    if 'terminology_service' not in g:
        driver = current_app.extensions.get('neo4j_driver')
        if not driver:
            raise ValueError("Neo4j driver not initialized — check Neo4j connection")
        from ..storage.terminology_service import TerminologyService
        g.terminology_service = TerminologyService(driver=driver)
    return g.terminology_service


@terminology_bp.route('/', methods=['GET'])
def list_mappings():
    """List term mappings accessible to the principal."""
    principal_id = request.headers.get("X-User-ID", "anonymous")
    scope_filter = request.args.get("scope")
    
    try:
        service = _get_service()
        mappings = service.list_mappings(principal_id, scope_filter)
        return jsonify({"success": True, "data": mappings})
    except Exception as e:
        logger.error(f"Error listing mappings: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@terminology_bp.route('/', methods=['POST'])
def create_mapping():
    """Create or update a term mapping."""
    principal_id = request.headers.get("X-User-ID", "anonymous")
    data = request.get_json() or {}
    
    scope = data.get("scope")
    source_term = data.get("source_term")
    standard_term = data.get("standard_term")
    entity_type = data.get("entity_type")
    description = data.get("description")
    team_id = data.get("team_id")

    if not all([scope, source_term, standard_term]):
        return jsonify({"success": False, "error": "Missing required fields: scope, source_term, standard_term"}), 400

    try:
        service = _get_service()
        result = service.create_or_update_mapping(
            principal_id=principal_id,
            scope=scope,
            source_term=source_term,
            standard_term=standard_term,
            entity_type=entity_type,
            description=description,
            team_id=team_id
        )
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]}), 400
            
        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"Error creating mapping: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@terminology_bp.route('/<mapping_uuid>', methods=['DELETE'])
def delete_mapping(mapping_uuid: str):
    """Soft-delete a term mapping."""
    principal_id = request.headers.get("X-User-ID", "anonymous")
    
    try:
        service = _get_service()
        result = service.delete_mapping(principal_id, mapping_uuid)
        
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]}), 400
            
        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"Error deleting mapping: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@terminology_bp.route('/<mapping_uuid>/preview', methods=['GET'])
def preview_migration(mapping_uuid: str):
    """Dry run a migration to see affected entities."""
    principal_id = request.headers.get("X-User-ID", "anonymous")
    
    try:
        service = _get_service()
        result = service.preview_migration(principal_id, mapping_uuid)
        
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]}), 400
            
        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"Error previewing migration: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@terminology_bp.route('/<mapping_uuid>/migrate', methods=['POST'])
def execute_migration(mapping_uuid: str):
    """Execute migration batch to standardize existing terms."""
    principal_id = request.headers.get("X-User-ID", "anonymous")
    
    try:
        service = _get_service()
        result = service.execute_migration(principal_id, mapping_uuid)
        
        if "error" in result:
            return jsonify({"success": False, "error": result["error"]}), 400
            
        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"Error executing migration: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
