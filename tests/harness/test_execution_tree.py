"""
test_execution_tree.py — Hierarchical Execution Tree 단위 테스트

Domain→Workflow→Run→Step 4-level 계층 구조의 추가/요약/검색/직렬화를 검증한다.
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.app.harness.execution_tree import ExecutionTree


class TestExecutionTree:
    def test_add_run_creates_hierarchy(self):
        """런 추가 시 Domain→Workflow→Run→Step 계층이 생성된다."""
        tree = ExecutionTree()
        tree.add_run("marketing", "churn_prediction", "run_001", [
            {"step_id": "collect_crm", "type": "code",
             "success": True, "elapsed_ms": 50},
            {"step_id": "predict_churn", "type": "code",
             "success": True, "elapsed_ms": 120},
        ])
        node = tree.get_domain("marketing")
        assert node is not None
        assert "churn_prediction" in node.children
        wf = node.children["churn_prediction"]
        assert "run_001" in wf.children
        run = wf.children["run_001"]
        assert len(run.children) == 2

    def test_summarize_domain(self):
        """도메인 요약 통계를 반환한다."""
        tree = ExecutionTree()
        tree.add_run("mkt", "churn", "r1", [
            {"step_id": "s1", "type": "code",
             "success": True, "elapsed_ms": 100},
        ])
        tree.add_run("mkt", "churn", "r2", [
            {"step_id": "s1", "type": "code",
             "success": False, "elapsed_ms": 50},
        ])
        summary = tree.summarize("mkt")
        assert summary["total_runs"] == 2
        assert summary["success_rate"] == 0.5

    def test_search_returns_matching_runs(self):
        """에러 메시지 기반으로 실행 기록을 검색한다."""
        tree = ExecutionTree()
        tree.add_run("devops", "cicd", "r1", [
            {"step_id": "build", "type": "code",
             "success": False, "elapsed_ms": 200,
             "error": "TypeError in map function"},
        ])
        tree.add_run("devops", "cicd", "r2", [
            {"step_id": "build", "type": "code",
             "success": True, "elapsed_ms": 100},
        ])
        results = tree.search("TypeError")
        assert len(results) == 1
        assert results[0]["run_id"] == "r1"

    def test_tree_to_dict_roundtrip(self):
        """JSON 직렬화/역직렬화 라운드트립이 정확하다."""
        tree = ExecutionTree()
        tree.add_run("content", "blog", "r1", [
            {"step_id": "draft", "type": "code",
             "success": True, "elapsed_ms": 300},
        ])
        data = tree.to_dict()
        tree2 = ExecutionTree.from_dict(data)
        assert tree2.get_domain("content") is not None
        wf = tree2.get_domain("content").children["blog"]
        assert "r1" in wf.children

    def test_nonexistent_domain_returns_none(self):
        """존재하지 않는 도메인 조회 시 None 반환."""
        tree = ExecutionTree()
        assert tree.get_domain("nonexistent") is None

    def test_summarize_empty_domain(self):
        """빈 도메인 요약은 0을 반환한다."""
        tree = ExecutionTree()
        summary = tree.summarize("empty")
        assert summary["total_runs"] == 0
