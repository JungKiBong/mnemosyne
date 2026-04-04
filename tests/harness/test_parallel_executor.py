"""Tests for ParallelExecutor — true concurrent branch execution."""
import time
import pytest
from unittest.mock import MagicMock

from src.app.harness.executors.parallel_executor import (
    ParallelExecutor,
    JoinStrategy,
)
from src.app.harness.executors import ExecutorResult


# ── Fixtures ─────────────────────────────────
@pytest.fixture
def dummy_context():
    return {"env": {}, "_meta": {"run_id": "par-001"}}


def _make_step_executor(delay_map=None, fail_ids=None):
    """Create a mock step executor that optionally delays and/or fails."""
    delay_map = delay_map or {}
    fail_ids = fail_ids or set()

    def executor_fn(step, context):
        bid = step["id"]
        delay = delay_map.get(bid, 0)
        if delay:
            time.sleep(delay)
        if bid in fail_ids:
            raise RuntimeError(f"Branch {bid} failed")
        return {"branch": bid, "result": "ok"}

    return executor_fn


# ── Test: wait_all ───────────────────────────
class TestParallelWaitAll:

    def test_all_branches_succeed(self, dummy_context):
        executor = ParallelExecutor(
            step_executor_fn=_make_step_executor(), max_workers=3
        )
        step = {
            "id": "parallel_1",
            "type": "parallel",
            "branches": ["a", "b", "c"],
            "_resolved_branches": [
                {"id": "a", "type": "code"},
                {"id": "b", "type": "code"},
                {"id": "c", "type": "code"},
            ],
            "join_strategy": "wait_all",
        }
        result = executor.execute(step, dummy_context)
        assert result.success is True
        assert "a" in result.output
        assert "b" in result.output
        assert "c" in result.output
        assert result.metadata["branches"] == 3

    def test_one_branch_fails(self, dummy_context):
        executor = ParallelExecutor(
            step_executor_fn=_make_step_executor(fail_ids={"b"}),
            max_workers=3,
        )
        step = {
            "id": "parallel_2",
            "type": "parallel",
            "branches": ["a", "b"],
            "_resolved_branches": [
                {"id": "a", "type": "code"},
                {"id": "b", "type": "code"},
            ],
            "join_strategy": "wait_all",
        }
        result = executor.execute(step, dummy_context)
        assert result.success is False
        assert "b" in result.error
        assert "a" in result.output  # a still succeeded

    def test_truly_parallel_faster_than_serial(self, dummy_context):
        """3 branches each sleeping 0.1s should finish in <0.25s if parallel."""
        executor = ParallelExecutor(
            step_executor_fn=_make_step_executor(
                delay_map={"x": 0.1, "y": 0.1, "z": 0.1}
            ),
            max_workers=3,
        )
        step = {
            "id": "speed_test",
            "type": "parallel",
            "branches": ["x", "y", "z"],
            "_resolved_branches": [
                {"id": "x", "type": "code"},
                {"id": "y", "type": "code"},
                {"id": "z", "type": "code"},
            ],
        }
        start = time.time()
        result = executor.execute(step, dummy_context)
        elapsed = time.time() - start

        assert result.success is True
        # Sequential would take ≥0.3s. Parallel should be ~0.1s.
        assert elapsed < 0.25, f"Expected <0.25s, got {elapsed:.3f}s"


# ── Test: first_success ─────────────────────
class TestParallelFirstSuccess:

    def test_first_success_returns_early(self, dummy_context):
        """Fast branch returns immediately, slow branches are cancelled."""
        executor = ParallelExecutor(
            step_executor_fn=_make_step_executor(
                delay_map={"fast": 0, "slow": 0.5}
            ),
            max_workers=2,
        )
        step = {
            "id": "first_1",
            "type": "parallel",
            "branches": ["fast", "slow"],
            "_resolved_branches": [
                {"id": "fast", "type": "code"},
                {"id": "slow", "type": "code"},
            ],
            "join_strategy": "first_success",
        }
        start = time.time()
        result = executor.execute(step, dummy_context)
        elapsed = time.time() - start

        assert result.success is True
        assert "fast" in result.output
        # Should return well before slow finishes (0.5s)
        assert elapsed < 0.4


# ── Edge cases ──────────────────────────────
class TestParallelEdgeCases:

    def test_no_branches(self, dummy_context):
        executor = ParallelExecutor(step_executor_fn=_make_step_executor())
        step = {"id": "empty", "type": "parallel", "branches": []}
        result = executor.execute(step, dummy_context)
        assert result.success is True
        assert result.metadata["branches"] == 0

    def test_no_executor_fn(self, dummy_context):
        executor = ParallelExecutor()  # no fn
        step = {
            "id": "no_fn",
            "type": "parallel",
            "_resolved_branches": [{"id": "a", "type": "code"}],
        }
        result = executor.execute(step, dummy_context)
        assert result.success is False
        assert "no step_executor_fn" in result.error
