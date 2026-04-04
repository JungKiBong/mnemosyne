"""
evolution_engine.py — 3-Mode Self-Evolution Engine

OpenSpace의 FIX/DERIVED/CAPTURED 패턴을 Mories Harness에 적용.
실행 결과를 분석하여 진화 모드를 분류하고, 개선 추천을 생성한다.

- FIX:      실패한 하네스를 자동 수리
- DERIVED:  부모에서 특화 버전 파생
- CAPTURED: 성공 실행에서 새 패턴 포착

작성: 2026-04-04
"""
import logging
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger("evolution_engine")


class EvolutionMode(Enum):
    FIX = "FIX"
    DERIVED = "DERIVED"
    CAPTURED = "CAPTURED"


class EvolutionEngine:
    """3-Mode Self-Evolution Engine for Harness patterns."""

    def __init__(self, metrics_store=None):
        self.metrics = metrics_store

    def classify_evolution(
        self,
        harness_id: str,
        run_success: bool,
        error_msg: Optional[str] = None,
        is_new_pattern: bool = False,
        fork_to_domain: Optional[str] = None,
    ) -> Optional[EvolutionMode]:
        """
        실행 결과를 분석하여 진화 모드를 분류한다.

        Returns:
            EvolutionMode or None (진화 불필요)
        """
        # 1. FIX: 실행 실패 시
        if not run_success and error_msg:
            logger.info(
                f"[Evolution] FIX 분류: {harness_id} — {error_msg[:80]}"
            )
            return EvolutionMode.FIX

        # 2. DERIVED: 다른 도메인으로 포크 요청 시
        if fork_to_domain:
            logger.info(
                f"[Evolution] DERIVED 분류: {harness_id} → {fork_to_domain}"
            )
            return EvolutionMode.DERIVED

        # 3. CAPTURED: 새로운 성공 패턴 발견 시
        if run_success and is_new_pattern:
            logger.info(
                f"[Evolution] CAPTURED 분류: 새 패턴 — {harness_id}"
            )
            return EvolutionMode.CAPTURED

        # 정상 성공 → 진화 불필요
        return None

    def suggest_fix(
        self,
        harness_id: str,
        error_msg: str,
        failed_step_id: str,
    ) -> Dict[str, Any]:
        """FIX 모드: 실패 원인 분석 및 수정 추천 생성."""
        recommendation = self._analyze_error(error_msg, failed_step_id)
        return {
            "mode": "FIX",
            "harness_id": harness_id,
            "failed_step": failed_step_id,
            "error": error_msg,
            "recommendation": recommendation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def derive(
        self,
        source_harness_id: str,
        target_domain: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """DERIVED 모드: 기존 하네스에서 파생 버전 메타데이터 생성."""
        return {
            "mode": "DERIVED",
            "source": source_harness_id,
            "target_domain": target_domain,
            "description": description,
            "new_harness_id": f"{source_harness_id}__{target_domain}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def capture(
        self,
        execution_log: List[Dict],
        domain: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """CAPTURED 모드: 성공 실행 로그에서 새 패턴 추출."""
        tool_chain = [
            step["step_id"]
            for step in execution_log
            if step.get("success")
        ]
        return {
            "mode": "CAPTURED",
            "domain": domain,
            "tool_chain": tool_chain,
            "description": (
                description
                or f"Auto-captured from {len(tool_chain)} successful steps"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def should_trigger_cascade(
        self, harness_id: str, threshold: float = 0.5
    ) -> bool:
        """성공률이 threshold 미만이면 cascade evolution 트리거."""
        if not self.metrics:
            return False
        stats = self.metrics.get_harness_stats(harness_id)
        if stats["total_runs"] < 2:
            return False
        return stats["success_rate"] < threshold

    def _analyze_error(self, error_msg: str, step_id: str) -> str:
        """규칙 기반 에러 분석 (향후 LLM 연동 확장)."""
        lower = error_msg.lower()
        if "keyerror" in lower:
            return (
                f"Step '{step_id}'에서 KeyError 발생. "
                "params 매핑의 변수명을 확인하세요."
            )
        if "typeerror" in lower:
            return (
                f"Step '{step_id}'에서 TypeError 발생. "
                "입력 타입 불일치를 확인하세요."
            )
        if "timeout" in lower:
            return (
                f"Step '{step_id}'에서 Timeout. "
                "timeout_seconds 증가 또는 on_error=retry 설정을 권장합니다."
            )
        if "connection" in lower:
            return (
                f"Step '{step_id}'에서 연결 오류. "
                "URL 및 네트워크 상태를 확인하세요."
            )
        return (
            f"Step '{step_id}'에서 알 수 없는 오류: "
            f"{error_msg[:100]}. 로그를 확인하세요."
        )
