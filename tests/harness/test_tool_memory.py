"""Tests for ToolMemoryIndex — per-tool execution statistics."""
import os
import tempfile
import pytest

from src.app.harness.memory.tool_memory_index import (
    ToolMemoryIndex,
    ToolExecution,
    ToolMemoryRecord,
)


@pytest.fixture
def tmi():
    """Create a ToolMemoryIndex with a temp database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    index = ToolMemoryIndex(db_path=path)
    yield index
    index.close()
    os.unlink(path)


# ── Recording ────────────────────────────────
class TestToolRecording:

    def test_record_single(self, tmi):
        tmi.record(ToolExecution(
            tool_name="docker_python",
            tool_type="container_exec",
            success=True,
            elapsed_ms=150,
            domain="engineering",
        ))
        stats = tmi.get_tool_stats("docker_python")
        assert stats is not None
        assert stats.total_executions == 1
        assert stats.success_count == 1
        assert stats.success_rate == 1.0

    def test_record_multiple(self, tmi):
        for i in range(5):
            tmi.record(ToolExecution(
                tool_name="api_service",
                tool_type="api_call",
                success=(i != 2),  # 1 failure at index 2
                elapsed_ms=100 + i * 10,
                domain="data_science",
                error="timeout" if i == 2 else None,
            ))
        stats = tmi.get_tool_stats("api_service")
        assert stats.total_executions == 5
        assert stats.success_count == 4
        assert stats.fail_count == 1
        assert stats.success_rate == 0.8
        assert stats.last_error == "timeout"

    def test_cost_tracking(self, tmi):
        tmi.record(ToolExecution(
            tool_name="gpt4_call",
            tool_type="api_call",
            success=True,
            elapsed_ms=500,
            cost_usd=0.03,
        ))
        tmi.record(ToolExecution(
            tool_name="gpt4_call",
            tool_type="api_call",
            success=True,
            elapsed_ms=450,
            cost_usd=0.02,
        ))
        stats = tmi.get_tool_stats("gpt4_call")
        assert stats.total_cost_usd == pytest.approx(0.05)


# ── Queries ──────────────────────────────────
class TestToolQueries:

    def test_get_all_stats(self, tmi):
        tmi.record(ToolExecution("tool_a", "code", True, 100))
        tmi.record(ToolExecution("tool_b", "api_call", True, 200))
        all_stats = tmi.get_all_stats()
        assert len(all_stats) == 2
        names = [s.tool_name for s in all_stats]
        assert "tool_a" in names
        assert "tool_b" in names

    def test_nonexistent_tool(self, tmi):
        assert tmi.get_tool_stats("ghost") is None

    def test_domains_tracked(self, tmi):
        tmi.record(ToolExecution("multi_tool", "code", True, 50, domain="eng"))
        tmi.record(ToolExecution("multi_tool", "code", True, 60, domain="ops"))
        tmi.record(ToolExecution("multi_tool", "code", True, 70, domain="eng"))
        stats = tmi.get_tool_stats("multi_tool")
        assert set(stats.domains_used) == {"eng", "ops"}


# ── Reliability ──────────────────────────────
class TestReliabilityRanking:

    def test_ranking_order(self, tmi):
        # Tool A: 100% success, 10 runs
        for _ in range(10):
            tmi.record(ToolExecution("reliable_tool", "code", True, 50))
        # Tool B: 50% success, 10 runs
        for i in range(10):
            tmi.record(ToolExecution("flaky_tool", "code", i % 2 == 0, 100))

        ranking = tmi.get_reliability_ranking(min_executions=3)
        assert len(ranking) == 2
        assert ranking[0].tool_name == "reliable_tool"
        assert ranking[1].tool_name == "flaky_tool"

    def test_min_executions_filter(self, tmi):
        tmi.record(ToolExecution("rare_tool", "code", True, 50))
        ranking = tmi.get_reliability_ranking(min_executions=3)
        assert len(ranking) == 0  # filtered out

    def test_best_tool_for_type(self, tmi):
        for _ in range(5):
            tmi.record(ToolExecution("fast_api", "api_call", True, 50))
        for _ in range(5):
            tmi.record(ToolExecution("slow_api", "api_call", True, 500))
        for i in range(5):
            tmi.record(ToolExecution("buggy_api", "api_call", i > 2, 100))

        best = tmi.get_best_tool_for_type("api_call", min_executions=3)
        assert best is not None
        # fast_api and slow_api both 100% — both valid
        assert best.success_rate >= 0.8


# ── ToolMemoryRecord properties ──────────────
class TestToolMemoryRecord:

    def test_reliability_with_zero_executions(self):
        r = ToolMemoryRecord(tool_name="t", tool_type="x")
        assert r.reliability_score == 0.0
        assert r.success_rate == 0.0

    def test_reliability_calculation(self):
        r = ToolMemoryRecord(
            tool_name="t", tool_type="x",
            total_executions=20, success_count=18, fail_count=2,
        )
        assert r.success_rate == 0.9
        assert r.reliability_score > 0.8

    def test_low_volume_penalty(self):
        """Few executions should lower reliability even with 100% success."""
        low = ToolMemoryRecord("t", "x", total_executions=1, success_count=1)
        high = ToolMemoryRecord("t", "x", total_executions=50, success_count=50)
        assert high.reliability_score > low.reliability_score
