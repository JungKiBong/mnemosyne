"""
test_memory_bridge.py

Harness ↔ Mories 범용 메모리 브릿지 테스트.
하네스 실행 결과(성공/실패/진화)가 Mories 인지 메모리 파이프라인으로
올바르게 변환되어 저장되는지 검증한다.
"""
import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.orchestration.memory_bridge import (
    MemoryBridge,
    HarnessExperience,
    ExperienceType,
)


class MockMemoryBackend:
    """테스트용 Mories 메모리 백엔드 Mock."""

    def __init__(self):
        self.ingested: list = []
        self.patterns_recorded: list = []
        self.reflections: list = []

    def ingest(self, content: str, salience: float, scope: str,
               source: str, metadata: dict):
        self.ingested.append({
            "content": content, "salience": salience,
            "scope": scope, "source": source, "metadata": metadata,
        })
        return {"status": "ingested", "id": f"mock_{len(self.ingested)}"}

    def record_pattern(self, domain: str, tool_chain: list,
                       trigger: str, metadata: dict):
        self.patterns_recorded.append({
            "domain": domain, "tool_chain": tool_chain,
            "trigger": trigger, "metadata": metadata,
        })
        return {"status": "recorded", "id": f"pat_{len(self.patterns_recorded)}"}

    def record_reflection(self, event: str, lesson: str,
                          domain: str, severity: str):
        self.reflections.append({
            "event": event, "lesson": lesson,
            "domain": domain, "severity": severity,
        })
        return {"status": "recorded"}


class TestMemoryBridge:
    def setup_method(self):
        self.backend = MockMemoryBackend()
        self.bridge = MemoryBridge(memory_backend=self.backend)

    def test_publish_success_experience(self):
        """성공 경험은 높은 salience로 Mories에 저장된다."""
        exp = HarnessExperience(
            harness_id="marketing_churn",
            domain="marketing",
            run_id="run_001",
            experience_type=ExperienceType.SUCCESS,
            tool_chain=["collect_crm", "predict_churn", "alert_team"],
            elapsed_ms=850,
            summary="마케팅 이탈 예측 파이프라인 성공",
        )
        result = self.bridge.publish(exp)
        assert result["status"] == "published"
        assert len(self.backend.ingested) == 1
        assert self.backend.ingested[0]["salience"] >= 0.7

    def test_publish_failure_creates_reflection(self):
        """실패 경험은 reflection(교훈)으로 Mories에 기록된다."""
        exp = HarnessExperience(
            harness_id="cicd_recovery",
            domain="devops",
            run_id="run_002",
            experience_type=ExperienceType.FAILURE,
            tool_chain=["build", "test"],
            elapsed_ms=120,
            error="TypeError in test step",
            summary="CI/CD 복구 실패",
        )
        result = self.bridge.publish(exp)
        assert result["status"] == "published"
        assert len(self.backend.reflections) == 1
        assert "TypeError" in self.backend.reflections[0]["event"]

    def test_publish_captured_records_pattern(self):
        """CAPTURED 경험은 재사용 가능한 패턴으로 기록된다."""
        exp = HarnessExperience(
            harness_id="content_blog",
            domain="content",
            run_id="run_003",
            experience_type=ExperienceType.CAPTURED,
            tool_chain=["draft", "review", "publish"],
            elapsed_ms=500,
            summary="블로그 자동 생성 패턴 포착",
        )
        result = self.bridge.publish(exp)
        assert result["status"] == "published"
        assert len(self.backend.patterns_recorded) == 1
        pat = self.backend.patterns_recorded[0]
        assert pat["domain"] == "content"
        assert pat["tool_chain"] == ["draft", "review", "publish"]

    def test_publish_healed_records_both(self):
        """HEALED 경험은 교훈 + 성공 패턴 모두 기록된다."""
        exp = HarnessExperience(
            harness_id="auto_fix_test",
            domain="test",
            run_id="run_004",
            experience_type=ExperienceType.HEALED,
            tool_chain=["step_a", "step_b_fixed"],
            elapsed_ms=300,
            error="Original: KeyError",
            summary="LLM이 KeyError를 수정하여 성공",
        )
        result = self.bridge.publish(exp)
        assert result["status"] == "published"
        # 교훈(원래 에러)과 성공 경험 모두 기록
        assert len(self.backend.reflections) == 1
        assert len(self.backend.ingested) == 1

    def test_experience_to_markdown(self):
        """경험 데이터가 마크다운으로 변환된다."""
        exp = HarnessExperience(
            harness_id="test_md",
            domain="test",
            run_id="run_005",
            experience_type=ExperienceType.SUCCESS,
            tool_chain=["a", "b"],
            elapsed_ms=100,
            summary="테스트 요약",
        )
        md = exp.to_markdown()
        assert "## Harness Experience" in md
        assert "test_md" in md
        assert "SUCCESS" in md

    def test_scope_inference(self):
        """도메인으로부터 적절한 Mories scope를 추론한다."""
        assert self.bridge.infer_scope("marketing") == "tribal"
        assert self.bridge.infer_scope("devops") == "tribal"
        assert self.bridge.infer_scope("test") == "personal"
        assert self.bridge.infer_scope("platform") == "social"
