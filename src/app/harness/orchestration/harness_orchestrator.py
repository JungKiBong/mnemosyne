"""
harness_orchestrator.py

HarnessRuntime 위에서 작동하는 Ochestrator.
1. Auto-Healing: 실행 실패(Evolution: FIX) 시 LLM Healer를 호출하여 DSL 수정 후 재시도
2. Mories Graph Sync: 성공(Evolution: CAPTURED) 시 추출된 패턴을 Mories LTM(Neo4j)에 기록

작성: 2026-04-04
"""
import logging
from typing import Dict, Any, Optional

from src.app.harness.harness_runtime import HarnessRuntime
from src.app.harness.evolution_engine import EvolutionMode

logger = logging.getLogger("harness_orchestrator")


class HarnessOrchestrator:
    def __init__(self, initial_workflow: dict, llm_healer: Optional[Any] = None):
        self.workflow = initial_workflow
        self.llm_healer = llm_healer
        self.heal_attempts = 0
        self.captured_patterns = []

    def run_with_auto_heal(self, max_retries: int = 1) -> Dict[str, Any]:
        """
        워크플로우를 실행한다. 에러 발생 및 FIX 분류 시 자동 복구를 시도한다.
        성공 후 새 패턴이면 Mories LTM에 저장한다.
        """
        current_workflow = self.workflow
        evolution_config = current_workflow.get("evolution", {})
        auto_fix_enabled = evolution_config.get("auto_fix", False)
        
        runtime_result = None
        
        for attempt in range(max_retries + 1):
            runtime = HarnessRuntime(current_workflow)
            runtime_result = runtime.run()
            
            # 성공 시
            if runtime_result.get("success"):
                # 항상 새 패턴이라고 임시로 간주 (데모 시뮬레이션용)
                # 실제로는 Evolution Engine이 "CAPTURED"를 뱉거나 우리가 수동트리거
                if getattr(self, "_trigger_capture", True) and evolution_config.get("capture_new_patterns", True):
                    pattern_data = {
                        "harness_id": current_workflow.get("harness_id"),
                        "domain": current_workflow.get("domain"),
                        "tool_chain": [s["step_id"] for s in runtime_result["execution_log"] if s["success"]]
                    }
                    self._sync_to_mories_ltm(pattern_data)
                
                runtime_result.setdefault("metadata", {})
                runtime_result["metadata"]["auto_healed"] = (self.heal_attempts > 0)
                return runtime_result

            # 실패 시 FIX 모드 확인
            evo_mode = runtime_result.get("evolution_mode")
            if evo_mode == EvolutionMode.FIX.value and auto_fix_enabled and self.llm_healer:
                if attempt < max_retries:
                    self.heal_attempts += 1
                    logger.info(f"Auto-Healing attempt {self.heal_attempts}/{max_retries}")
                    
                    # 로그 추적해서 실패한 step 가져오기
                    failed_logs = [s for s in runtime_result["execution_log"] if not s["success"]]
                    failed_step = failed_logs[-1]["step_id"] if failed_logs else "unknown"
                    error_msg = runtime_result.get("error", "")
                    
                    # LLM 기반 워크플로우 동적 패치
                    current_workflow = self.llm_healer.heal_workflow(
                        workflow=current_workflow,
                        error_msg=error_msg,
                        failed_step_id=failed_step
                    )
                else:
                    logger.error("Max retries exceeded for Auto-Healing.")
            else:
                # FIX 불가하거나 힐러가 없으면 그냥 반복분쇄
                break
                
        runtime_result.setdefault("metadata", {})
        runtime_result["metadata"]["auto_healed"] = False
        return runtime_result
        
    def _sync_to_mories_ltm(self, pattern_data: dict):
        """
        [Mories MCP Target]
        실제로 MCP 'mories_harness_record' 를 호출하는 어댑터 역할.
        성공한 툴체인을 지식그래프에 퍼블리시한다.
        """
        logger.info(f"Syncing captured pattern to Mories LTM: {pattern_data['harness_id']}")
        self.captured_patterns.append(pattern_data)
        
        # 여기서 실제 Mories API 서버 (100.75.95.45:?) 나 내부 Graph DB를 찔러서 영구기록.
        # 이번 스텝에서는 구조적 연동까지만 구현.
