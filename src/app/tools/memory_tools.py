"""
Mnemosyne MCP Tools — Agent-Callable Memory Tool Definitions

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

class MnemosyneToolkit:
    """
    Complete toolkit for agent-based memory operations.

    Usage:
        toolkit = MnemosyneToolkit()
        result = toolkit.execute("memory_store", {"content": "...", "source": "agent"})
        tools = toolkit.get_all_schemas("openai")
    """

    def __init__(self):
        from ..storage.memory_manager import MemoryManager
        self._manager = MemoryManager()
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_tools()

    def close(self):
        self._manager.close()

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

        from neo4j import GraphDatabase
        from ..config import Config
        driver = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD))

        with driver.session() as session:
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


        driver.close()

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
        bridge = SynapticBridge()
        try:
            return bridge.share_memory(from_agent, uuid, target_scope, message)
        finally:
            bridge.close()

    def _exec_memory_empathy(self, uuid: str, from_agent: str,
                             boost_amount: float = 0.1, reason: str = "") -> dict:
        from ..storage.synaptic_bridge import SynapticBridge
        bridge = SynapticBridge()
        try:
            return bridge.empathy_boost(from_agent, uuid, boost_amount, reason)
        finally:
            bridge.close()

    def _exec_memory_status(self) -> dict:
        return self._manager.get_memory_overview()

    def _exec_memory_decay_run(self, dry_run: bool = True) -> dict:
        return self._manager.run_decay(dry_run=dry_run)

    def _exec_memory_export(self, format: str, scope: str = None,
                            min_salience: float = 0.3,
                            manifest_name: str = None) -> dict:
        from ..storage.data_product import MemoryDataProduct
        dp = MemoryDataProduct()
        try:
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
        finally:
            dp.close()

    def _exec_memory_history(self, uuid: str) -> dict:
        from ..storage.memory_audit import MemoryAudit
        audit = MemoryAudit()
        try:
            return audit.get_history(uuid)
        finally:
            audit.close()

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


    # ── Helpers ──

    def _set_scope(self, uuid: str, scope: str):
        """Set scope on an entity node."""
        from neo4j import GraphDatabase
        from ..config import Config
        driver = GraphDatabase.driver(Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD))
        with driver.session() as session:
            session.run("MATCH (e:Entity {uuid: $uuid}) SET e.scope = $scope",
                       uuid=uuid, scope=scope)
        driver.close()

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
