"""
memory_bridge.py — Harness ↔ Mories 범용 메모리 브릿지

하네스 실행 결과(경험)를 Mories 인지 메모리 파이프라인으로 변환한다.
단일 목적이 아닌 **범용 확장**으로, 어떤 도메인의 하네스든
Mories의 STM/LTM/Decay/Search 체계에 편입되도록 설계.

4가지 경험 유형을 인지 메모리로 라우팅:
  SUCCESS  → LTM 저장 (high salience)
  FAILURE  → Reflection(교훈) 기록
  CAPTURED → 재사용 가능한 Pattern 등록
  HEALED   → Reflection + LTM 저장 (자기수복 성공)

작성: 2026-04-04
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("harness.memory_bridge")


class ExperienceType(Enum):
    SUCCESS = "SUCCESS"       # 정상 성공
    FAILURE = "FAILURE"       # 실패 (FIX 필요)
    CAPTURED = "CAPTURED"     # 새 패턴 포착
    HEALED = "HEALED"         # 자기수복 후 성공
    DERIVED = "DERIVED"       # 도메인 포크
    HUMAN_CORRECTED = "HUMAN_CORRECTED" # HITL 피드백에 의한 교정/규칙 추가


@dataclass
class HarnessExperience:
    """하네스 실행 경험 — Mories 메모리 변환의 단위 입력."""
    harness_id: str
    domain: str
    run_id: str
    experience_type: ExperienceType
    tool_chain: List[str]
    elapsed_ms: int
    summary: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_markdown(self) -> str:
        """Mories ingest용 마크다운 포맷 변환."""
        lines = [
            f"## Harness Experience: {self.harness_id}",
            f"- **Type**: {self.experience_type.value}",
            f"- **Domain**: {self.domain}",
            f"- **Run ID**: {self.run_id}",
            f"- **Tool Chain**: {' → '.join(self.tool_chain)}",
            f"- **Elapsed**: {self.elapsed_ms}ms",
            f"- **Timestamp**: {self.timestamp}",
        ]
        if self.summary:
            lines.append(f"\n### Summary\n{self.summary}")
        if self.error:
            lines.append(f"\n### Error\n```\n{self.error}\n```")
        return "\n".join(lines)


# ─────────────────────────────────────────────
# Scope Mapping — 도메인 → Mories Scope
# ─────────────────────────────────────────────

DEFAULT_SCOPE_MAP: Dict[str, str] = {
    # 팀 레벨 (tribal)
    "marketing": "tribal",
    "devops": "tribal",
    "engineering": "tribal",
    "content": "tribal",
    "sales": "tribal",
    # 조직 레벨 (social)
    "platform": "social",
    "security": "social",
    "compliance": "social",
    # 글로벌 (불변)
    "core": "global",
}


class MemoryBridge:
    """
    Harness → Mories 범용 메모리 브릿지.

    memory_backend 프로토콜:
        - ingest(content, salience, scope, source, metadata) → dict
        - record_pattern(domain, tool_chain, trigger, metadata) → dict
        - record_reflection(event, lesson, domain, severity) → dict

    이 인터페이스를 구현하는 백엔드는:
        1. MockMemoryBackend (테스트)
        2. MoriesApiBackend (실제 Mories REST API)
        3. MoriesMcpBackend (MCP 도구 호출)
        4. DirectNeo4jBackend (Neo4j 직접 연결)
    등 자유롭게 교체 가능.
    """

    def __init__(
        self,
        memory_backend=None,
        scope_map: Optional[Dict[str, str]] = None,
    ):
        self.backend = memory_backend
        self.scope_map = scope_map or DEFAULT_SCOPE_MAP

    def publish(self, experience: HarnessExperience) -> Dict[str, Any]:
        """
        경험을 유형에 따라 적절한 Mories 메모리 채널로 라우팅한다.

        Returns:
            {"status": "published", "actions": [...]}
        """
        actions = []
        scope = self.infer_scope(experience.domain)

        if experience.experience_type == ExperienceType.SUCCESS:
            actions.append(self._publish_success(experience, scope))

        elif experience.experience_type == ExperienceType.FAILURE:
            actions.append(self._publish_failure(experience, scope))

        elif experience.experience_type == ExperienceType.CAPTURED:
            actions.append(self._publish_captured(experience, scope))
            actions.append(self._publish_success(experience, scope))

        elif experience.experience_type == ExperienceType.HEALED:
            actions.append(self._publish_failure(experience, scope))
            actions.append(self._publish_success(experience, scope))

        elif experience.experience_type == ExperienceType.DERIVED:
            actions.append(self._publish_captured(experience, scope))

        elif experience.experience_type == ExperienceType.HUMAN_CORRECTED:
            actions.append(self._publish_human_feedback(experience, scope))

        logger.info(
            f"[MemoryBridge] Published {experience.experience_type.value} "
            f"for {experience.harness_id}: {len(actions)} actions"
        )

        return {"status": "published", "actions": actions}

    def infer_scope(self, domain: str) -> str:
        """도메인으로부터 Mories 메모리 scope를 추론한다."""
        return self.scope_map.get(domain, "personal")

    # ─────────────────────────────────────────
    # Private Publishing Methods
    # ─────────────────────────────────────────

    def _publish_success(
        self, exp: HarnessExperience, scope: str
    ) -> dict:
        """성공 경험을 LTM 후보(STM→auto-promote)로 저장."""
        content = exp.to_markdown()
        salience = self._calculate_salience(exp)

        result = self.backend.ingest(
            content=content,
            salience=salience,
            scope=scope,
            source=f"harness:{exp.harness_id}",
            metadata={
                "harness_id": exp.harness_id,
                "domain": exp.domain,
                "run_id": exp.run_id,
                "tool_chain": exp.tool_chain,
                "elapsed_ms": exp.elapsed_ms,
                "experience_type": exp.experience_type.value,
            },
        )
        return {"action": "ingest", "result": result}

    def _publish_failure(
        self, exp: HarnessExperience, scope: str
    ) -> dict:
        """실패 경험을 교훈(reflection)으로 기록."""
        severity = "high" if exp.elapsed_ms > 5000 else "medium"
        result = self.backend.record_reflection(
            event=f"Harness '{exp.harness_id}' failed: {exp.error or 'unknown'}",
            lesson=(
                f"Domain '{exp.domain}'의 '{exp.harness_id}' 실행 실패. "
                f"Tool chain: {' → '.join(exp.tool_chain)}. "
                f"향후 유사 시나리오에서 사전 검증 필요."
            ),
            domain=exp.domain,
            severity=severity,
        )
        return {"action": "reflection", "result": result}

    def _publish_captured(
        self, exp: HarnessExperience, scope: str
    ) -> dict:
        """새 패턴을 재사용 가능한 하네스 패턴으로 등록."""
        result = self.backend.record_pattern(
            domain=exp.domain,
            tool_chain=exp.tool_chain,
            trigger=f"Captured from {exp.harness_id} run {exp.run_id}",
            metadata={
                "source_harness": exp.harness_id,
                "elapsed_ms": exp.elapsed_ms,
                "scope": scope,
                "experience_type": exp.experience_type.value,
            },
        )
        return {"action": "pattern", "result": result}

    def _publish_human_feedback(
        self, exp: HarnessExperience, scope: str
    ) -> dict:
        """HITL 사람의 피드백을 영구적인 규칙(Instruction)으로 기억."""
        if hasattr(self.backend, "record_instruction"):
            result = self.backend.record_instruction(
                category="human_feedback",
                rule=exp.summary,
                description=f"Human feedback received during '{exp.harness_id}'. Original tool_chain: {' → '.join(exp.tool_chain)}",
                strictness="must"
            )
        else:
            # Fallback if record_instruction isn't strictly available (e.g., in some mock backends)
            result = {"status": "saved_as_mock_feedback", "rule": exp.summary}
        return {"action": "human_feedback", "result": result}

    def _calculate_salience(self, exp: HarnessExperience) -> float:
        """경험 유형과 실행 결과로부터 salience를 산출한다."""
        base = 0.5

        # 유형별 가중치
        type_boost = {
            ExperienceType.SUCCESS: 0.2,
            ExperienceType.CAPTURED: 0.3,
            ExperienceType.HEALED: 0.25,
            ExperienceType.DERIVED: 0.15,
            ExperienceType.HUMAN_CORRECTED: 0.4,
            ExperienceType.FAILURE: 0.0,
        }
        base += type_boost.get(exp.experience_type, 0)

        # 복잡도 보너스 (스텝 수)
        if len(exp.tool_chain) >= 5:
            base += 0.1
        elif len(exp.tool_chain) >= 3:
            base += 0.05

        return min(1.0, round(base, 2))
