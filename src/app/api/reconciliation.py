"""
Reconciliation API — Data Consistency Endpoints

Provides REST endpoints for:
  - Running reconciliation checks
  - Quick health checks
  - Viewing reconciliation history
"""

from flask import Blueprint, request, jsonify
from ..utils.logger import get_logger

reconciliation_bp = Blueprint('reconciliation', __name__, url_prefix='/api/reconciliation')

logger = get_logger('mirofish.api.reconciliation')


def _get_service():
    """Lazy-load ReconciliationService."""
    from ..storage.reconciliation_service import ReconciliationService
    return ReconciliationService()


@reconciliation_bp.route('/run', methods=['POST'])
def run_reconciliation():
    """
    POST /api/reconciliation/run
    Run full reconciliation check.

    Body (JSON):
        auto_fix (bool): Auto-fix INFO-level issues (default: false)

    Returns:
        ReconciliationResult with all issues and health score
    """
    data = request.get_json(silent=True) or {}
    auto_fix = data.get('auto_fix', False)

    svc = _get_service()
    try:
        result = svc.run(auto_fix=auto_fix)
        return jsonify(result.to_dict())
    except Exception as e:
        logger.error(f"Reconciliation run failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        svc.close()


@reconciliation_bp.route('/check', methods=['GET'])
def quick_check():
    """
    GET /api/reconciliation/check
    Lightweight health check (no auto-fix).
    """
    svc = _get_service()
    try:
        result = svc.quick_check()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Quick check failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        svc.close()


@reconciliation_bp.route('/history', methods=['GET'])
def reconciliation_history():
    """
    GET /api/reconciliation/history
    Get history of reconciliation runs.

    Query params:
        limit (int): Max results (default: 10)
    """
    limit = request.args.get('limit', 10, type=int)

    svc = _get_service()
    try:
        history = svc.get_run_history(limit=limit)
        return jsonify({"history": history, "count": len(history)})
    except Exception as e:
        logger.error(f"History query failed: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        svc.close()
