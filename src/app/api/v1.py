from flask import Blueprint, jsonify

# Define an API v1 Blueprint
api_v1_bp = Blueprint('api_v1', __name__)

@api_v1_bp.route('/info', methods=['GET'])
def get_v1_info():
    """Returns information about the API v1."""
    return jsonify({
        "version": "1.0",
        "status": "active",
        "description": "Mories API v1 endpoint."
    }), 200
