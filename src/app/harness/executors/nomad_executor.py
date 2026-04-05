import logging
from typing import Any, Dict
from src.app.harness.executors import BaseExecutor, ExecutorResult

logger = logging.getLogger("nomad_executor")

class NomadExecutor(BaseExecutor):
    """
    HashiCorp Nomad 원격 인프라에서 작업을 스케줄링하고 결과를 대기/콜백하는 Executor.
    """
    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        import time
        start = time.time()
        job_spec = step.get("job_spec", {})
        # TODO: python-nomad 또는 REST API를 통해 Job 제출 및 모니터링 구현
        logger.info("[nomad] Nomad 인프라 작업 제출 시뮬레이션")
        elapsed = int((time.time() - start) * 1000)
        return ExecutorResult(
            success=True,
            output={"status": "nomad_simulated", "job": job_spec.get("name")},
            elapsed_ms=elapsed
        )
