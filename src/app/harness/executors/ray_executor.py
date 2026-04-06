import ast
import logging
import os
import time
from typing import Any, Dict

from src.app.harness.executors import BaseExecutor, ExecutorResult

logger = logging.getLogger(__name__)

class SecurityError(Exception):
    pass

def _validate_script(code: str) -> None:
    """AST-level security validation before execution."""
    # Prevent imports and global modifications.
    # Note: `exec` and `eval` are caught by BLOCKED_NAMES.
    BLOCKED_NODES = (ast.Import, ast.ImportFrom, ast.Global)
    
    # Prevent access to dangerous built-ins or modules if somehow referenced
    BLOCKED_NAMES = {
        "__import__", "eval", "exec", "compile", "open",
        "os", "subprocess", "sys", "shutil", "socket", "urllib", "requests"
    }

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SecurityError(f"Syntax error in script: {e}")

    for node in ast.walk(tree):
        if isinstance(node, BLOCKED_NODES):
            raise SecurityError(f"Security Policy Violation: Blocked AST node {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise SecurityError(f"Security Policy Violation: Blocked identifier '{node.id}'")


def _get_ray():
    """Lazy-load ray to avoid ImportError in minimal environments."""
    try:
        import ray
        return ray
    except ImportError:
        return None


class RayExecutor(BaseExecutor):
    """
    Ray 클러스터를 활용하여 코드를 분산 실행하는 Executor.
    AST 기반 보안 검증을 통해 악성 코드(예: os 명령 실행)를 사전에 차단합니다.
    """
    executor_type = "ray"

    def __init__(self):
        self._ray = _get_ray()
        self._connected = False

    def _ensure_connected(self):
        if not self._ray:
            logger.warning("Ray module not installed. Proceeding with simulated execution.")
            return

        if not self._connected and not self._ray.is_initialized():
            ray_address = os.environ.get("RAY_ADDRESS", "auto")
            logger.info(f"Connecting to Ray cluster at {ray_address}...")
            try:
                self._ray.init(address=ray_address, ignore_reinit_error=True)
                self._connected = True
            except Exception as e:
                logger.warning(f"Failed to connect to Ray cluster: {e}")

    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        start = time.time()
        script = step.get("script", "")
        params = step.get("parameters", {})
        timeout = step.get("timeout", 120)

        # 1. AST 수준 보안 검증 (exec() 취약점 대응)
        logger.info("[ray] Validating script AST for security policies...")
        try:
            _validate_script(script)
        except SecurityError as e:
            logger.error(f"[ray] Security validation failed: {str(e)}")
            return ExecutorResult(
                success=False,
                error=str(e),
                elapsed_ms=int((time.time() - start) * 1000)
            )

        # 2. Ray 클러스터 연결 확인
        self._ensure_connected()

        # Ray 미설치 시 시뮬레이션 모드 작동
        if not self._ray or not self._ray.is_initialized():
            logger.info("[ray] Ray 클러스터 연결 실패 또는 미설치. 시뮬레이션 모드로 실행합니다.")
            time.sleep(0.5)  # Simulate some processing time
            return ExecutorResult(
                success=True,
                output={"status": "ray_simulated", "safe_script": script[:50] + "..."},
                elapsed_ms=int((time.time() - start) * 1000)
            )

        # 3. Ray Task 실행 프로비저닝 (자원 설정)
        num_cpus = params.get("num_cpus", 1)
        ray_options = {"num_cpus": num_cpus}
        
        # 샌드박싱 처리를 통해 안전한 실행 환경 구축
        @self._ray.remote(**ray_options)
        def _execute_script_remote(script_code: str, ctx: dict):
            """Ray Worker 노드 내부에서 격리 실행되는 Task"""
            local_ns = {"context": ctx, "result": None}
            safe_builtins = {
                "print": print, "range": range, "len": len, "round": round,
                "int": int, "str": str, "float": float, "bool": bool,
                "list": list, "dict": dict, "tuple": tuple, "set": set,
                "True": True, "False": False, "None": None,
                "Exception": Exception, "ValueError": ValueError
            }
            # 제한된 빌트인 환경에서 실행 (exec 취약점 방어 2차 차단선)
            exec(script_code, {"__builtins__": safe_builtins}, local_ns)

            if "run" in local_ns and callable(local_ns["run"]):
                return local_ns["run"](ctx)
            return local_ns.get("result", {"status": "completed"})

        logger.info(f"  [ray] Submitting task to cluster (cpus={num_cpus}, timeout={timeout}s)")
        
        # 원격 실행 및 타임아웃 감시
        try:
            ref = _execute_script_remote.remote(script, dict(context))
            # timeout 처리를 위해 wait 함수 사용
            ready, not_ready = self._ray.wait([ref], timeout=timeout)

            if ready:
                result = self._ray.get(ref)
                elapsed_ms = int((time.time() - start) * 1000)
                
                # 워커 노드 ID 등 메타데이터 추적 (옵션)
                metadata = {}
                worker_node = os.environ.get("RAY_NODE_ID", "local")
                if worker_node:
                    metadata["worker_node"] = worker_node

                return ExecutorResult(
                    success=True,
                    output=result,
                    elapsed_ms=elapsed_ms,
                    metadata=metadata
                )
            else:
                return ExecutorResult(
                    success=False,
                    error=f"Ray task timed out after {timeout}s",
                    elapsed_ms=int((time.time() - start) * 1000)
                )

        except Exception as e:
            logger.error(f"[ray] Execution failed: {str(e)}")
            return ExecutorResult(
                success=False,
                error=f"Ray worker error: {str(e)}",
                elapsed_ms=int((time.time() - start) * 1000)
            )
