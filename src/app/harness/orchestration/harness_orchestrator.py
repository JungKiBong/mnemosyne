"""
harness_orchestrator.py — 범용 Harness Lifecycle Orchestrator

Mories 생태계의 범용 확장.
어떤 도메인의 워크플로우든 실행하고, 결과(경험)를
Mories 인지 메모리 파이프라인으로 자동 퍼블리싱한다.

핵심 루프:
  Execute → Classify → (Auto-Heal if FIX) → Publish Experience → Repeat

작성: 2026-04-04
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Protocol

from src.app.harness.harness_runtime import HarnessRuntime
from src.app.harness.evolution_engine import EvolutionMode
from src.app.harness.orchestration.memory_bridge import (
    MemoryBridge,
    HarnessExperience,
    ExperienceType,
)

logger = logging.getLogger("harness_orchestrator")


class LLMHealer(Protocol):
    """LLM 기반 워크플로우 자동 복구 프로토콜."""
    def heal_workflow(
        self, workflow: dict, error_msg: str, failed_step_id: str
    ) -> dict: ...


class HarnessOrchestrator:
    """
    범용 Harness Lifecycle Orchestrator.

    Plugins:
        - llm_healer: 워크플로우 자동 복구 (DI)
        - memory_bridge: Mories 메모리 연동 (DI)
    """

    def __init__(
        self,
        initial_workflow: dict,
        llm_healer: Optional[Any] = None,
        memory_bridge: Optional[MemoryBridge] = None,
    ):
        self.workflow = initial_workflow
        self.llm_healer = llm_healer
        self.memory_bridge = memory_bridge or MemoryBridge()
        self.heal_attempts = 0
        self.captured_patterns: list = []

    def run_with_auto_heal(
        self, max_retries: int = 1
    ) -> Dict[str, Any]:
        """
        워크플로우를 실행한다.
        FIX 시 Auto-Heal, 성공 시 Experience 퍼블리싱.
        """
        current_workflow = self.workflow
        evolution_config = current_workflow.get("evolution", {})
        auto_fix_enabled = evolution_config.get("auto_fix", False)

        runtime_result = None
        original_error = None

        for attempt in range(max_retries + 1):
            runtime = HarnessRuntime(current_workflow)
            runtime_result = runtime.run()

            if runtime_result.get("success"):
                # 성공 경험 유형 결정
                if self.heal_attempts > 0:
                    exp_type = ExperienceType.HEALED
                elif evolution_config.get("capture_new_patterns", True):
                    exp_type = ExperienceType.CAPTURED
                else:
                    exp_type = ExperienceType.SUCCESS

                # Mories에 경험 퍼블리싱
                experience = HarnessExperience(
                    harness_id=current_workflow.get(
                        "harness_id", "unknown"
                    ),
                    domain=current_workflow.get("domain", "unknown"),
                    run_id=runtime_result.get("run_id", ""),
                    experience_type=exp_type,
                    tool_chain=[
                        s["step_id"]
                        for s in runtime_result.get("execution_log", [])
                        if s.get("success")
                    ],
                    elapsed_ms=runtime_result.get("elapsed_ms", 0),
                    error=original_error,
                    summary=(
                        f"{'Auto-healed and succeeded' if self.heal_attempts > 0 else 'Succeeded'}"
                        f" in {runtime_result.get('elapsed_ms', 0)}ms"
                    ),
                )

                if self.memory_bridge.backend is not None:
                    self.memory_bridge.publish(experience)

                # 패턴 캡처 (레거시 호환)
                self.captured_patterns.append({
                    "harness_id": experience.harness_id,
                    "domain": experience.domain,
                    "tool_chain": experience.tool_chain,
                })

                runtime_result.setdefault("metadata", {})
                runtime_result["metadata"]["auto_healed"] = (
                    self.heal_attempts > 0
                )
                runtime_result["metadata"]["experience_type"] = (
                    exp_type.value
                )
                return runtime_result

            # 실패 처리
            evo_mode = runtime_result.get("evolution_mode")
            original_error = runtime_result.get("error", "")

            if (
                evo_mode == EvolutionMode.FIX.value
                and auto_fix_enabled
                and self.llm_healer
                and attempt < max_retries
            ):
                self.heal_attempts += 1
                logger.info(
                    f"Auto-Healing attempt "
                    f"{self.heal_attempts}/{max_retries}"
                )

                failed_logs = [
                    s
                    for s in runtime_result.get("execution_log", [])
                    if not s.get("success")
                ]
                failed_step = (
                    failed_logs[-1]["step_id"]
                    if failed_logs
                    else "unknown"
                )

                current_workflow = self.llm_healer.heal_workflow(
                    workflow=current_workflow,
                    error_msg=original_error,
                    failed_step_id=failed_step,
                )
            else:
                break

        # 최종 실패 → Mories에 실패 경험 기록
        experience = HarnessExperience(
            harness_id=current_workflow.get("harness_id", "unknown"),
            domain=current_workflow.get("domain", "unknown"),
            run_id=runtime_result.get("run_id", ""),
            experience_type=ExperienceType.FAILURE,
            tool_chain=[
                s["step_id"]
                for s in runtime_result.get("execution_log", [])
            ],
            elapsed_ms=runtime_result.get("elapsed_ms", 0),
            error=runtime_result.get("error", ""),
            summary=(
                f"Failed after {self.heal_attempts} heal attempts: "
                f"{runtime_result.get('error', 'unknown')}"
            ),
        )

        if self.memory_bridge.backend is not None:
            self.memory_bridge.publish(experience)

        # Failure webhook notification
        self._notify_failure_webhook(
            harness_id=current_workflow.get("harness_id", "unknown"),
            error=runtime_result.get("error", ""),
            run_id=runtime_result.get("run_id", ""),
        )

        runtime_result.setdefault("metadata", {})
        runtime_result["metadata"]["auto_healed"] = False
        return runtime_result

    def _notify_failure_webhook(
        self, harness_id: str, error: str, run_id: str
    ) -> None:
        """Send failure alert to configured webhook endpoint."""
        webhook_url = self.workflow.get("config", {}).get("monitoring", {}).get(
            "webhook_on_failure"
        )
        if not webhook_url:
            return
        try:
            import requests as _requests
            _requests.post(webhook_url, json={
                "event": "harness_failure",
                "harness_id": harness_id,
                "run_id": run_id,
                "error": error[:500],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, timeout=5)
            logger.info(f"Failure webhook sent to {webhook_url}")
        except Exception as e:
            logger.warning(f"Failure webhook failed: {e}")

    # Legacy alias
    def _sync_to_mories_ltm(self, pattern_data: dict):
        self.captured_patterns.append(pattern_data)
