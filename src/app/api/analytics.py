import logging
from flask import Blueprint, request, jsonify, current_app

logger = logging.getLogger('mirofish.api.analytics')
analytics_bp = Blueprint('analytics', __name__)


# --- Merged from maturity.py ---
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





def _get_manager():
    from ..security.memory_maturity import get_maturity_manager
    return get_maturity_manager()


@analytics_bp.route('/maturity/overview', methods=['GET'])
def overview():
    """종합 현황 — 대시보드용."""
    mgr = _get_manager()
    return jsonify(mgr.get_overview())


@analytics_bp.route('/maturity/list/<level>', methods=['GET'])
def list_by_maturity(level):
    """특정 성숙도 레벨의 기억 목록."""
    mgr = _get_manager()
    scope = request.args.get('scope')
    limit = int(request.args.get('limit', 50))
    memories = mgr.get_memories_by_maturity(level, scope, limit)
    return jsonify({"maturity": level, "count": len(memories), "memories": memories})


@analytics_bp.route('/maturity/set', methods=['POST'])
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


@analytics_bp.route('/maturity/<uuid>', methods=['GET'])
def get_maturity(uuid):
    """특정 기억의 성숙도 조회."""
    mgr = _get_manager()
    return jsonify(mgr.get_maturity(uuid))


@analytics_bp.route('/maturity/check-promotions', methods=['POST'])
def check_promotions():
    """자동 승격 실행."""
    mgr = _get_manager()
    result = mgr.check_promotions()
    return jsonify(result)


@analytics_bp.route('/maturity/rules', methods=['GET'])
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


# --- Merged from reconciliation.py ---
"""
Reconciliation API — Data Consistency Endpoints

Provides REST endpoints for:
  - Running reconciliation checks
  - Quick health checks
  - Viewing reconciliation history
"""

from ..utils.logger import get_logger


logger = get_logger('mirofish.api.reconciliation')


def _get_service():
    """Lazy-load ReconciliationService."""
    from ..storage.reconciliation_service import ReconciliationService
    return ReconciliationService()


@analytics_bp.route('/reconcile/run', methods=['POST'])
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


@analytics_bp.route('/reconcile/check', methods=['GET'])
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


@analytics_bp.route('/reconcile/history', methods=['GET'])
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


# --- Merged from report.py ---
"""
Report API Routes
Provides interfaces for simulation report generation, retrieval, and conversation
"""

import os
import traceback
import threading
from flask import request, jsonify, send_file, current_app


from ..config import Config
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..services.graph_tools import GraphToolsService
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.report')


# ============== Report Generation Interface ==============

@analytics_bp.route('/report/generate', methods=['POST'])
def generate_report():
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        force_regenerate = data.get('force_regenerate', False)
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return jsonify({"success": False, "error": f"Simulation does not exist: {simulation_id}"}), 404

        if not force_regenerate:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({"success": True, "data": {
                    "simulation_id": simulation_id,
                    "report_id": existing_report.report_id,
                    "status": "completed",
                    "message": "Report already exists",
                    "already_generated": True
                }})

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({"success": False, "error": f"Project does not exist: {state.project_id}"}), 404

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({"success": False, "error": "Missing graph ID, please ensure graph is built"}), 400

        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            return jsonify({"success": False, "error": "Missing simulation requirement description"}), 400

        import uuid
        report_id = f"report_{uuid.uuid4().hex[:12]}"

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="report_generate",
            metadata={"simulation_id": simulation_id, "graph_id": graph_id, "report_id": report_id}
        )

        # Initialize graph_tools in Flask context BEFORE spawning thread
        # (current_app is not available inside background threads)
        storage = current_app.extensions.get('neo4j_storage')
        if not storage:
            return jsonify({"success": False, "error": "GraphStorage not initialized — check Neo4j connection"}), 500
        graph_tools = GraphToolsService(storage=storage)

        def run_generate():
            try:
                task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=0, message="Initializing Report Agent...")
                agent = ReportAgent(
                    graph_id=graph_id,
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    graph_tools=graph_tools
                )
                def progress_callback(stage, progress, message):
                    task_manager.update_task(task_id, progress=progress, message=f"[{stage}] {message}")
                report = agent.generate_report(progress_callback=progress_callback, report_id=report_id)
                ReportManager.save_report(report)
                if report.status == ReportStatus.COMPLETED:
                    task_manager.complete_task(task_id, result={"report_id": report.report_id, "simulation_id": simulation_id, "status": "completed"})
                else:
                    task_manager.fail_task(task_id, report.error or "Report generation failed")
            except Exception as e:
                logger.error(f"Report generation failed: {str(e)}")
                task_manager.fail_task(task_id, str(e))

        thread = threading.Thread(target=run_generate, daemon=True)
        thread.start()

        return jsonify({"success": True, "data": {
            "simulation_id": simulation_id,
            "report_id": report_id,
            "task_id": task_id,
            "status": "generating",
            "message": "Report generation task started. Query progress via /api/report/generate/status",
            "already_generated": False
        }})

    except Exception as e:
        logger.error(f"Failed to start report generation task: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/generate/status', methods=['POST'])
def get_generate_status():
    try:
        data = request.get_json() or {}
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')

        if simulation_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({"success": True, "data": {
                    "simulation_id": simulation_id,
                    "report_id": existing_report.report_id,
                    "status": "completed",
                    "progress": 100,
                    "message": "Report generated",
                    "already_completed": True
                }})

        if not task_id:
            return jsonify({"success": False, "error": "Please provide task_id or simulation_id"}), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": f"Task does not exist: {task_id}"}), 404

        return jsonify({"success": True, "data": task.to_dict()})

    except Exception as e:
        logger.error(f"Failed to query task status: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============== Report Retrieval Interface ==============

@analytics_bp.route('/report/<report_id>', methods=['GET'])
def get_report(report_id: str):
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({"success": False, "error": f"Report does not exist: {report_id}"}), 404
        return jsonify({"success": True, "data": report.to_dict()})
    except Exception as e:
        logger.error(f"Failed to get report: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/by-simulation/<simulation_id>', methods=['GET'])
def get_report_by_simulation(simulation_id: str):
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        if not report:
            return jsonify({"success": False, "error": f"No report available for this simulation: {simulation_id}", "has_report": False}), 404
        return jsonify({"success": True, "data": report.to_dict()})
    except Exception as e:
        logger.error(f"Failed to get report: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/list', methods=['GET'])
def list_reports():
    try:
        simulation_id = request.args.get('simulation_id')
        limit = request.args.get('limit', 50, type=int)
        reports = ReportManager.list_reports(simulation_id=simulation_id, limit=limit)
        return jsonify({"success": True, "data": [r.to_dict() for r in reports], "count": len(reports)})
    except Exception as e:
        logger.error(f"Failed to list reports: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/<report_id>/download', methods=['GET'])
def download_report(report_id: str):
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({"success": False, "error": f"Report does not exist: {report_id}"}), 404

        md_path = ReportManager._get_report_markdown_path(report_id)
        if not os.path.exists(md_path):
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(report.markdown_content)
                temp_path = f.name
            return send_file(temp_path, as_attachment=True, download_name=f"{report_id}.md")

        return send_file(md_path, as_attachment=True, download_name=f"{report_id}.md")

    except Exception as e:
        logger.error(f"Failed to download report: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/<report_id>', methods=['DELETE'])
def delete_report(report_id: str):
    try:
        success = ReportManager.delete_report(report_id)
        if not success:
            return jsonify({"success": False, "error": f"Report does not exist: {report_id}"}), 404
        return jsonify({"success": True, "message": f"Report deleted: {report_id}"})
    except Exception as e:
        logger.error(f"Failed to delete report: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Report Agent Chat Interface ==============

@analytics_bp.route('/report/chat', methods=['POST'])
def chat_with_report_agent():
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        message = data.get('message')
        chat_history = data.get('chat_history', [])

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400
        if not message:
            return jsonify({"success": False, "error": "Please provide message"}), 400

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return jsonify({"success": False, "error": f"Simulation does not exist: {simulation_id}"}), 404

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({"success": False, "error": f"Project does not exist: {state.project_id}"}), 404

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({"success": False, "error": "Missing graph ID"}), 400

        simulation_requirement = project.simulation_requirement or ""

        storage = current_app.extensions.get('neo4j_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized — check Neo4j connection")
        graph_tools = GraphToolsService(storage=storage)

        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement,
            graph_tools=graph_tools
        )

        result = agent.chat(message=message, chat_history=chat_history)
        return jsonify({"success": True, "data": {"response": result, "simulation_id": simulation_id}})

    except Exception as e:
        logger.error(f"Chat failed: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Report Progress and Section Retrieval Interface ==============

@analytics_bp.route('/report/<report_id>/progress', methods=['GET'])
def get_report_progress(report_id: str):
    try:
        progress = ReportManager.get_progress(report_id)
        if not progress:
            return jsonify({"success": False, "error": f"Report does not exist or progress info unavailable: {report_id}"}), 404
        return jsonify({"success": True, "data": progress})
    except Exception as e:
        logger.error(f"Failed to get report progress: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/<report_id>/sections', methods=['GET'])
def get_report_sections(report_id: str):
    try:
        sections = ReportManager.get_generated_sections(report_id)
        report = ReportManager.get_report(report_id)
        is_complete = report is not None and report.status == ReportStatus.COMPLETED
        return jsonify({"success": True, "data": {
            "report_id": report_id,
            "sections": sections,
            "total": len(sections),
            "is_complete": is_complete
        }})
    except Exception as e:
        logger.error(f"Failed to get section list: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/<report_id>/section/<int:section_index>', methods=['GET'])
def get_single_section(report_id: str, section_index: int):
    try:
        section_path = ReportManager._get_section_path(report_id, section_index)
        if not os.path.exists(section_path):
            return jsonify({"success": False, "error": f"Section does not exist: section_{section_index:02d}.md"}), 404
        with open(section_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"success": True, "data": {"filename": f"section_{section_index:02d}.md", "content": content}})
    except Exception as e:
        logger.error(f"Failed to get section content: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Report Status Check Interface ==============

@analytics_bp.route('/report/check/<simulation_id>', methods=['GET'])
def check_report_status(simulation_id: str):
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        has_report = report is not None
        report_status = report.status.value if report and hasattr(report.status, 'value') else (report.status if report else None)
        report_id = report.report_id if report else None
        interview_unlocked = has_report and report.status == ReportStatus.COMPLETED
        return jsonify({"success": True, "data": {
            "simulation_id": simulation_id,
            "has_report": has_report,
            "report_id": report_id,
            "report_status": report_status,
            "interview_unlocked": interview_unlocked
        }})
    except Exception as e:
        logger.error(f"Failed to check report status: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Agent Log Interface ==============

@analytics_bp.route('/report/<report_id>/agent-log', methods=['GET'])
def get_agent_log(report_id: str):
    try:
        from_line = request.args.get('from_line', 0, type=int)
        log_data = ReportManager.get_agent_log(report_id, from_line=from_line)
        return jsonify({"success": True, "data": log_data})
    except Exception as e:
        logger.error(f"Failed to get agent log: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/<report_id>/agent-log/stream', methods=['GET'])
def stream_agent_log(report_id: str):
    try:
        logs = ReportManager.get_agent_log_stream(report_id)
        return jsonify({"success": True, "data": {"logs": logs, "count": len(logs)}})
    except Exception as e:
        logger.error(f"Failed to get agent log: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Console Log Interface ==============

@analytics_bp.route('/report/<report_id>/console-log', methods=['GET'])
def get_console_log(report_id: str):
    try:
        from_line = request.args.get('from_line', 0, type=int)
        log_data = ReportManager.get_console_log(report_id, from_line=from_line)
        return jsonify({"success": True, "data": log_data})
    except Exception as e:
        logger.error(f"Failed to get console log: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/<report_id>/console-log/stream', methods=['GET'])
def stream_console_log(report_id: str):
    try:
        logs = ReportManager.get_console_log_stream(report_id)
        return jsonify({"success": True, "data": {"logs": logs, "count": len(logs)}})
    except Exception as e:
        logger.error(f"Failed to get console log: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Tool Call Interface (For Debugging) ==============

@analytics_bp.route('/report/tools/search', methods=['POST'])
def search_graph_tool():
    try:
        data = request.get_json() or {}
        graph_id = data.get('graph_id')
        query = data.get('query')
        limit = data.get('limit', 10)
        if not graph_id or not query:
            return jsonify({"success": False, "error": "Please provide graph_id and query"}), 400
        storage = current_app.extensions.get('neo4j_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized — check Neo4j connection")
        tools = GraphToolsService(storage=storage)
        result = tools.search_graph(graph_id=graph_id, query=query, limit=limit)
        return jsonify({"success": True, "data": result.to_dict()})
    except Exception as e:
        logger.error(f"Graph search failed: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@analytics_bp.route('/report/tools/statistics', methods=['POST'])
def get_graph_statistics_tool():
    try:
        data = request.get_json() or {}
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({"success": False, "error": "Please provide graph_id"}), 400
        storage = current_app.extensions.get('neo4j_storage')
        if not storage:
            raise ValueError("GraphStorage not initialized — check Neo4j connection")
        tools = GraphToolsService(storage=storage)
        result = tools.get_graph_statistics(graph_id)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"Failed to get graph statistics: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500

# --- Merged from data_product.py ---
"""
Data Product API — Phase 11: AI-Ready Memory Export

REST endpoints for exporting memories as AI-consumable data products.
"""





def _get_dp():
    from ..storage.data_product import MemoryDataProduct
    driver = current_app.extensions.get('neo4j_driver')
    return MemoryDataProduct(driver=driver)


# ── RAG Corpus ──

@analytics_bp.route('/data-product/rag', methods=['GET'])
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
    result = dp.export_rag_corpus(scope, min_sal, include_rels, fmt)
    return jsonify(result)


@analytics_bp.route('/data-product/rag/download', methods=['GET'])
def download_rag():
    """Download RAG corpus as a file."""
    scope = request.args.get('scope', None)
    min_sal = request.args.get('min_salience', 0.3, type=float)

    dp = _get_dp()
    result = dp.export_rag_corpus(scope, min_sal, True, 'jsonl')
    return Response(
        result["content"],
        mimetype='application/x-jsonlines',
        headers={"Content-Disposition": "attachment; filename=mories_rag_corpus.jsonl"},
    )


# ── Knowledge Snapshot ──

@analytics_bp.route('/data-product/snapshot', methods=['GET'])
def export_snapshot():
    """Export full knowledge graph snapshot."""
    scope = request.args.get('scope', None)
    min_sal = request.args.get('min_salience', 0.0, type=float)

    dp = _get_dp()
    result = dp.export_knowledge_snapshot(scope, min_sal)
    return jsonify(result)


# ── Training Dataset ──

@analytics_bp.route('/data-product/training', methods=['GET'])
def export_training():
    """
    Export Q&A training pairs.
    Query: format(json|jsonl), min_salience
    """
    fmt = request.args.get('format', 'jsonl')
    min_sal = request.args.get('min_salience', 0.5, type=float)

    dp = _get_dp()
    result = dp.export_training_dataset(fmt, min_sal)
    return jsonify(result)


@analytics_bp.route('/data-product/training/download', methods=['GET'])
def download_training():
    """Download training dataset as file."""
    min_sal = request.args.get('min_salience', 0.5, type=float)

    dp = _get_dp()
    result = dp.export_training_dataset('jsonl', min_sal)
    return Response(
        result["content"],
        mimetype='application/x-jsonlines',
        headers={"Content-Disposition": "attachment; filename=mories_training.jsonl"},
    )


# ── Memory Manifest ──

@analytics_bp.route('/data-product/manifest', methods=['POST'])
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
    manifest = dp.create_manifest(
        name=name,
        description=data.get('description', ''),
        scope=data.get('scope', None),
        include_audit=data.get('include_audit', True),
    )
    return jsonify(manifest)


@analytics_bp.route('/data-product/manifest/list', methods=['GET'])
def list_manifests():
    """List all created manifests."""
    dp = _get_dp()
    return jsonify(dp.list_manifests())


# ── Import — Manifest ──

@analytics_bp.route('/data-product/manifest/import', methods=['POST'])
def import_manifest():
    """
    Import a Memory Manifest JSON into Neo4j.
    Body: Full manifest JSON (from create_manifest or downloaded file).
    Query: graph_id (optional), strategy (merge|create), imported_by (optional)
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Request body must be a valid manifest JSON"}), 400

    graph_id = request.args.get('graph_id', '')
    strategy = request.args.get('strategy', 'merge')
    imported_by = request.args.get('imported_by', 'api')

    if strategy not in ('merge', 'create'):
        return jsonify({"error": "strategy must be 'merge' or 'create'"}), 400

    dp = _get_dp()
    try:
        result = dp.import_manifest(
            manifest=data,
            target_graph_id=graph_id,
            merge_strategy=strategy,
            imported_by=imported_by,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Manifest import failed: {e}")
        return jsonify({"error": str(e)}), 500


# ── Import — RAG Corpus ──

@analytics_bp.route('/data-product/rag/import', methods=['POST'])
def import_rag():
    """
    Import a JSONL RAG corpus into Neo4j.
    Content-Type: application/json → body: {"content": "...jsonl..."}
    Content-Type: text/plain → body is raw JSONL content.
    Query: graph_id, scope, imported_by
    """
    content_type = request.content_type or ''

    if 'json' in content_type:
        data = request.get_json(force=True)
        content = data.get('content', '')
    else:
        # Accept raw JSONL text
        content = request.get_data(as_text=True)

    if not content or not content.strip():
        return jsonify({"error": "JSONL content is required"}), 400

    graph_id = request.args.get('graph_id', '')
    scope = request.args.get('scope', 'personal')
    imported_by = request.args.get('imported_by', 'api')

    dp = _get_dp()
    try:
        result = dp.import_rag_corpus(
            content=content,
            target_graph_id=graph_id,
            default_scope=scope,
            imported_by=imported_by,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"RAG import failed: {e}")
        return jsonify({"error": str(e)}), 500


# ── Import History ──

@analytics_bp.route('/data-product/imports', methods=['GET'])
def list_imports():
    """List all import records."""
    dp = _get_dp()
    return jsonify(dp.list_imports())


# ── Analytics CSV ──

@analytics_bp.route('/data-product/analytics/csv', methods=['GET'])
def export_csv():
    """Export analytics as CSV file."""
    dp = _get_dp()
    csv_content = dp.export_analytics_csv()
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment; filename=mories_analytics.csv"},
    )


# ── Summary ──

@analytics_bp.route('/data-product/catalog', methods=['GET'])
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
            {
                "id": "manifest_import",
                "name": "Manifest Import",
                "description": "Import a Memory Manifest JSON into Neo4j (merge or create strategy)",
                "endpoint": "/api/memory/data/manifest/import",
                "method": "POST",
                "params": ["graph_id", "strategy(merge|create)", "imported_by"],
            },
            {
                "id": "rag_import",
                "name": "RAG Corpus Import",
                "description": "Import JSONL RAG corpus documents as Entity nodes",
                "endpoint": "/api/memory/data/rag/import",
                "method": "POST",
                "params": ["graph_id", "scope", "imported_by"],
            },
            {
                "id": "import_history",
                "name": "Import History",
                "description": "List all past import operations with statistics",
                "endpoint": "/api/memory/data/imports",
                "method": "GET",
            },
        ],
        "version": "1.1.0",
    })

@analytics_bp.route('/salience_trend', methods=['GET'])
def get_salience_trend():
    """Returns memory salience distribution and trend over time."""
    driver = current_app.extensions.get('neo4j_driver')
    if not driver:
        return jsonify({"error": "Neo4j driver not initialized"}), 500

    query = """
    MATCH (e:Entity)
    WHERE e.last_accessed IS NOT NULL
    WITH substring(toString(e.last_accessed), 0, 10) AS access_date, avg(e.salience) AS avg_salience, count(e) AS memory_count
    RETURN access_date, avg_salience, memory_count
    ORDER BY access_date DESC
    LIMIT 30
    """
    
    with driver.session() as session:
        records = session.run(query).data()
    
    return jsonify({
        "status": "success",
        "trend_data": records
    })


# --- Harness (Evolutionary Process Patterns) API ---
"""
Harness API — Process Pattern Management

Endpoints:
  GET  /api/analytics/harness/list        — List all harness patterns
  GET  /api/analytics/harness/overview     — Dashboard overview stats
  GET  /api/analytics/harness/<uuid>       — Get harness detail
  POST /api/analytics/harness/record       — Record a new harness pattern
  POST /api/analytics/harness/<uuid>/execute — Record an execution
  POST /api/analytics/harness/<uuid>/evolve  — Evolve a harness pattern
  GET  /api/analytics/harness/<uuid>/compare — Compare versions
"""


def _get_category_mgr():
    """Lazy-load MemoryCategoryManager."""
    from ..storage.memory_categories import MemoryCategoryManager
    return MemoryCategoryManager()


@analytics_bp.route('/harness/list', methods=['GET'])
def list_harnesses():
    """List all harness patterns, optionally filtered by domain."""
    domain = request.args.get('domain', None)
    agent_id = request.args.get('agent_id', 'all')
    include_low = request.args.get('include_low_success', 'false') == 'true'

    try:
        mgr = _get_category_mgr()
        patterns = mgr.list_harnesses(
            domain=domain,
            agent_id=agent_id,
            include_low_success=include_low,
        )
        return jsonify({
            "status": "success",
            "count": len(patterns),
            "patterns": patterns,
        })
    except Exception as e:
        logger.error(f"Harness list failed: {e}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/harness/overview', methods=['GET'])
def harness_overview():
    """Dashboard overview: aggregated stats for harness patterns."""
    try:
        mgr = _get_category_mgr()
        all_patterns = mgr.list_harnesses(agent_id='all', include_low_success=True)

        domains = {}
        process_types = {}
        total_executions = 0
        total_success = 0
        total_failure = 0

        for p in all_patterns:
            d = p.get('domain', 'unknown')
            pt = p.get('process_type', 'unknown')
            domains[d] = domains.get(d, 0) + 1
            process_types[pt] = process_types.get(pt, 0) + 1
            total_executions += p.get('execution_count', 0)
            sr = p.get('success_rate', 0)
            ec = p.get('execution_count', 0)
            total_success += int(sr * ec)
            total_failure += int((1 - sr) * ec)

        avg_success_rate = (total_success / total_executions) if total_executions > 0 else 0

        return jsonify({
            "status": "success",
            "overview": {
                "total_patterns": len(all_patterns),
                "total_executions": total_executions,
                "avg_success_rate": round(avg_success_rate, 3),
                "total_success": total_success,
                "total_failure": total_failure,
                "domains": domains,
                "process_types": process_types,
            }
        })
    except Exception as e:
        logger.error(f"Harness overview failed: {e}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/harness/<uuid>', methods=['GET'])
def get_harness_detail(uuid):
    """Get detailed info for a specific harness pattern."""
    try:
        mgr = _get_category_mgr()
        result = mgr.recall_harness(harness_uuid=uuid)
        if result.get('error'):
            return jsonify(result), 404
        return jsonify({"status": "success", "harness": result})
    except Exception as e:
        logger.error(f"Harness detail failed: {e}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/harness/record', methods=['POST'])
def record_harness():
    """Record a new harness pattern."""
    data = request.get_json(force=True)
    domain = data.get('domain')
    trigger = data.get('trigger')
    tool_chain = data.get('tool_chain', [])
    if not domain or not trigger or not tool_chain:
        return jsonify({"error": "domain, trigger, and tool_chain are required"}), 400

    try:
        mgr = _get_category_mgr()
        result = mgr.record_harness(
            domain=domain,
            trigger=trigger,
            tool_chain=tool_chain,
            description=data.get('description', ''),
            process_type=data.get('process_type', 'pipeline'),
            data_flow=data.get('data_flow'),
            tags=data.get('tags'),
            agent_id=data.get('agent_id', 'system'),
            scope=data.get('scope', 'tribal'),
        )
        return jsonify(result), 201
    except Exception as e:
        logger.error(f"Harness record failed: {e}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/harness/<uuid>/execute', methods=['POST'])
def record_harness_execution(uuid):
    """Record an execution result for a harness pattern."""
    data = request.get_json(force=True)
    try:
        mgr = _get_category_mgr()
        result = mgr.record_harness_execution(
            harness_uuid=uuid,
            success=data.get('success', True),
            execution_time_ms=data.get('execution_time_ms', 0),
            context=data.get('context', {}),
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Harness execution record failed: {e}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/harness/<uuid>/evolve', methods=['POST'])
def evolve_harness(uuid):
    """Evolve a harness pattern with a new tool chain."""
    data = request.get_json(force=True)
    new_chain = data.get('new_tool_chain', [])
    reason = data.get('reason', '')
    if not new_chain:
        return jsonify({"error": "new_tool_chain is required"}), 400

    try:
        mgr = _get_category_mgr()
        result = mgr.evolve_harness(
            harness_uuid=uuid,
            new_tool_chain=new_chain,
            change_reason=reason,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Harness evolve failed: {e}")
        return jsonify({"error": str(e)}), 500


@analytics_bp.route('/harness/<uuid>/compare', methods=['GET'])
def compare_harness(uuid):
    """Compare two versions of a harness pattern."""
    version_a = request.args.get('version_a', type=int)
    version_b = request.args.get('version_b', type=int)

    try:
        mgr = _get_category_mgr()
        result = mgr.compare_harness_versions(
            harness_uuid=uuid,
            version_a=version_a,
            version_b=version_b,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Harness compare failed: {e}")
        return jsonify({"error": str(e)}), 500

