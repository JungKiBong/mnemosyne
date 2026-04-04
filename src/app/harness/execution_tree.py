"""
execution_tree.py — Hierarchical Execution Tree

CatchMe의 Hierarchical Activity Tree 패턴을 적용.
Domain → Workflow → Run → Step 4-level 계층으로 실행 이력을 조직한다.
LLM이 Top-Down으로 관련 실행 기록만 탐색할 수 있도록 설계.

작성: 2026-04-04
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger("execution_tree")


@dataclass
class TreeNode:
    """계층적 실행 트리의 노드."""
    name: str
    level: str  # root / domain / workflow / run / step
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: Dict[str, "TreeNode"] = field(default_factory=dict)
    summary: str = ""

    def add_child(self, key: str, node: "TreeNode"):
        self.children[key] = node

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "level": self.level,
            "metadata": self.metadata,
            "summary": self.summary,
            "children": {k: v.to_dict() for k, v in self.children.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TreeNode":
        node = cls(
            name=data["name"],
            level=data["level"],
            metadata=data.get("metadata", {}),
            summary=data.get("summary", ""),
        )
        for k, v in data.get("children", {}).items():
            node.children[k] = cls.from_dict(v)
        return node


class ExecutionTree:
    """4-level hierarchical execution history tree."""

    def __init__(self):
        self.root = TreeNode(name="harness_executions", level="root")

    def add_run(
        self,
        domain: str,
        workflow: str,
        run_id: str,
        steps: List[Dict],
    ):
        """실행 기록을 계층 트리에 추가한다."""
        # Domain level
        if domain not in self.root.children:
            self.root.add_child(
                domain, TreeNode(name=domain, level="domain")
            )
        domain_node = self.root.children[domain]

        # Workflow level
        if workflow not in domain_node.children:
            domain_node.add_child(
                workflow, TreeNode(name=workflow, level="workflow")
            )
        wf_node = domain_node.children[workflow]

        # Run level
        success = all(s.get("success", False) for s in steps)
        total_ms = sum(s.get("elapsed_ms", 0) for s in steps)
        run_node = TreeNode(
            name=run_id,
            level="run",
            metadata={
                "success": success,
                "total_ms": total_ms,
                "step_count": len(steps),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Step level
        for s in steps:
            step_meta = {k: v for k, v in s.items() if k != "step_id"}
            step_node = TreeNode(
                name=s["step_id"], level="step", metadata=step_meta,
            )
            run_node.add_child(s["step_id"], step_node)

        wf_node.add_child(run_id, run_node)
        self._update_summaries(domain_node, wf_node)

    def get_domain(self, domain: str) -> Optional[TreeNode]:
        """도메인 노드를 반환한다."""
        return self.root.children.get(domain)

    def summarize(self, domain: str) -> Dict[str, Any]:
        """도메인 전체 요약 통계를 반환한다."""
        domain_node = self.get_domain(domain)
        if not domain_node:
            return {"total_runs": 0, "success_rate": 0.0}

        runs = []
        for wf in domain_node.children.values():
            runs.extend(wf.children.values())

        total = len(runs)
        if total == 0:
            return {"total_runs": 0, "success_rate": 0.0}

        successes = sum(1 for r in runs if r.metadata.get("success"))
        return {
            "domain": domain,
            "total_runs": total,
            "success_rate": successes / total,
            "workflows": list(domain_node.children.keys()),
        }

    def search(self, query: str) -> List[Dict[str, Any]]:
        """에러 메시지 기반으로 실행 기록을 검색한다."""
        results = []
        query_lower = query.lower()

        for domain_node in self.root.children.values():
            for wf_node in domain_node.children.values():
                for run_id, run_node in wf_node.children.items():
                    for step_node in run_node.children.values():
                        error = step_node.metadata.get("error", "")
                        if error and query_lower in error.lower():
                            results.append({
                                "domain": domain_node.name,
                                "workflow": wf_node.name,
                                "run_id": run_id,
                                "step_id": step_node.name,
                                "error": error,
                            })
        return results

    def to_dict(self) -> dict:
        """전체 트리를 딕셔너리로 직렬화한다."""
        return self.root.to_dict()

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionTree":
        """딕셔너리에서 트리를 복원한다."""
        tree = cls()
        tree.root = TreeNode.from_dict(data)
        return tree

    def _update_summaries(
        self, domain_node: TreeNode, wf_node: TreeNode
    ):
        """워크플로우/도메인 노드의 요약을 갱신한다."""
        # Workflow summary
        runs = list(wf_node.children.values())
        total = len(runs)
        successes = sum(1 for r in runs if r.metadata.get("success"))
        wf_node.summary = f"{total} runs, {successes}/{total} success"

        # Domain summary
        all_runs = []
        for wf in domain_node.children.values():
            all_runs.extend(wf.children.values())
        dt = len(all_runs)
        ds = sum(1 for r in all_runs if r.metadata.get("success"))
        wf_count = len(domain_node.children)
        domain_node.summary = (
            f"{dt} runs across {wf_count} workflows, "
            f"{ds}/{dt} success"
        )
