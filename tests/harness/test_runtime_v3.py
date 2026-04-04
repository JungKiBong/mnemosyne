"""
test_runtime_v3.py — Harness Runtime v3 통합 테스트

MetricsStore, EvolutionEngine, ExecutionTree가 런타임에 올바르게 통합되었는지 검증한다.
"""
import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.harness_runtime import HarnessRuntime


class TestRuntimeV3Integration:
    def _simple_workflow(self):
        return {
            "harness_id": "test_v3",
            "version": 3,
            "domain": "test",
            "steps": [
                {"id": "s1", "type": "wait", "timeout_seconds": 0},
                {"id": "done", "type": "end"},
            ],
            "state_storage": {
                "type": "json_file",
                "path": tempfile.mkdtemp(),
            },
        }

    def test_result_contains_metrics_summary(self):
        """실행 결과에 metrics_summary 필드가 포함된다."""
        result = HarnessRuntime(self._simple_workflow()).run()
        assert result["success"] is True
        assert "metrics_summary" in result
        assert result["metrics_summary"]["total_runs"] >= 1

    def test_result_contains_execution_tree(self):
        """실행 결과에 execution_tree 필드가 포함된다."""
        result = HarnessRuntime(self._simple_workflow()).run()
        assert "execution_tree" in result
        tree = result["execution_tree"]
        assert tree["level"] == "root"
        assert "test" in tree["children"]  # domain

    def test_evolution_mode_fix_on_failure(self):
        """실행 실패 시 evolution_mode가 FIX로 분류된다."""
        wf = {
            "harness_id": "fail_test",
            "version": 3,
            "domain": "test",
            "steps": [
                {
                    "id": "bad_step",
                    "type": "code",
                    "action": "nonexistent_module.nonexistent_func",
                },
            ],
            "state_storage": {
                "type": "json_file",
                "path": tempfile.mkdtemp(),
            },
        }
        result = HarnessRuntime(wf).run()
        assert result["success"] is False
        assert result.get("evolution_mode") == "FIX"

    def test_no_evolution_on_normal_success(self):
        """정상 성공 시 evolution_mode가 None이다."""
        result = HarnessRuntime(self._simple_workflow()).run()
        assert result["success"] is True
        assert result.get("evolution_mode") is None
