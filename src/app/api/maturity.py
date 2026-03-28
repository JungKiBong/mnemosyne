"""
Maturity API — Knowledge Lifecycle Management

Endpoints:
  GET  /api/maturity/overview           — 종합 현황 (대시보드용)
  GET  /api/maturity/list/<level>       — 특정 성숙도 기억 목록
  POST /api/maturity/set                — 성숙도 수동 설정
  GET  /api/maturity/<uuid>             — 특정 기억 성숙도 조회
  POST /api/maturity/check-promotions   — 자동 승격 실행
  GET  /api/maturity/rules              — 접근 규칙 매트릭스
"""

import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger('mirofish.api.maturity')

maturity_bp = Blueprint('maturity', __name__, url_prefix='/api/maturity')


def _get_manager():
    from ..security.memory_maturity import get_maturity_manager
    return get_maturity_manager()


@maturity_bp.route('/overview', methods=['GET'])
def overview():
    """종합 현황 — 대시보드용."""
    mgr = _get_manager()
    return jsonify(mgr.get_overview())


@maturity_bp.route('/list/<level>', methods=['GET'])
def list_by_maturity(level):
    """특정 성숙도 레벨의 기억 목록."""
    mgr = _get_manager()
    scope = request.args.get('scope')
    limit = int(request.args.get('limit', 50))
    memories = mgr.get_memories_by_maturity(level, scope, limit)
    return jsonify({"maturity": level, "count": len(memories), "memories": memories})


@maturity_bp.route('/set', methods=['POST'])
def set_maturity():
    """기억 성숙도 수동 설정."""
    data = request.get_json(force=True)
    mgr = _get_manager()
    result = mgr.set_maturity(
        uuid=data.get('uuid', ''),
        level=data.get('level', 'learning'),
        changed_by=data.get('changed_by', 'admin'),
        reason=data.get('reason', ''),
    )
    return jsonify(result)


@maturity_bp.route('/<uuid>', methods=['GET'])
def get_maturity(uuid):
    """특정 기억의 성숙도 조회."""
    mgr = _get_manager()
    return jsonify(mgr.get_maturity(uuid))


@maturity_bp.route('/check-promotions', methods=['POST'])
def check_promotions():
    """자동 승격 실행."""
    mgr = _get_manager()
    result = mgr.check_promotions()
    return jsonify(result)


@maturity_bp.route('/rules', methods=['GET'])
def access_rules():
    """성숙도별 접근 규칙 매트릭스."""
    from ..security.memory_maturity import MATURITY_ACCESS, MaturityLevel
    rules = {}
    for level, access in MATURITY_ACCESS.items():
        rules[level.value] = {
            **access,
            "emoji": {"learning": "🌱", "unstable": "⚡", "mature": "✅", "secret": "🔒"}[level.value],
        }
    return jsonify({"rules": rules})
