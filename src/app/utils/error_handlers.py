"""
Global Error Handlers for Mories API
"""

import logging
from flask import jsonify
from werkzeug.exceptions import HTTPException

from .errors import MoriesAPIError

logger = logging.getLogger(__name__)

def register_error_handlers(app):
    """Registers standard JSON error handlers to the Flask app."""

    @app.errorhandler(MoriesAPIError)
    def handle_mories_api_error(error):
        """Handle custom application errors."""
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        """Handle default Werkzeug HTTP exceptions (e.g. 404, 405)."""
        response = jsonify({
            "error": {
                "code": f"HTTP_{error.code}",
                "message": error.description,
                "details": {}
            }
        })
        response.status_code = error.code
        return response

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Catch-all for unhandled exceptions (500)."""
        logger.exception("Unhandled Exception: %s", error)
        response = jsonify({
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected system error occurred.",
                "details": {"type": str(type(error).__name__)}
            }
        })
        response.status_code = 500
        return response
