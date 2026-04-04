"""
True Parallel Executor — concurrent branch execution using ThreadPoolExecutor.

Replaces the sequential emulation in HarnessRuntime._handle_parallel
with actual concurrent execution.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.app.harness.executors import BaseExecutor, ExecutorResult

logger = logging.getLogger(__name__)


class JoinStrategy(str, Enum):
    """How to handle results from parallel branches."""
    WAIT_ALL = "wait_all"           # Wait for all branches (default)
    FIRST_SUCCESS = "first_success"  # Return as soon as one succeeds


@dataclass
class BranchResult:
    """Individual branch execution outcome."""
    branch_id: str
    result: ExecutorResult
    completed_at: float  # monotonic timestamp


class ParallelExecutor(BaseExecutor):
    """
    Executes multiple branch steps concurrently using a thread pool.

    DSL format:
        {
            "id": "parallel_step",
            "type": "parallel",
            "branches": ["step_a", "step_b", "step_c"],
            "join_strategy": "wait_all",   # or "first_success"
            "max_workers": 4               # optional thread pool size
        }
    """

    executor_type = "parallel"

    def __init__(self, step_executor_fn=None, max_workers: int = 4):
        """
        Args:
            step_executor_fn: Callable(step_dict, context) -> Any
                The function to call for each branch step.
            max_workers: Default thread pool size.
        """
        self._step_executor_fn = step_executor_fn
        self._max_workers = max_workers

    def set_step_executor(self, fn):
        """Set the function used to execute individual steps."""
        self._step_executor_fn = fn

    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        """
        Execute all branches in parallel.

        The `step` must contain a `_resolved_branches` key with a list of
        actual step dicts to execute (resolved by the runtime before calling).
        """
        branch_ids = step.get("branches", [])
        resolved_branches: List[dict] = step.get("_resolved_branches", [])
        join_strategy = JoinStrategy(step.get("join_strategy", "wait_all"))
        max_workers = step.get("max_workers", self._max_workers)

        if not resolved_branches:
            logger.warning("[parallel] No resolved branches to execute")
            return ExecutorResult(success=True, output={}, metadata={"branches": 0})

        if self._step_executor_fn is None:
            return ExecutorResult(
                success=False,
                error="ParallelExecutor: no step_executor_fn configured",
            )

        logger.info(
            f"  [parallel] Executing {len(resolved_branches)} branches "
            f"(strategy={join_strategy.value}, workers={max_workers})"
        )

        start = time.time()
        branch_results: Dict[str, BranchResult] = {}
        errors: List[str] = []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_bid: Dict[Future, str] = {}

            for branch_step in resolved_branches:
                bid = branch_step["id"]
                future = pool.submit(
                    self._run_branch, bid, branch_step, context
                )
                future_to_bid[future] = bid

            if join_strategy == JoinStrategy.FIRST_SUCCESS:
                # Return as soon as any branch succeeds
                for future in as_completed(future_to_bid):
                    bid = future_to_bid[future]
                    br = future.result()
                    branch_results[bid] = br
                    if br.result.success:
                        logger.info(f"  [parallel] First success: '{bid}'")
                        # Cancel remaining futures
                        for remaining in future_to_bid:
                            if remaining != future:
                                remaining.cancel()
                        break
                    else:
                        errors.append(f"{bid}: {br.result.error}")
            else:
                # Wait for all
                for future in as_completed(future_to_bid):
                    bid = future_to_bid[future]
                    br = future.result()
                    branch_results[bid] = br
                    if not br.result.success:
                        errors.append(f"{bid}: {br.result.error}")

        elapsed_ms = int((time.time() - start) * 1000)

        # Merge outputs into result
        merged_output = {}
        for bid, br in branch_results.items():
            if br.result.output is not None:
                merged_output[bid] = br.result.output

        all_success = len(errors) == 0
        return ExecutorResult(
            success=all_success,
            output=merged_output,
            error="; ".join(errors) if errors else None,
            elapsed_ms=elapsed_ms,
            metadata={
                "branches": len(branch_results),
                "join_strategy": join_strategy.value,
                "branch_details": {
                    bid: {
                        "success": br.result.success,
                        "elapsed_ms": br.result.elapsed_ms,
                    }
                    for bid, br in branch_results.items()
                },
            },
        )

    def _run_branch(
        self, branch_id: str, step: dict, context: Dict[str, Any]
    ) -> BranchResult:
        """Execute a single branch in a worker thread."""
        start = time.time()
        try:
            output = self._step_executor_fn(step, context)
            result = ExecutorResult(
                success=True,
                output=output,
                elapsed_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            logger.warning(f"  [parallel] Branch '{branch_id}' failed: {e}")
            result = ExecutorResult(
                success=False,
                error=str(e),
                elapsed_ms=int((time.time() - start) * 1000),
            )
        return BranchResult(
            branch_id=branch_id,
            result=result,
            completed_at=time.monotonic(),
        )
