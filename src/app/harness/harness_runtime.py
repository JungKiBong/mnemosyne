"""
harness_runtime.py — Mories Harness v2 범용 워크플로우 런타임 엔진

분기(branch), 반복(loop), 조건 판단, 코드 실행, 외부 API 호출,
웹훅 발사, 병렬 실행, 대기를 JSON DSL로 정의한 워크플로우를
실제로 구동하는 실행 엔진.

상태는 JSON 파일로 체크포인트되어, 중단 후 재개가 가능합니다.
실행 결과는 Mories harness_execute API로 기록되어 자기 개선 루프를 형성합니다.

작성: 2026-04-04
"""

import json
import os
import re
import time
import logging
import importlib
import uuid
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import requests

logger = logging.getLogger("harness_runtime")


# ─────────────────────────────────────────────
# 1. 변수 치환 엔진 (${step_id.output_key} 등)
# ─────────────────────────────────────────────
def _resolve_vars(value: Any, context: Dict[str, Any]) -> Any:
    """
    문자열 내의 ${step_id.output_key} 패턴을 context에서 검색하여 치환한다.
    중첩된 dict/list도 재귀적으로 처리한다.
    """
    if isinstance(value, str):
        # ${step_id.key} 패턴 추출
        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, value)
        if not matches:
            return value
        result = value
        for match in matches:
            parts = match.split(".", 1)
            if len(parts) == 2:
                step_id, key = parts
                resolved = context.get(step_id, {}).get(key, f"<UNRESOLVED:{match}>")
            else:
                # 환경변수 또는 단일 키 참조
                resolved = context.get("env", {}).get(match, os.environ.get(match, f"<UNRESOLVED:{match}>"))
            # 전체가 변수 하나뿐이면 원래 타입 유지
            if result == f"${{{match}}}":
                return resolved
            result = result.replace(f"${{{match}}}", str(resolved))
        return result
    elif isinstance(value, dict):
        return {k: _resolve_vars(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_vars(item, context) for item in value]
    return value


# ─────────────────────────────────────────────
# 2. 조건 파서 (Condition Parser)
# ─────────────────────────────────────────────

def _parse_condition(resolved: str) -> bool:
    """
    Parse a simple condition string safely.
    Supports: ==, !=, <, >, <=, >=, null checks, truthy evaluation.
    """
    s = str(resolved).strip()

    # Null/None checks
    for op, expected in [("!=", False), ("==", True)]:
        for null_word in ("null", "None"):
            pattern = f"{op} {null_word}"
            if pattern in s or f"{op}{null_word}" in s:
                val = s.split(op)[0].strip()
                is_null = val in ("None", "null", "", "<UNRESOLVED")
                return is_null if expected else not is_null

    # Comparison operators (order matters: >= before >, <= before <)
    for op, fn in [
        (">=", lambda a, b: a >= b),
        ("<=", lambda a, b: a <= b),
        ("!=", lambda a, b: a != b),
        ("==", lambda a, b: a == b),
        (">",  lambda a, b: a > b),
        ("<",  lambda a, b: a < b),
    ]:
        if op in s:
            parts = s.split(op, 1)
            if len(parts) == 2:
                try:
                    return fn(float(parts[0].strip()), float(parts[1].strip()))
                except ValueError:
                    # String comparison fallback
                    return fn(parts[0].strip(), parts[1].strip())

    # Truthy evaluation
    return bool(s) and s.lower() not in ("false", "0", "none", "null")


# ─────────────────────────────────────────────
# 3. 개별 스텝 실행기 (Step Executors)
# ─────────────────────────────────────────────
def _exec_code(step: dict, context: dict) -> Any:
    """Python 함수를 동적으로 import하여 실행한다."""
    action = step["action"]  # 예: "edge_agent.detect_event"
    parts = action.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(f"action 형식 오류: '{action}' — 'module.function' 형태여야 합니다")

    module_path, func_name = parts
    params = _resolve_vars(step.get("params", {}), context)

    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        result = func(**params)
        logger.info(f"  [code] {action}() → {str(result)[:120]}")
        return result
    except Exception as e:
        logger.error(f"  [code] {action}() 실행 실패: {e}")
        raise


def _exec_api_call(step: dict, context: dict) -> Any:
    """외부 REST API를 호출한다 (Dify, 커스텀 서비스 등)."""
    url = _resolve_vars(step["url"], context)
    method = step.get("method", "POST").upper()
    headers = _resolve_vars(step.get("headers", {}), context)
    body = _resolve_vars(step.get("body", {}), context)
    timeout = step.get("timeout_seconds", 30)

    logger.info(f"  [api_call] {method} {url}")
    try:
        resp = requests.request(method, url, json=body, headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            logger.warning(f"  [api_call] HTTP {resp.status_code}: {resp.text[:200]}")
        ct = (resp.headers.get("content-type") or "").lower()
        result = resp.json() if "application/json" in ct else resp.text
        return result
    except Exception as e:
        logger.error(f"  [api_call] 요청 실패: {e}")
        raise


def _exec_webhook(step: dict, context: dict) -> Any:
    """n8n / Zapier 등 외부 웹훅 엔드포인트에 이벤트를 POST한다."""
    url = _resolve_vars(step["url"], context)
    body = _resolve_vars(step.get("body", {}), context)
    timeout = step.get("timeout_seconds", 10)

    logger.info(f"  [webhook] POST {url}")
    try:
        resp = requests.post(url, json=body, timeout=timeout)
        logger.info(f"  [webhook] 응답: {resp.status_code}")
        return {"status_code": resp.status_code, "body": resp.text[:200]}
    except Exception as e:
        logger.error(f"  [webhook] 발사 실패: {e}")
        raise


# ─────────────────────────────────────────────
# 3. 상태 저장/복원 (JSON 체크포인트)
# ─────────────────────────────────────────────
class StateManager:
    """워크플로우 실행 상태를 JSON 파일로 체크포인트한다."""

    def __init__(self, storage_config: dict, run_id: str):
        self.storage_type = storage_config.get("type", "json_file")
        base_path = storage_config.get("path", "./harness_state")
        # ${harness_id} 등의 변수는 나중에 치환
        self.state_dir = base_path
        self.run_id = run_id
        self.state_file = os.path.join(self.state_dir, f"{run_id}.json")
        os.makedirs(self.state_dir, exist_ok=True)

    def save(self, state: dict):
        """현재 상태를 JSON 파일에 체크포인트한다."""
        state["_updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)
        logger.debug(f"  [state] 체크포인트 저장: {self.state_file}")

    def load(self) -> Optional[dict]:
        """이전 체크포인트가 있으면 로드한다."""
        if os.path.exists(self.state_file):
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def delete(self):
        """실행 완료 후 체크포인트 파일을 제거한다."""
        if os.path.exists(self.state_file):
            os.remove(self.state_file)


# ─────────────────────────────────────────────
# 4. 메인 런타임 엔진
# ─────────────────────────────────────────────
class HarnessRuntime:
    """
    JSON DSL 워크플로우를 실제로 실행하는 범용 런타임 엔진 (v4).

    지원 스텝 타입:
    - code: Python 함수 호출
    - api_call: 외부 REST API 호출
    - webhook: n8n/Zapier 등 이벤트 발사
    - container_exec: Docker 컨테이너 내 실행 (v4)
    - branch: 조건 분기 (then/else)
    - loop: 반복 (max_iterations + goto)
    - parallel: 실제 병렬 스텝 실행 (v4 ThreadPoolExecutor)
    - wait: 비동기 대기
    - end: 종료 + 결과 기록
    """

    def __init__(self, workflow: dict, env_overrides: Optional[dict] = None):
        """
        Args:
            workflow: JSON DSL 워크플로우 딕셔너리
            env_overrides: 환경변수 오버라이드
        """
        self.workflow = workflow
        self.steps = {s["id"]: s for s in workflow["steps"]}
        self.step_order = [s["id"] for s in workflow["steps"]]

        # 실행 컨텍스트: 각 스텝의 출력값 + 환경변수
        self.context: Dict[str, Any] = {
            "env": {**workflow.get("env", {}), **(env_overrides or {})},
            "_meta": {
                "harness_id": workflow.get("harness_id", "unknown"),
                "domain": workflow.get("domain", "unknown"),
                "run_id": uuid.uuid4().hex[:12],
                "started_at": datetime.now(timezone.utc).isoformat()
            }
        }

        # 상태 관리자
        storage_cfg = workflow.get("state_storage", {"type": "json_file", "path": "./harness_state"})
        self.state_mgr = StateManager(storage_cfg, self.context["_meta"]["run_id"])

        # 루프 카운터 (무한루프 방지)
        self._loop_counters: Dict[str, int] = {}

        # 실행 로그
        self._execution_log: list = []

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

        # ── v4: Executor Registry + Tool Memory ──
        from src.app.harness.executors import create_default_registry
        from src.app.harness.executors.parallel_executor import ParallelExecutor
        from src.app.harness.executors.container_executor import ContainerExecutor
        from src.app.harness.memory.tool_memory_index import ToolMemoryIndex

        self._executor_registry = create_default_registry()

        # Register container executor
        self._executor_registry.register("container_exec", ContainerExecutor())

        # Parallel executor with callback to our _execute_step_fn
        self._parallel_executor = ParallelExecutor(
            step_executor_fn=self._execute_step_fn,
            max_workers=workflow.get("parallel_workers", 4),
        )
        self._executor_registry.register("parallel", self._parallel_executor)

        # Tool Memory Index
        tool_memory_db = os.path.join(
            storage_cfg.get("path", "./harness_state"), "tool_memory.db"
        )
        self._tool_memory = ToolMemoryIndex(db_path=tool_memory_db)

    def _execute_step_fn(self, step: dict, context: Dict[str, Any]) -> Any:
        """Callback for ParallelExecutor — execute a single sub-step and return result."""
        step_type = step["type"]
        if self._executor_registry.has(step_type):
            er = self._executor_registry.execute(step_type, step, context)
            if not er.success:
                raise RuntimeError(er.error or "Unknown error")
            return er.output
        # Fallback for non-registry types
        if step_type == "code":
            return _exec_code(step, context)
        elif step_type == "api_call":
            return _exec_api_call(step, context)
        elif step_type == "webhook":
            return _exec_webhook(step, context)
        raise ValueError(f"Unknown step_type for parallel branch: {step_type}")

    def run(self, resume: bool = False) -> dict:
        """
        워크플로우를 처음부터(또는 체크포인트에서 재개) 실행한다.

        Returns:
            실행 결과 요약 딕셔너리
        """
        run_id = self.context["_meta"]["run_id"]
        logger.info(f"🚀 Harness Runtime 시작 [run_id={run_id}]")
        logger.info(f"   도메인: {self.workflow.get('domain')} | 스텝 수: {len(self.steps)}")

        # 재개 시도
        current_idx = 0
        if resume:
            saved = self.state_mgr.load()
            if saved:
                self.context.update(saved.get("context", {}))
                current_idx = saved.get("current_step_idx", 0)
                logger.info(f"   ▶ 체크포인트에서 재개: step #{current_idx}")

        start_time = time.time()
        success = True
        error_msg = None

        try:
            while current_idx < len(self.step_order):
                step_id = self.step_order[current_idx]
                step = self.steps[step_id]
                step_type = step["type"]

                logger.info(f"━━ Step [{current_idx}] '{step_id}' (type={step_type}) ━━")

                # 체크포인트 저장
                self.state_mgr.save({
                    "current_step_idx": current_idx,
                    "context": {k: v for k, v in self.context.items() if k != "env"}
                })

                # 스텝 타입별 실행 분기
                next_idx = self._execute_step(step, current_idx)

                if next_idx == -1:
                    # end 스텝에 의한 종료
                    break
                current_idx = next_idx

        except Exception as e:
            success = False
            error_msg = str(e)
            logger.error(f"❌ 워크플로우 실행 실패: {e}")

            # 모니터링 웹훅 발사 (실패 시)
            fail_hook = self.workflow.get("monitoring", {}).get("webhook_on_failure")
            if fail_hook:
                try:
                    requests.post(fail_hook, json={
                        "run_id": run_id,
                        "error": error_msg,
                        "step": locals().get('step_id', 'unknown')
                    }, timeout=5)
                except Exception:
                    pass

        elapsed_ms = int((time.time() - start_time) * 1000)

        # 결과 요약
        result = {
            "run_id": run_id,
            "harness_id": self.workflow.get("harness_id"),
            "domain": self.workflow.get("domain"),
            "success": success,
            "error": error_msg,
            "elapsed_ms": elapsed_ms,
            "steps_executed": len(self._execution_log),
            "execution_log": self._execution_log,
            "final_context_keys": list(self.context.keys())
        }

        # ── v3: execution tree + evolution classification ──
        from src.app.harness.metrics_store import RunSummary

        self._exec_tree.add_run(
            domain=self.workflow.get("domain", "unknown"),
            workflow=self.workflow.get("harness_id", "unknown"),
            run_id=run_id,
            steps=self._execution_log,
        )

        evo_mode = self._evolution.classify_evolution(
            harness_id=self.workflow.get("harness_id", "unknown"),
            run_success=success,
            error_msg=error_msg,
        )

        self._metrics.record_run(RunSummary(
            run_id=run_id,
            harness_id=self.workflow.get("harness_id", "unknown"),
            domain=self.workflow.get("domain", "unknown"),
            success=success,
            total_steps=len(self._execution_log),
            elapsed_ms=elapsed_ms,
            evolution_mode=evo_mode.value if evo_mode else None,
        ))

        result["metrics_summary"] = self._metrics.get_harness_stats(
            self.workflow.get("harness_id", "unknown")
        )
        result["execution_tree"] = self._exec_tree.to_dict()
        result["evolution_mode"] = evo_mode.value if evo_mode else None

        # 성공 시 체크포인트 정리
        if success:
            self.state_mgr.delete()
            complete_hook = self.workflow.get("monitoring", {}).get("webhook_on_complete")
            if complete_hook:
                try:
                    requests.post(complete_hook, json=result, timeout=5)
                except Exception:
                    pass

        logger.info(f"{'✅' if success else '❌'} 실행 완료 [{elapsed_ms}ms] — "
                     f"스텝 {len(self._execution_log)}건 실행")
        return result

    def _execute_step(self, step: dict, current_idx: int) -> int:
        """
        단일 스텝을 실행하고, 다음 스텝 인덱스를 반환한다.
        -1을 반환하면 워크플로우 종료.
        """
        step_id = step["id"]
        step_type = step["type"]
        start = time.time()

        try:
            # ── v4: Native handlers (control flow) ──
            if step_type == "branch":
                return self._handle_branch(step, current_idx)

            elif step_type == "loop":
                return self._handle_loop(step, current_idx)

            elif step_type == "parallel":
                self._handle_parallel(step)

            elif step_type == "wait":
                wait_sec = step.get("timeout_seconds", 5)
                logger.info(f"  [wait] {wait_sec}초 대기...")
                time.sleep(wait_sec)

            elif step_type == "end":
                logger.info(f"  [end] 워크플로우 종료")
                self._log_step(step_id, step_type, time.time() - start, True)
                return -1

            # ── v4: Delegate to ExecutorRegistry ──
            elif self._executor_registry.has(step_type):
                exec_result = self._executor_registry.execute(step_type, step, self.context)
                if step.get("output_key"):
                    self.context.setdefault(step_id, {})[step.get("output_key")] = exec_result.output
                if not exec_result.success:
                    raise RuntimeError(exec_result.error or f"Executor failed for {step_type}")
                # Record tool memory
                self._record_tool_memory(step_id, step_type, exec_result)

            else:
                logger.warning(f"  [unknown] Unregistered step_type: {step_type}")

            self._log_step(step_id, step_type, time.time() - start, True)
            return current_idx + 1

        except Exception as e:
            # 에러 핸들링 (on_error)
            on_error = step.get("on_error", "abort")

            if on_error == "skip":
                logger.warning(f"  [skip] 에러 무시하고 다음 스텝으로: {e}")
                self._log_step(step_id, step_type, time.time() - start, False, str(e))
                return current_idx + 1

            elif on_error == "retry":
                retry_key = f"retry_{step_id}"
                self._loop_counters[retry_key] = self._loop_counters.get(retry_key, 0) + 1
                max_retry = step.get("retry_count", 3)
                if self._loop_counters[retry_key] <= max_retry:
                    logger.warning(f"  [retry] {self._loop_counters[retry_key]}/{max_retry}: {e}")
                    time.sleep(1)  # 재시도 전 1초 대기
                    return current_idx  # 같은 스텝 재실행
                else:
                    logger.error(f"  [retry] 최대 재시도 횟수 초과")

            elif on_error == "fallback":
                fb_step = step.get("fallback_step")
                if fb_step and fb_step in self.steps:
                    logger.warning(f"  [fallback] → {fb_step}")
                    self._log_step(step_id, step_type, time.time() - start, False, str(e))
                    return self.step_order.index(fb_step)

            # abort (기본값)
            self._log_step(step_id, step_type, time.time() - start, False, str(e))
            raise

    def _handle_branch(self, step: dict, current_idx: int) -> int:
        """조건 분기를 처리한다. condition 문자열을 변수 치환 후 평가한다."""
        raw_cond = step.get("condition", "true")
        resolved = _resolve_vars(raw_cond, self.context)

        try:
            cond_result = _parse_condition(resolved)
        except Exception:
            cond_result = False

        target = step.get("then") if cond_result else step.get("else")
        logger.info(f"  [branch] 조건='{raw_cond}' → {cond_result} → goto '{target}'")

        if target and target in self.steps:
            return self.step_order.index(target)
        return current_idx + 1

    def _handle_loop(self, step: dict, current_idx: int) -> int:
        """반복 스텝을 처리한다. max_iterations 초과 시 다음 스텝으로 진행."""
        loop_id = step["id"]
        max_iter = step.get("max_iterations", 5)
        goto_step = step.get("goto")

        self._loop_counters[loop_id] = self._loop_counters.get(loop_id, 0) + 1
        current_count = self._loop_counters[loop_id]

        if current_count <= max_iter and goto_step in self.steps:
            logger.info(f"  [loop] 반복 {current_count}/{max_iter} → goto '{goto_step}'")
            return self.step_order.index(goto_step)
        else:
            logger.info(f"  [loop] 최대 반복({max_iter}) 도달, 다음 스텝으로 진행")
            return current_idx + 1

    def _handle_parallel(self, step: dict):
        """v4: 실제 병렬 실행 (ThreadPoolExecutor)"""
        branch_ids = step.get("branches", [])
        resolved = [self.steps[bid] for bid in branch_ids if bid in self.steps]

        if not resolved:
            logger.warning("  [parallel] No valid branches found")
            return

        # Inject resolved branches for ParallelExecutor
        step_copy = {**step, "_resolved_branches": resolved}
        exec_result = self._parallel_executor.execute(step_copy, self.context)

        # Merge branch outputs into context
        if exec_result.output:
            for bid, output in exec_result.output.items():
                self.context.setdefault(bid, {})["_parallel_result"] = output

        if not exec_result.success:
            logger.warning(f"  [parallel] Some branches failed: {exec_result.error}")

    def _record_tool_memory(self, step_id: str, step_type: str, exec_result):
        """Record executor result into Tool Memory Index."""
        try:
            from src.app.harness.memory.tool_memory_index import ToolExecution
            self._tool_memory.record(ToolExecution(
                tool_name=step_id,
                tool_type=step_type,
                success=exec_result.success,
                elapsed_ms=exec_result.elapsed_ms,
                domain=self.workflow.get("domain", "unknown"),
                error=exec_result.error,
            ))
        except Exception as e:
            logger.debug(f"Tool memory record failed (non-critical): {e}")

    def _log_step(self, step_id: str, step_type: str, elapsed: float, success: bool, error: str = None):
        """실행 로그에 스텝 결과를 추가한다."""
        entry = {
            "step_id": step_id,
            "type": step_type,
            "success": success,
            "elapsed_ms": int(elapsed * 1000),
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self._execution_log.append(entry)

        # v3: record to metrics store
        from src.app.harness.metrics_store import StepMetric
        self._metrics.record_step(StepMetric(
            run_id=self.context["_meta"]["run_id"],
            harness_id=self.workflow.get("harness_id", "unknown"),
            step_id=step_id,
            step_type=step_type,
            success=success,
            elapsed_ms=int(elapsed * 1000),
            error=error,
        ))


# ─────────────────────────────────────────────
# 5. 편의 함수: JSON 파일에서 로드하여 실행
# ─────────────────────────────────────────────
def run_workflow_from_file(filepath: str, env_overrides: Optional[dict] = None, resume: bool = False) -> dict:
    """
    JSON DSL 워크플로우 파일을 읽어 실행한다.

    Args:
        filepath: 워크플로우 JSON 파일 경로
        env_overrides: 환경변수 오버라이드 딕셔너리
        resume: True면 이전 체크포인트에서 재개

    Returns:
        실행 결과 요약 딕셔너리
    """
    with open(filepath, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    runtime = HarnessRuntime(workflow, env_overrides)
    return runtime.run(resume=resume)


# ─────────────────────────────────────────────
# 6. CLI 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python harness_runtime.py <workflow.json> [--resume]")
        sys.exit(1)

    wf_file = sys.argv[1]
    do_resume = "--resume" in sys.argv

    result = run_workflow_from_file(wf_file, resume=do_resume)
    print(json.dumps(result, indent=2, ensure_ascii=False))
