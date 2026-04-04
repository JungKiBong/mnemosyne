"""
test_metrics_store.py — MetricsStore 단위 테스트

SQLite 기반 실행 메트릭 저장소의 CRUD 및 통계 기능을 검증한다.
"""
import pytest
import os
import tempfile
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.metrics_store import MetricsStore, StepMetric, RunSummary


class TestMetricsStore:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.store = MetricsStore(db_path=os.path.join(self.tmp, "metrics.db"))

    def test_record_step_metric(self):
        """스텝 실행 메트릭을 기록하고 조회한다."""
        metric = StepMetric(
            run_id="run_001",
            harness_id="marketing_churn",
            step_id="collect_crm",
            step_type="code",
            success=True,
            elapsed_ms=120,
        )
        self.store.record_step(metric)
        results = self.store.get_steps_by_run("run_001")
        assert len(results) == 1
        assert results[0]["step_id"] == "collect_crm"
        assert results[0]["elapsed_ms"] == 120

    def test_record_run_summary(self):
        """런 요약을 기록하고 조회한다."""
        summary = RunSummary(
            run_id="run_001",
            harness_id="marketing_churn",
            domain="marketing",
            success=True,
            total_steps=5,
            elapsed_ms=850,
            total_cost_usd=0.003,
        )
        self.store.record_run(summary)
        result = self.store.get_run("run_001")
        assert result is not None
        assert result["total_cost_usd"] == 0.003
        assert result["harness_id"] == "marketing_churn"

    def test_get_harness_stats(self):
        """하네스별 통계(성공률, 평균시간, 총비용)를 계산한다."""
        for i in range(3):
            self.store.record_run(RunSummary(
                run_id=f"run_{i}",
                harness_id="churn",
                domain="marketing",
                success=i != 1,  # run_1만 실패
                total_steps=5,
                elapsed_ms=100 * (i + 1),
                total_cost_usd=0.001 * (i + 1),
            ))
        stats = self.store.get_harness_stats("churn")
        assert stats["total_runs"] == 3
        assert stats["success_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert stats["avg_elapsed_ms"] == 200  # (100+200+300)/3
        assert stats["total_cost_usd"] == pytest.approx(0.006, abs=0.0001)

    def test_empty_stats(self):
        """존재하지 않는 하네스의 통계는 빈 결과를 반환한다."""
        stats = self.store.get_harness_stats("nonexistent")
        assert stats["total_runs"] == 0
        assert stats["success_rate"] == 0.0
