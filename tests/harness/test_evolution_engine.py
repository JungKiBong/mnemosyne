"""
test_evolution_engine.py — 3-Mode Evolution Engine 단위 테스트

FIX/DERIVED/CAPTURED 분류, 수정 추천, 파생, cascade 트리거를 검증한다.
"""
import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.evolution_engine import EvolutionEngine, EvolutionMode
from src.app.harness.metrics_store import MetricsStore, RunSummary


class TestEvolutionEngine:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.metrics = MetricsStore(db_path=os.path.join(self.tmp, "m.db"))
        self.engine = EvolutionEngine(metrics_store=self.metrics)

    def test_classify_fix_mode(self):
        """실패한 실행 → FIX 모드 분류."""
        mode = self.engine.classify_evolution(
            harness_id="churn", run_success=False,
            error_msg="TypeError in step collect_crm",
        )
        assert mode == EvolutionMode.FIX

    def test_classify_captured_mode(self):
        """새로운 성공 패턴 → CAPTURED 모드 분류."""
        mode = self.engine.classify_evolution(
            harness_id="new_pattern", run_success=True,
            is_new_pattern=True,
        )
        assert mode == EvolutionMode.CAPTURED

    def test_classify_derived_mode(self):
        """유사 도메인 포크 → DERIVED 모드 분류."""
        mode = self.engine.classify_evolution(
            harness_id="churn", run_success=True,
            fork_to_domain="finance",
        )
        assert mode == EvolutionMode.DERIVED

    def test_classify_none_on_normal_success(self):
        """정상 성공 → 진화 불필요 (None)."""
        mode = self.engine.classify_evolution(
            harness_id="churn", run_success=True,
        )
        assert mode is None

    def test_suggest_fix_returns_recommendation(self):
        """FIX 모드에서 추천을 반환한다."""
        rec = self.engine.suggest_fix(
            harness_id="churn",
            error_msg="KeyError: 'customer_count'",
            failed_step_id="predict_churn",
        )
        assert "recommendation" in rec
        assert rec["mode"] == "FIX"
        assert "predict_churn" in rec["recommendation"]

    def test_derive_creates_fork_metadata(self):
        """DERIVED 모드에서 포크 메타데이터를 생성한다."""
        meta = self.engine.derive(
            source_harness_id="marketing_churn",
            target_domain="finance",
            description="금융 고객 이탈 예측으로 파생",
        )
        assert meta["source"] == "marketing_churn"
        assert meta["target_domain"] == "finance"
        assert meta["mode"] == "DERIVED"

    def test_capture_extracts_pattern(self):
        """CAPTURED 모드에서 성공 실행 로그로부터 패턴을 추출한다."""
        log = [
            {"step_id": "s1", "success": True},
            {"step_id": "s2", "success": True},
            {"step_id": "s3", "success": False},
        ]
        pattern = self.engine.capture(log, domain="test")
        assert pattern["mode"] == "CAPTURED"
        assert pattern["tool_chain"] == ["s1", "s2"]  # 성공한 것만

    def test_should_trigger_cascade(self):
        """성공률 50% 미만 시 cascade 트리거."""
        for i in range(4):
            self.metrics.record_run(RunSummary(
                run_id=f"r{i}", harness_id="churn", domain="mkt",
                success=i < 1,  # r0만 성공, r1~r3 실패
                total_steps=3, elapsed_ms=100,
            ))
        assert self.engine.should_trigger_cascade("churn", threshold=0.5) is True

    def test_no_cascade_when_above_threshold(self):
        """성공률이 임계값 이상이면 cascade 미발생."""
        for i in range(4):
            self.metrics.record_run(RunSummary(
                run_id=f"r{i}", harness_id="good", domain="mkt",
                success=True, total_steps=3, elapsed_ms=100,
            ))
        assert self.engine.should_trigger_cascade("good", threshold=0.5) is False
