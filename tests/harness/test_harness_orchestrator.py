"""
test_harness_orchestrator.py

Harness Orchestrator의 Auto-Healing(자동복구) 루프와 Mories LTM 캡처 통합 로직 검증.
"""
import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.orchestration.harness_orchestrator import HarnessOrchestrator


class MockLLMHealer:
    """테스트용 LLM 자동복구 Mock. 에러를 분석하여 워크플로우를 수정한다."""
    def heal_workflow(self, workflow: dict, error_msg: str, failed_step_id: str) -> dict:
        import copy
        new_wf = copy.deepcopy(workflow)
        # 단순 테스트 목적: TypeError 수정 시뮬레이션
        if "nonexistent" in error_msg:
            for step in new_wf["steps"]:
                if step["id"] == failed_step_id:
                    # 잘못된 action을 정상 wait로 교체하여 "복구"를 시뮬레이션
                    step["type"] = "wait"
                    step["timeout_seconds"] = 0
                    if "action" in step:
                        del step["action"]
        return new_wf


class TestHarnessOrchestrator:
    def test_auto_healing_loop(self):
        """실패 시 FIX 모드가 감지되면 LLM 힐러가 개입하여 복구 및 재실행한다."""
        wf = {
            "harness_id": "auto_heal_test",
            "version": 3,
            "domain": "test",
            "steps": [
                {
                    "id": "bad_code_step",
                    "type": "code",
                    "action": "nonexistent_func"  # 의도적 에러 유발
                },
                {
                    "id": "done",
                    "type": "end"
                }
            ],
            "state_storage": {"type": "json_file", "path": tempfile.mkdtemp()},
            "evolution": {"auto_fix": True}
        }
        
        orchestrator = HarnessOrchestrator(
            initial_workflow=wf,
            llm_healer=MockLLMHealer()
        )
        
        # 실제 최대 1회 Auto Recovery 시도
        result = orchestrator.run_with_auto_heal(max_retries=1)
        
        # 첫 실행은 실패했으나, Orchestrator가 고치고 재실행해서 결국 성공해야 함
        assert result["success"] is True
        assert orchestrator.heal_attempts == 1
        assert "auto_healed" in result["metadata"]
        assert result["metadata"]["auto_healed"] is True

    def test_sync_captured_patterns_to_memory(self):
        """CAPTURED 진화 모드가 발생하면 Mories Graph에 저장됨을 시뮬레이타한다."""
        wf = {
            "harness_id": "capture_test",
            "version": 3,
            "domain": "marketing",
            "steps": [
                {"id": "s1", "type": "wait", "timeout_seconds": 0},
                {"id": "done", "type": "end"}
            ],
            "state_storage": {"type": "json_file", "path": tempfile.mkdtemp()},
            "evolution": {"capture_new_patterns": True}
        }
        
        orchestrator = HarnessOrchestrator(wf)
        # CAPTURED를 강제 트리거하기 위해 mock
        def mock_capture(p):
            orchestrator.captured_patterns.append(p)
            
        orchestrator._sync_to_mories_ltm = mock_capture
        
        result = orchestrator.run_with_auto_heal()
        assert result["success"] is True
        # 기본적으로 정상 실행 시, 새 패턴인 경우 CAPTURED가 됨
        assert len(orchestrator.captured_patterns) >= 1
