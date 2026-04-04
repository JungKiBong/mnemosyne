# Harness v3 — Detailed Implementation Code

이 문서는 `2026-04-04-harness-v3-evolution-engine.md` 계획의 상세 코드를 포함합니다.

---

## Task 1: `metrics_store.py` 테스트 코드

```python
# tests/harness/test_metrics_store.py
import pytest
import os
import tempfile
from src.app.harness.metrics_store import MetricsStore, StepMetric, RunSummary

class TestMetricsStore:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.store = MetricsStore(db_path=os.path.join(self.tmp, "metrics.db"))

    def test_record_step_metric(self):
        metric = StepMetric(
            run_id="run_001", harness_id="marketing_churn",
            step_id="collect_crm", step_type="code",
            success=True, elapsed_ms=120,
        )
        self.store.record_step(metric)
        results = self.store.get_steps_by_run("run_001")
        assert len(results) == 1
        assert results[0]["step_id"] == "collect_crm"

    def test_record_run_summary(self):
        summary = RunSummary(
            run_id="run_001", harness_id="marketing_churn",
            domain="marketing", success=True,
            total_steps=5, elapsed_ms=850, total_cost_usd=0.003,
        )
        self.store.record_run(summary)
        result = self.store.get_run("run_001")
        assert result["success"] is True or result["success"] == 1
        assert result["total_cost_usd"] == 0.003

    def test_get_harness_stats(self):
        for i in range(3):
            self.store.record_run(RunSummary(
                run_id=f"run_{i}", harness_id="churn", domain="marketing",
                success=i != 1, total_steps=5, elapsed_ms=100 * (i + 1),
            ))
        stats = self.store.get_harness_stats("churn")
        assert stats["total_runs"] == 3
        assert stats["success_rate"] == pytest.approx(2/3, abs=0.01)
```

---

## Task 2: `evolution_engine.py` 테스트 코드

```python
# tests/harness/test_evolution_engine.py
import pytest
import os
import tempfile
from src.app.harness.evolution_engine import EvolutionEngine, EvolutionMode
from src.app.harness.metrics_store import MetricsStore, RunSummary

class TestEvolutionEngine:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.metrics = MetricsStore(db_path=os.path.join(self.tmp, "m.db"))
        self.engine = EvolutionEngine(metrics_store=self.metrics)

    def test_classify_fix(self):
        mode = self.engine.classify_evolution(
            harness_id="churn", run_success=False,
            error_msg="TypeError in collect_crm",
        )
        assert mode == EvolutionMode.FIX

    def test_classify_captured(self):
        mode = self.engine.classify_evolution(
            harness_id="new", run_success=True, is_new_pattern=True,
        )
        assert mode == EvolutionMode.CAPTURED

    def test_classify_derived(self):
        mode = self.engine.classify_evolution(
            harness_id="churn", run_success=True, fork_to_domain="finance",
        )
        assert mode == EvolutionMode.DERIVED

    def test_classify_none(self):
        mode = self.engine.classify_evolution(harness_id="churn", run_success=True)
        assert mode is None

    def test_suggest_fix(self):
        rec = self.engine.suggest_fix("churn", "KeyError: 'count'", "predict")
        assert "recommendation" in rec
        assert rec["mode"] == "FIX"

    def test_derive(self):
        meta = self.engine.derive("marketing_churn", "finance", "금융 파생")
        assert meta["source"] == "marketing_churn"
        assert meta["mode"] == "DERIVED"

    def test_cascade_trigger(self):
        for i in range(4):
            self.metrics.record_run(RunSummary(
                run_id=f"r{i}", harness_id="churn", domain="mkt",
                success=i < 1, total_steps=3, elapsed_ms=100,
            ))
        assert self.engine.should_trigger_cascade("churn", threshold=0.5) is True
```

---

## Task 3: `execution_tree.py` 테스트 코드

```python
# tests/harness/test_execution_tree.py
import pytest
from src.app.harness.execution_tree import ExecutionTree

class TestExecutionTree:
    def test_add_run(self):
        tree = ExecutionTree()
        tree.add_run("marketing", "churn", "r1", [
            {"step_id": "s1", "type": "code", "success": True, "elapsed_ms": 50},
        ])
        assert tree.get_domain("marketing") is not None
        assert "churn" in tree.get_domain("marketing").children

    def test_summarize(self):
        tree = ExecutionTree()
        tree.add_run("mkt", "churn", "r1", [{"step_id": "s1", "type": "code", "success": True, "elapsed_ms": 100}])
        tree.add_run("mkt", "churn", "r2", [{"step_id": "s1", "type": "code", "success": False, "elapsed_ms": 50}])
        s = tree.summarize("mkt")
        assert s["total_runs"] == 2
        assert s["success_rate"] == 0.5

    def test_search(self):
        tree = ExecutionTree()
        tree.add_run("devops", "cicd", "r1", [
            {"step_id": "build", "type": "code", "success": False, "elapsed_ms": 200, "error": "TypeError in map"},
        ])
        results = tree.search("TypeError")
        assert len(results) >= 1

    def test_roundtrip(self):
        tree = ExecutionTree()
        tree.add_run("content", "blog", "r1", [{"step_id": "draft", "type": "code", "success": True, "elapsed_ms": 300}])
        data = tree.to_dict()
        tree2 = ExecutionTree.from_dict(data)
        assert tree2.get_domain("content") is not None
```

---

## Task 4: Runtime v3 통합 테스트

```python
# tests/harness/test_runtime_v3.py
import pytest
import tempfile
from src.app.harness.harness_runtime import HarnessRuntime

class TestRuntimeV3:
    def _simple_wf(self):
        return {
            "harness_id": "test_v3", "version": 3, "domain": "test",
            "steps": [
                {"id": "s1", "type": "wait", "timeout_seconds": 0},
                {"id": "done", "type": "end"},
            ],
            "state_storage": {"type": "json_file", "path": tempfile.mkdtemp()},
        }

    def test_metrics_summary_in_result(self):
        result = HarnessRuntime(self._simple_wf()).run()
        assert result["success"] is True
        assert "metrics_summary" in result

    def test_execution_tree_in_result(self):
        result = HarnessRuntime(self._simple_wf()).run()
        assert "execution_tree" in result

    def test_evolution_mode_on_failure(self):
        wf = {
            "harness_id": "fail_test", "version": 3, "domain": "test",
            "steps": [{"id": "bad", "type": "code", "action": "nonexistent.func"}],
            "state_storage": {"type": "json_file", "path": tempfile.mkdtemp()},
        }
        result = HarnessRuntime(wf).run()
        assert result["success"] is False
        assert result.get("evolution_mode") == "FIX"
```

---

## Task 4 Step 3: `harness_runtime.py` 수정 지침

**수정 위치 1:** `__init__` 메서드 끝 (line ~206 이후)
```python
        # ── v3: Evolution Engine + Metrics + Tree ──
        from src.app.harness.metrics_store import MetricsStore
        from src.app.harness.evolution_engine import EvolutionEngine
        from src.app.harness.execution_tree import ExecutionTree
        metrics_db = os.path.join(
            storage_cfg.get("path", "./harness_state"), "metrics.db"
        )
        self._metrics = MetricsStore(db_path=metrics_db)
        self._evolution = EvolutionEngine(metrics_store=self._metrics)
        self._exec_tree = ExecutionTree()
```

**수정 위치 2:** `_log_step` 메서드 (line ~443) — 기존 코드 유지 + 추가
```python
        # v3: record to metrics store
        from src.app.harness.metrics_store import StepMetric
        self._metrics.record_step(StepMetric(
            run_id=self.context["_meta"]["run_id"],
            harness_id=self.workflow.get("harness_id", "unknown"),
            step_id=step_id, step_type=step_type,
            success=success, elapsed_ms=int(elapsed * 1000), error=error,
        ))
```

**수정 위치 3:** `run()` 메서드 결과 반환 직전 (line ~284 이후)
```python
        # v3: execution tree + evolution classification
        from src.app.harness.metrics_store import RunSummary
        self._exec_tree.add_run(
            domain=self.workflow.get("domain", "unknown"),
            workflow=self.workflow.get("harness_id", "unknown"),
            run_id=run_id, steps=self._execution_log,
        )
        evo_mode = self._evolution.classify_evolution(
            harness_id=self.workflow.get("harness_id", "unknown"),
            run_success=success, error_msg=error_msg,
        )
        self._metrics.record_run(RunSummary(
            run_id=run_id,
            harness_id=self.workflow.get("harness_id", "unknown"),
            domain=self.workflow.get("domain", "unknown"),
            success=success, total_steps=len(self._execution_log),
            elapsed_ms=elapsed_ms,
            evolution_mode=evo_mode.value if evo_mode else None,
        ))
        result["metrics_summary"] = self._metrics.get_harness_stats(
            self.workflow.get("harness_id", "unknown"))
        result["execution_tree"] = self._exec_tree.to_dict()
        result["evolution_mode"] = evo_mode.value if evo_mode else None
```
