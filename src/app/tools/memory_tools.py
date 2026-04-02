"""
Mories MCP Tools — Agent-Callable Memory Tool Definitions

Provides structured tool definitions that multi-agent frameworks
(ADK, LangGraph, CrewAI, OpenAI Function Calling) can directly invoke.

Each tool has:
  - name, description, parameters (JSON Schema)
  - execute() method wired to the actual engine
"""

import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

logger = logging.getLogger('mirofish.mcp_tools')


# ──────────────────────────────────────────
# Tool Definition Schema
# ──────────────────────────────────────────

@dataclass
class ToolParameter:
    name: str
    type: str  # string, number, boolean, array
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: List[ToolParameter]
    category: str = "memory"

    def to_openai_schema(self) -> dict:
        """Export as OpenAI Function Calling compatible schema."""
        props = {}
        required = []
        for p in self.parameters:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            props[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }

    def to_mcp_schema(self) -> dict:
        """Export as MCP-compatible tool schema."""
        props = {}
        required = []
        for p in self.parameters:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            props[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        }


# ──────────────────────────────────────────
# Tool Registry
# ──────────────────────────────────────────

class MoriesToolkit:
    """
    Complete toolkit for agent-based memory operations.

    Usage:
        toolkit = MoriesToolkit()
        result = toolkit.execute("memory_store", {"content": "...", "source": "agent"})
        tools = toolkit.get_all_schemas("openai")
    """

    def __init__(self):
        from ..storage.memory_manager import MemoryManager
        self._manager = MemoryManager.get_instance()
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_tools()

    def close(self):
        pass  # Singleton — do not close shared manager

    # ──────────────────────────────────────────
    # Tool Definitions
    # ──────────────────────────────────────────

    def _register_tools(self):
        """Register all available memory tools."""

        # 1. memory_store — 기억 저장
        self._tools["memory_store"] = ToolDefinition(
            name="memory_store",
            description="새로운 기억을 단기기억(STM) 버퍼에 저장합니다. salience가 자동 임계값(0.7) 이상이면 자동으로 장기기억(LTM)에 승격됩니다.",
            parameters=[
                ToolParameter("content", "string", "저장할 기억 내용"),
                ToolParameter("source", "string", "기억 출처 (agent, user, document, observation 등)", default="agent"),
                ToolParameter("salience", "number", "중요도 0.0~1.0 (높을수록 중요)", required=False, default=0.5),
                ToolParameter("metadata", "object", "추가 메타데이터", required=False),
                ToolParameter("scope", "string", "기억 범위", required=False, default="personal",
                            enum=["personal", "tribal", "social", "global"]),
            ],
        )

        # 2. memory_search — 기억 검색 (자동 강화 포함)
        self._tools["memory_search"] = ToolDefinition(
            name="memory_search",
            description="저장된 기억을 검색합니다. 검색된 기억은 자동으로 salience가 강화됩니다 (Retrieval Boost).",
            parameters=[
                ToolParameter("query", "string", "검색 질의"),
                ToolParameter("scope", "string", "검색 범위 필터", required=False,
                            enum=["personal", "tribal", "social", "global", "all"]),
                ToolParameter("limit", "number", "최대 결과 수", required=False, default=10),
                ToolParameter("min_salience", "number", "최소 salience 필터", required=False, default=0.1),
            ],
        )

        # 3. memory_recall — 특정 기억 상세 조회
        self._tools["memory_recall"] = ToolDefinition(
            name="memory_recall",
            description="UUID로 특정 기억을 상세 조회합니다. 조회 시 salience가 강화됩니다.",
            parameters=[
                ToolParameter("uuid", "string", "기억의 UUID"),
            ],
        )

        # 4. memory_boost — 수동 강화/약화
        self._tools["memory_boost"] = ToolDefinition(
            name="memory_boost",
            description="특정 기억의 중요도(salience)를 수동으로 조정합니다. 양수면 강화, 음수면 약화.",
            parameters=[
                ToolParameter("uuid", "string", "기억의 UUID"),
                ToolParameter("amount", "number", "조정량 (-1.0 ~ 1.0)", default=0.1),
                ToolParameter("reason", "string", "조정 사유", required=False, default=""),
            ],
        )

        # 5. memory_share — 기억 공유 (스코프 변경)
        self._tools["memory_share"] = ToolDefinition(
            name="memory_share",
            description="기억을 다른 에이전트나 스코프로 공유합니다.",
            parameters=[
                ToolParameter("uuid", "string", "공유할 기억의 UUID"),
                ToolParameter("from_agent", "string", "공유하는 에이전트 ID"),
                ToolParameter("target_scope", "string", "공유 대상 스코프",
                            enum=["tribal", "social", "global"]),
                ToolParameter("message", "string", "공유 메시지", required=False, default=""),
            ],
        )

        # 6. memory_empathy — 공감 강화
        self._tools["memory_empathy"] = ToolDefinition(
            name="memory_empathy",
            description="다른 에이전트의 기억을 확인하고 공감 강화합니다. 양쪽 모두 salience가 상승합니다.",
            parameters=[
                ToolParameter("uuid", "string", "강화할 기억의 UUID"),
                ToolParameter("from_agent", "string", "강화하는 에이전트 ID"),
                ToolParameter("boost_amount", "number", "강화량 0.0~0.5", required=False, default=0.1),
                ToolParameter("reason", "string", "강화 사유", required=False, default=""),
            ],
        )

        # 7. memory_status — 기억 시스템 상태 조회
        self._tools["memory_status"] = ToolDefinition(
            name="memory_status",
            description="전체 기억 시스템의 건강 상태를 조회합니다. STM/LTM 통계, 감쇠 현황, 위험 기억 등.",
            parameters=[],
        )

        # 8. memory_decay_run — 망각 실행/시뮬레이션
        self._tools["memory_decay_run"] = ToolDefinition(
            name="memory_decay_run",
            description="Ebbinghaus 망각 곡선 기반 감쇠 사이클을 실행합니다. dry_run=true면 시뮬레이션만 합니다.",
            parameters=[
                ToolParameter("dry_run", "boolean", "시뮬레이션 모드 여부", required=False, default=True),
            ],
        )

        # 9. memory_export — 데이터 제품 내보내기
        self._tools["memory_export"] = ToolDefinition(
            name="memory_export",
            description="기억 데이터를 AI-Ready 형식으로 내보냅니다.",
            parameters=[
                ToolParameter("format", "string", "내보내기 형식",
                            enum=["rag_corpus", "knowledge_snapshot", "training_dataset", "manifest", "analytics_csv"]),
                ToolParameter("scope", "string", "스코프 필터", required=False),
                ToolParameter("min_salience", "number", "최소 salience", required=False, default=0.3),
                ToolParameter("manifest_name", "string", "Manifest 이름 (manifest 형식일 때)", required=False),
            ],
        )

        # 10. memory_history — 변경 이력 조회
        self._tools["memory_history"] = ToolDefinition(
            name="memory_history",
            description="특정 기억의 전체 변경 이력을 조회합니다. 언제 생성/강화/감쇠/공유되었는지 타임라인.",
            parameters=[
                ToolParameter("uuid", "string", "기억의 UUID"),
            ],
        )

        # 11. memory_encrypt — 기억 암호화
        self._tools["memory_encrypt"] = ToolDefinition(
            name="memory_encrypt",
            description="특정 기억을 AES-256으로 암호화합니다. 암호화된 기억은 복호화 키 없이 읽을 수 없습니다.",
            category="security",
            parameters=[
                ToolParameter("uuid", "string", "암호화할 기억의 UUID"),
                ToolParameter("fields", "array", "암호화할 필드 목록", required=False),
            ],
        )

        # 12. memory_decrypt — 기억 복호화 (일시적 반환)
        self._tools["memory_decrypt"] = ToolDefinition(
            name="memory_decrypt",
            description="암호화된 기억을 복호화하여 원문을 반환합니다. DB에는 암호화 상태를 유지합니다.",
            category="security",
            parameters=[
                ToolParameter("uuid", "string", "복호화할 기억의 UUID"),
            ],
        )

        # 13. memory_check_access — 접근 권한 확인
        self._tools["memory_check_access"] = ToolDefinition(
            name="memory_check_access",
            description="특정 주체(에이전트/사용자)가 기억에 대한 특정 작업을 수행할 수 있는지 확인합니다.",
            category="security",
            parameters=[
                ToolParameter("principal_id", "string", "확인할 주체 ID"),
                ToolParameter("action", "string", "확인할 작업",
                            enum=["search", "store", "boost", "share", "decrypt", "export"]),
                ToolParameter("scope", "string", "기억 스코프", required=False, default="personal"),
            ],
        )

        # 14. research_context — 연구 컨텍스트 조회 (AutoResearchClaw 통합)
        self._tools["research_context"] = ToolDefinition(
            name="research_context",
            description="연구 주제에 대한 기존 지식·논문·실험·교훈을 검색하여 카테고리별로 정리된 컨텍스트를 반환합니다. AutoResearchClaw 파이프라인의 Stage 4(문헌 수집), Stage 7(합성)에서 활용합니다.",
            category="research",
            parameters=[
                ToolParameter("topic", "string", "연구 주제 또는 검색 쿼리"),
                ToolParameter("limit", "number", "최대 결과 수", required=False, default=20),
                ToolParameter("categories", "array", "필터할 카테고리 (paper, citation, experiment, lesson, synthesis)", required=False),
                ToolParameter("graph_id", "string", "프로젝트 그래프 ID", required=False),
            ],
        )

        # 15. research_archive — 연구 결과 일괄 아카이브 (AutoResearchClaw 통합)
        self._tools["research_archive"] = ToolDefinition(
            name="research_archive",
            description="연구 파이프라인의 결과물(논문, 참조, 실험, 리뷰, 교훈)을 구조화하여 기억에 일괄 저장합니다. AutoResearchClaw의 Stage 21(KNOWLEDGE_ARCHIVE)에서 호출합니다.",
            category="research",
            parameters=[
                ToolParameter("run_id", "string", "연구 실행 ID"),
                ToolParameter("topic", "string", "연구 주제"),
                ToolParameter("artifacts", "object", "아티팩트 객체: {paper_draft?, references?, experiment_results?, reviews?, synthesis?, lessons?}"),
                ToolParameter("graph_id", "string", "프로젝트 그래프 ID", required=False, default="research"),
            ],
        )

        # ── Cognitive Memory Tools ──

        # 16. memory_preference — 선호 기억 저장
        self._tools["memory_preference"] = ToolDefinition(
            name="memory_preference",
            description="사용자/에이전트의 선호를 기억합니다. 같은 키의 선호가 이미 있으면 업서트합니다.",
            category="cognitive",
            parameters=[
                ToolParameter("key", "string", "선호 키 (예: language, coding_style)"),
                ToolParameter("value", "string", "선호 값 (예: korean, functional)"),
                ToolParameter("description", "string", "선호 설명", required=False, default=""),
                ToolParameter("subcategory", "string", "선호 카테고리", required=False, default="general",
                            enum=["communication", "coding_style", "workflow", "ui", "general"]),
                ToolParameter("confidence", "number", "확신도 0.0~1.0", required=False, default=0.8),
            ],
        )

        # 17. memory_recall_preferences
        self._tools["memory_recall_preferences"] = ToolDefinition(
            name="memory_recall_preferences",
            description="저장된 선호를 회상합니다. 세션 시작 시 호출하여 사용자 맥락을 복원합니다.",
            category="cognitive",
            parameters=[
                ToolParameter("key", "string", "특정 키 필터", required=False),
            ],
        )

        # 18. memory_instruction — 행동 규칙 기억
        self._tools["memory_instruction"] = ToolDefinition(
            name="memory_instruction",
            description="행동 규칙을 기억합니다. must 수준은 자동으로 영구 기억(PM)으로 승격됩니다.",
            category="cognitive",
            parameters=[
                ToolParameter("rule", "string", "규칙 내용"),
                ToolParameter("trigger", "string", "적용 시점", required=False, default="always",
                            enum=["always", "pre_commit", "pre_code", "pre_deploy", "on_error"]),
                ToolParameter("priority", "string", "우선순위", required=False, default="should",
                            enum=["must", "should", "may"]),
                ToolParameter("subcategory", "string", "규칙 분류", required=False, default="workflow",
                            enum=["coding", "workflow", "communication", "security"]),
            ],
        )

        # 19. memory_recall_instructions
        self._tools["memory_recall_instructions"] = ToolDefinition(
            name="memory_recall_instructions",
            description="활성 행동 규칙을 회상합니다. 작업 전 준수 규칙 확인용.",
            category="cognitive",
            parameters=[
                ToolParameter("trigger", "string", "시점 필터", required=False,
                            enum=["always", "pre_commit", "pre_code", "pre_deploy", "on_error"]),
                ToolParameter("priority", "string", "우선순위 필터", required=False,
                            enum=["must", "should", "may"]),
            ],
        )

        # 20. memory_reflection — 자기 성찰 기억
        self._tools["memory_reflection"] = ToolDefinition(
            name="memory_reflection",
            description="성찰/교훈을 기억합니다. 동일 교훈 반복 시 자동 강화됩니다.",
            category="cognitive",
            parameters=[
                ToolParameter("event", "string", "발생 이벤트"),
                ToolParameter("lesson", "string", "교훈"),
                ToolParameter("severity", "string", "심각도", required=False, default="medium",
                            enum=["high", "medium", "low"]),
                ToolParameter("domain", "string", "교훈 영역", required=False, default="general"),
            ],
        )

        # 21. memory_recall_reflections
        self._tools["memory_recall_reflections"] = ToolDefinition(
            name="memory_recall_reflections",
            description="과거 교훈을 회상합니다. 같은 실수 방지용.",
            category="cognitive",
            parameters=[
                ToolParameter("domain", "string", "영역 필터", required=False),
                ToolParameter("severity", "string", "심각도 필터", required=False,
                            enum=["high", "medium", "low"]),
            ],
        )

        # 22. memory_conditional — 조건부 지식
        self._tools["memory_conditional"] = ToolDefinition(
            name="memory_conditional",
            description="IF condition THEN action 형태의 조건부 지식을 기억합니다.",
            category="cognitive",
            parameters=[
                ToolParameter("condition", "object", "조건 (예: {\"python_version\": \"<3.10\"})"),
                ToolParameter("then_action", "string", "조건 충족 시 행동"),
                ToolParameter("else_action", "string", "미충족 시 행동", required=False),
                ToolParameter("subcategory", "string", "조건 유형", required=False, default="contextual",
                            enum=["version_specific", "env_specific", "temporal", "contextual"]),
                ToolParameter("confidence", "number", "확신도", required=False, default=0.9),
            ],
        )

        # 23. memory_recall_conditionals
        self._tools["memory_recall_conditionals"] = ToolDefinition(
            name="memory_recall_conditionals",
            description="조건부 지식을 회상합니다. context 전달 시 매칭되는 것만 반환.",
            category="cognitive",
            parameters=[
                ToolParameter("context", "object", "현재 환경 컨텍스트", required=False),
                ToolParameter("subcategory", "string", "유형 필터", required=False,
                            enum=["version_specific", "env_specific", "temporal", "contextual"]),
            ],
        )

        # 24. memory_task_handoff — 멀티에이전트 태스크 핸드오프
        self._tools["memory_task_handoff"] = ToolDefinition(
            name="memory_task_handoff",
            description="멀티에이전트 태스크를 위임합니다. 컨텍스트와 함께 기억에 저장.",
            category="orchestration",
            parameters=[
                ToolParameter("task_id", "string", "고유 태스크 ID"),
                ToolParameter("task_description", "string", "태스크 설명"),
                ToolParameter("from_agent", "string", "위임 에이전트 ID"),
                ToolParameter("to_agent", "string", "수신 에이전트 ID"),
                ToolParameter("context", "object", "공유 컨텍스트", required=False),
                ToolParameter("task_type", "string", "유형", required=False, default="handoff",
                            enum=["handoff", "delegation", "coordination", "escalation"]),
            ],
        )

        # 25. memory_task_update
        self._tools["memory_task_update"] = ToolDefinition(
            name="memory_task_update",
            description="태스크 상태 업데이트. 실패 시 자동 성찰 기억 생성.",
            category="orchestration",
            parameters=[
                ToolParameter("task_id", "string", "태스크 ID"),
                ToolParameter("status", "string", "새 상태",
                            enum=["in_progress", "completed", "failed", "escalated"]),
                ToolParameter("result_summary", "string", "결과 요약", required=False),
                ToolParameter("escalate_to", "string", "에스컬레이션 대상", required=False),
            ],
        )

        # 26. memory_active_tasks
        self._tools["memory_active_tasks"] = ToolDefinition(
            name="memory_active_tasks",
            description="활성 멀티에이전트 태스크 조회.",
            category="orchestration",
            parameters=[
                ToolParameter("agent_id", "string", "에이전트 ID 필터", required=False),
            ],
        )

    # ──────────────────────────────────────────
    # Tool Execution
    # ──────────────────────────────────────────

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with given arguments."""
        if tool_name not in self._tools:
            return {"error": f"Unknown tool: {tool_name}", "available": list(self._tools.keys())}

        handler = getattr(self, f"_exec_{tool_name}", None)
        if not handler:
            return {"error": f"Handler not implemented for {tool_name}"}

        try:
            result = handler(**arguments)
            return {"status": "success", "tool": tool_name, "result": result}
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} — {e}", exc_info=True)
            return {"status": "error", "tool": tool_name, "error": str(e)}

    # ── Handlers ──

    def _exec_memory_store(self, content: str, source: str = "agent",
                           salience: float = 0.5, metadata: dict = None,
                           scope: str = "personal") -> dict:
        meta = metadata or {}
        meta["scope"] = scope

        item = self._manager.stm_add(content=content, source=source,
                                      metadata=meta, ttl=None)
        # Set salience
        self._manager.stm_evaluate(item.id, salience)

        # Auto-promote if salience >= threshold
        if salience >= self._manager.config.auto_promote_threshold:
            result = self._manager.stm_promote(item.id)
            # Set scope on promoted entity
            if result.get("ltm_uuid"):
                self._set_scope(result["ltm_uuid"], scope)
            return {**result, "auto_promoted": True, "scope": scope}

        return {"stm_id": item.id, "salience": salience, "scope": scope,
                "status": "stored_in_stm",
                "note": f"Auto-promote at salience >= {self._manager.config.auto_promote_threshold}"}

    def _exec_memory_search(self, query: str, scope: str = "all",
                            limit: int = 10, min_salience: float = 0.1) -> dict:
        scope_filter = f"AND e.scope = '{scope}'" if scope != "all" else ""

        with self._manager._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL
                  AND e.salience >= $min_sal
                  AND (toLower(e.name) CONTAINS toLower($search_term)
                       OR toLower(COALESCE(e.summary, '')) CONTAINS toLower($search_term))
                  {scope_filter}
                RETURN e.uuid AS uuid, e.name AS name,
                       e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       e.summary AS summary,
                       e.access_count AS access_count,
                       e.last_accessed AS last_accessed
                ORDER BY e.salience DESC
                LIMIT $limit
            """, search_term=query, min_sal=min_salience, limit=limit).data()

        # Retrieval boost for found items
        if records:
            uuids = [r["uuid"] for r in records]
            boosted = self._manager.boost_on_retrieval(uuids)
            return {"results": records, "count": len(records), "retrieval_boosted": boosted}

        return {"results": [], "count": 0, "retrieval_boosted": 0}

    def _exec_memory_recall(self, uuid: str) -> dict:
        result = self._manager.get_salience_timeline(uuid)
        if "error" not in result:
            self._manager.boost_on_retrieval([uuid])
        return result

    def _exec_memory_boost(self, uuid: str, amount: float = 0.1, reason: str = "") -> dict:
        return self._manager.manual_boost(uuid, amount)

    def _exec_memory_share(self, uuid: str, from_agent: str,
                           target_scope: str = "tribal", message: str = "") -> dict:
        from ..storage.synaptic_bridge import SynapticBridge
        driver = self._manager._driver if self._manager else None
        bridge = SynapticBridge(driver=driver)
        return bridge.share_memory(from_agent, uuid, target_scope, message)

    def _exec_memory_empathy(self, uuid: str, from_agent: str,
                             boost_amount: float = 0.1, reason: str = "") -> dict:
        from ..storage.synaptic_bridge import SynapticBridge
        driver = self._manager._driver if self._manager else None
        bridge = SynapticBridge(driver=driver)
        return bridge.empathy_boost(from_agent, uuid, boost_amount, reason)

    def _exec_memory_status(self) -> dict:
        return self._manager.get_memory_overview()

    def _exec_memory_decay_run(self, dry_run: bool = True) -> dict:
        return self._manager.run_decay(dry_run=dry_run)

    def _exec_memory_export(self, format: str, scope: str = None,
                            min_salience: float = 0.3,
                            manifest_name: str = None) -> dict:
        from ..storage.data_product import MemoryDataProduct
        driver = self._manager._driver if self._manager else None
        dp = MemoryDataProduct(driver=driver)
        if format == "rag_corpus":
            return dp.export_rag_corpus(scope, min_salience, True, "json")
        elif format == "knowledge_snapshot":
            return dp.export_knowledge_snapshot(scope, min_salience)
        elif format == "training_dataset":
            return dp.export_training_dataset("json", min_salience)
        elif format == "manifest":
            name = manifest_name or f"Snapshot-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
            return dp.create_manifest(name, scope=scope)
        elif format == "analytics_csv":
            return {"csv": dp.export_analytics_csv()}
        else:
            return {"error": f"Unknown format: {format}"}

    def _exec_memory_history(self, uuid: str) -> dict:
        from ..storage.memory_audit import MemoryAudit
        driver = self._manager._driver if self._manager else None
        audit = MemoryAudit(driver=driver)
        return audit.get_history(uuid)

    # ── Security Handlers ──

    def _exec_memory_encrypt(self, uuid: str, fields: list = None) -> dict:
        from ..security.memory_encryption import get_encryption
        enc = get_encryption()
        return enc.encrypt_memory(uuid, fields=fields)

    def _exec_memory_decrypt(self, uuid: str) -> dict:
        from ..security.memory_encryption import get_encryption
        enc = get_encryption()
        return enc.decrypt_memory(uuid)

    def _exec_memory_check_access(self, principal_id: str, action: str,
                                   scope: str = "personal") -> dict:
        from ..security.memory_rbac import get_rbac
        rbac = get_rbac()
        return rbac.check_permission(principal_id, action, scope)

    # ── Research Integration Handlers (AutoResearchClaw) ──

    def _exec_research_context(self, topic: str, limit: int = 20,
                               categories: list = None,
                               graph_id: str = None) -> dict:
        """Retrieve categorized prior knowledge for a research topic."""
        cat_filter = ""
        if categories:
            type_list = ", ".join(f"'{c}'" for c in categories)
            cat_filter = f"AND e.metadata_type IN [{type_list}]"

        graph_filter = f"AND e.graph_id = '{graph_id}'" if graph_id else ""

        with self._manager._driver.session() as session:
            records = session.run(f"""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL
                  AND e.salience >= 0.3
                  AND (toLower(e.name) CONTAINS toLower($topic)
                       OR toLower(COALESCE(e.summary, '')) CONTAINS toLower($topic))
                  {cat_filter}
                  {graph_filter}
                RETURN e.uuid AS uuid, e.name AS name,
                       e.salience AS salience,
                       COALESCE(e.scope, 'personal') AS scope,
                       e.summary AS summary,
                       COALESCE(e.metadata_type, 'general') AS category,
                       e.metadata_run_id AS run_id,
                       e.metadata_topic AS topic
                ORDER BY e.salience DESC
                LIMIT $limit
            """, topic=topic, limit=limit).data()

        categorized = {"papers": [], "citations": [], "experiments": [],
                       "lessons": [], "synthesis": [], "other": []}
        category_map = {
            "paper_draft": "papers", "synthesis": "synthesis",
            "citation": "citations", "experiment_result": "experiments",
            "lesson_learned": "lessons"
        }

        for r in records:
            bucket = category_map.get(r.get("category"), "other")
            categorized[bucket].append({
                "uuid": r["uuid"],
                "content": r.get("name") or r.get("summary", ""),
                "salience": r.get("salience", 0),
                "run_id": r.get("run_id"),
                "topic": r.get("topic"),
            })

        if records:
            uuids = [r["uuid"] for r in records]
            self._manager.boost_on_retrieval(uuids)

        return {
            "topic": topic,
            "total_found": len(records),
            "categories": {k: len(v) for k, v in categorized.items()},
            "context": categorized,
        }

    def _exec_research_archive(self, run_id: str, topic: str,
                               artifacts: dict,
                               graph_id: str = "research") -> dict:
        """Batch-store research pipeline outputs as structured memories."""
        stored = []
        errors = []

        artifact_types = [
            ("paper_draft", "paper_draft", 0.9, "tribal"),
            ("synthesis", "synthesis", 0.85, "tribal"),
            ("experiment_results", "experiment_result", 0.8, "tribal"),
            ("reviews", "peer_review", 0.7, "tribal"),
            ("lessons", "lesson_learned", 0.95, "global"),
        ]

        for key, mem_type, salience, scope in artifact_types:
            data = artifacts.get(key)
            if not data:
                continue

            items_to_store = data if isinstance(data, list) else [data]

            for item in items_to_store:
                content = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                prefix = f"[{mem_type.replace('_', ' ').title()}] {topic}"
                full_content = f"{prefix}\n\n{content[:5000]}"

                try:
                    result = self._exec_memory_store(
                        content=full_content,
                        source=f"researchclaw:{run_id}:{mem_type}",
                        salience=salience,
                        metadata={
                            "type": mem_type,
                            "run_id": run_id,
                            "topic": topic,
                            "graph_id": graph_id,
                        },
                        scope=scope,
                    )
                    stored.append({"type": mem_type, "status": result.get("status", "stored")})
                except Exception as e:
                    errors.append({"type": mem_type, "error": str(e)})

        refs = artifacts.get("references", [])
        if isinstance(refs, list):
            for ref in refs[:50]:
                ref_text = ref if isinstance(ref, str) else f"{ref.get('title', 'Unknown')} ({ref.get('year', 'N/A')})"
                try:
                    self._exec_memory_store(
                        content=f"[Citation] {ref_text}",
                        source=f"researchclaw:{run_id}:citation",
                        salience=0.6,
                        metadata={"type": "citation", "run_id": run_id, "graph_id": graph_id},
                        scope="tribal",
                    )
                    stored.append({"type": "citation", "status": "stored"})
                except Exception as e:
                    errors.append({"type": "citation", "error": str(e)})

        return {
            "run_id": run_id,
            "topic": topic,
            "graph_id": graph_id,
            "total_stored": len(stored),
            "errors": errors,
            "summary": stored,
        }

    # ── Cognitive Memory Handlers ──

    def _get_category_manager(self):
        """Lazy-load MemoryCategoryManager."""
        from ..storage.memory_categories import MemoryCategoryManager
        driver = self._manager._driver if self._manager else None
        return MemoryCategoryManager(driver=driver)

    def _exec_memory_preference(self, key: str, value: str,
                                description: str = "", subcategory: str = "general",
                                confidence: float = 0.8) -> dict:
        mgr = self._get_category_manager()
        return mgr.record_preference(key=key, value=value, description=description,
                                      subcategory=subcategory, confidence=confidence)

    def _exec_memory_recall_preferences(self, key: str = None) -> dict:
        mgr = self._get_category_manager()
        return {"preferences": mgr.recall_preferences(key=key)}

    def _exec_memory_instruction(self, rule: str, trigger: str = "always",
                                  priority: str = "should",
                                  subcategory: str = "workflow") -> dict:
        mgr = self._get_category_manager()
        return mgr.record_instruction(rule=rule, trigger=trigger,
                                       priority=priority, subcategory=subcategory)

    def _exec_memory_recall_instructions(self, trigger: str = None,
                                          priority: str = None) -> dict:
        mgr = self._get_category_manager()
        return {"instructions": mgr.recall_instructions(trigger=trigger, priority=priority)}

    def _exec_memory_reflection(self, event: str, lesson: str,
                                 severity: str = "medium",
                                 domain: str = "general") -> dict:
        mgr = self._get_category_manager()
        return mgr.record_reflection(event=event, lesson=lesson,
                                      severity=severity, domain=domain)

    def _exec_memory_recall_reflections(self, domain: str = None,
                                         severity: str = None) -> dict:
        mgr = self._get_category_manager()
        return {"reflections": mgr.recall_reflections(domain=domain, severity=severity)}

    def _exec_memory_conditional(self, condition: dict, then_action: str,
                                  else_action: str = None,
                                  subcategory: str = "contextual",
                                  confidence: float = 0.9) -> dict:
        mgr = self._get_category_manager()
        return mgr.record_conditional(condition=condition, then_action=then_action,
                                       else_action=else_action, subcategory=subcategory,
                                       confidence=confidence)

    def _exec_memory_recall_conditionals(self, context: dict = None,
                                          subcategory: str = None) -> dict:
        mgr = self._get_category_manager()
        return {"conditionals": mgr.recall_conditionals(context=context, subcategory=subcategory)}

    def _exec_memory_task_handoff(self, task_id: str, task_description: str,
                                   from_agent: str, to_agent: str,
                                   context: dict = None,
                                   task_type: str = "handoff") -> dict:
        mgr = self._get_category_manager()
        return mgr.record_task_handoff(task_id=task_id, task_description=task_description,
                                        from_agent=from_agent, to_agent=to_agent,
                                        context=context, task_type=task_type)

    def _exec_memory_task_update(self, task_id: str, status: str,
                                  result_summary: str = None,
                                  escalate_to: str = None) -> dict:
        mgr = self._get_category_manager()
        return mgr.update_task_status(task_id=task_id, status=status,
                                       result_summary=result_summary,
                                       escalate_to=escalate_to)

    def _exec_memory_active_tasks(self, agent_id: str = None) -> dict:
        mgr = self._get_category_manager()
        return {"tasks": mgr.get_active_tasks(agent_id=agent_id)}

    # ── Helpers ──

    def _set_scope(self, uuid: str, scope: str):
        """Set scope on an entity node."""
        with self._manager._driver.session() as session:
            session.run("MATCH (e:Entity {uuid: $uuid}) SET e.scope = $scope",
                       uuid=uuid, scope=scope)

    # ──────────────────────────────────────────
    # Schema Export
    # ──────────────────────────────────────────

    def get_all_schemas(self, format: str = "openai") -> List[dict]:
        """Export all tool schemas in the specified format."""
        if format == "openai":
            return [t.to_openai_schema() for t in self._tools.values()]
        elif format == "mcp":
            return [t.to_mcp_schema() for t in self._tools.values()]
        else:
            return [asdict(t) for t in self._tools.values()]

    def get_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def get_tool_description(self, name: str) -> Optional[dict]:
        tool = self._tools.get(name)
        return asdict(tool) if tool else None

