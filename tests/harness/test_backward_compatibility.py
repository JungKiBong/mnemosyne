"""
test_backward_compatibility.py — v3 하위 호환성 검증

기존 v2 워크플로우가 v3 런타임에서 정상 실행되고,
v3 결과 필드(metrics_summary, execution_tree, evolution_mode)가
새로 추가되는지 확인한다.
"""
import pytest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.harness_runtime import HarnessRuntime

WORKFLOW_DIR = os.path.join(
    os.path.dirname(__file__), "../../src/app/harness/workflows"
)


class TestBackwardCompatibility:
    def _load_and_exec(self, filename: str) -> dict:
        """기존 워크플로우를 v3 런타임으로 실행한다."""
        path = os.path.join(WORKFLOW_DIR, filename)
        if not os.path.exists(path):
            pytest.skip(f"Workflow file not found: {filename}")
        with open(path) as f:
            wf = json.load(f)
        # 임시 디렉토리로 state_storage 리다이렉트
        wf.setdefault("state_storage", {})["path"] = tempfile.mkdtemp()
        return HarnessRuntime(wf).run()

    def test_marketing_churn_v3_fields(self):
        """marketing_churn: v3 필드가 결과에 추가된다."""
        result = self._load_and_exec("marketing_churn.json")
        assert "metrics_summary" in result
        assert "execution_tree" in result
        assert "evolution_mode" in result

    def test_content_creation_v3_fields(self):
        """content_creation: v3 필드가 결과에 추가된다."""
        result = self._load_and_exec("content_creation.json")
        assert "metrics_summary" in result
        assert "execution_tree" in result

    def test_cicd_auto_recovery_v3_fields(self):
        """cicd_auto_recovery: v3 필드가 결과에 추가된다."""
        result = self._load_and_exec("cicd_auto_recovery.json")
        assert "metrics_summary" in result
        assert "execution_tree" in result

    def test_v2_result_fields_preserved(self):
        """기존 v2 결과 필드가 모두 보존된다."""
        result = self._load_and_exec("marketing_churn.json")
        v2_keys = {"run_id", "harness_id", "domain", "success",
                    "error", "elapsed_ms", "steps_executed",
                    "execution_log", "final_context_keys"}
        for key in v2_keys:
            assert key in result, f"Missing v2 field: {key}"
