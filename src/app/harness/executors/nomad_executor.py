"""
Nomad Executor — Submit and monitor batch jobs on HashiCorp Nomad.

Uses the Nomad HTTP API to submit parameterized batch jobs,
poll for completion, and collect allocation logs.

DSL step format:
    {
        "id": "gpu_training",
        "type": "nomad",
        "job_spec": {
            "name": "model-train",
            "type": "batch",
            "image": "pytorch/pytorch:latest",
            "command": "python train.py",
            "datacenter": "dc1",
            "cpu": 2000,
            "memory": 4096
        },
        "timeout": 600
    }
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

from src.app.harness.executors import BaseExecutor, ExecutorResult

def _get_requests():
    """Lazy-load requests to avoid ImportError in minimal environments."""
    try:
        import requests
        return requests
    except ImportError:
        raise RuntimeError("requests package not installed — pip install requests")

logger = logging.getLogger(__name__)

NOMAD_ADDR = os.environ.get("NOMAD_ADDR", "http://192.168.35.101:4646")


class NomadExecutor(BaseExecutor):
    """
    Execute tasks by submitting batch jobs to a Nomad cluster.

    Supports:
      - Parameterized batch job submission
      - Allocation status polling
      - Log collection from completed allocations
    """

    executor_type = "nomad"

    def __init__(self, nomad_addr: Optional[str] = None):
        self._addr = nomad_addr or NOMAD_ADDR

    def validate(self, step: dict) -> Optional[str]:
        job_spec = step.get("job_spec", {})
        if not job_spec.get("name"):
            return "nomad step requires job_spec.name"
        return None

    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        _requests = _get_requests()
        job_spec = step.get("job_spec", {})
        timeout = step.get("timeout", 300)
        start = time.time()

        job_name = job_spec.get("name", f"harness-{step.get('id', 'unknown')}")
        image = job_spec.get("image", "busybox:latest")
        command = job_spec.get("command", "echo 'hello from nomad'")
        datacenter = job_spec.get("datacenter", "dc1")
        cpu = job_spec.get("cpu", 500)
        memory = job_spec.get("memory", 256)

        try:
            # 0. Purge any previous run with same ID
            self._purge_job(job_name.replace(" ", "-").lower())

            # 1. Register batch job
            job_id = self._submit_job(
                job_name, image, command, datacenter, cpu, memory
            )
            logger.info(f"  [nomad] Submitted job '{job_id}'")

            # 2. Poll for completion
            final_status, alloc_id = self._poll_job(
                job_id, timeout, start
            )

            elapsed_ms = int((time.time() - start) * 1000)

            if final_status == "complete":
                # 3. Collect logs
                logs = self._get_alloc_logs(alloc_id) if alloc_id else ""
                return ExecutorResult(
                    success=True,
                    output=logs,
                    elapsed_ms=elapsed_ms,
                    metadata={
                        "mode": "nomad_batch",
                        "job_id": job_id,
                        "alloc_id": alloc_id,
                        "datacenter": datacenter,
                    },
                )
            elif final_status == "failed":
                logs = self._get_alloc_logs(alloc_id) if alloc_id else ""
                return ExecutorResult(
                    success=False,
                    output=logs,
                    error=f"Nomad job '{job_id}' failed",
                    elapsed_ms=elapsed_ms,
                    metadata={"job_id": job_id, "alloc_id": alloc_id},
                )
            else:
                return ExecutorResult(
                    success=False,
                    error=f"Nomad job '{job_id}' timed out ({timeout}s)",
                    elapsed_ms=elapsed_ms,
                    metadata={
                        "job_id": job_id,
                        "final_status": final_status,
                        "timeout": True,
                    },
                )

        except Exception as conn_err:
            import requests as _req_mod
            if isinstance(conn_err, _req_mod.ConnectionError):
                elapsed_ms = int((time.time() - start) * 1000)
                return ExecutorResult(
                    success=False,
                    error=f"Cannot connect to Nomad at {self._addr}",
                    elapsed_ms=elapsed_ms,
                    metadata={"nomad_addr": self._addr},
                )
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return ExecutorResult(
                success=False,
                error=f"Nomad execution failed: {e}",
                elapsed_ms=elapsed_ms,
            )

    # ── Nomad API Helpers ───────────────────────

    def _purge_job(self, job_id: str):
        """Purge any existing job with this ID to avoid stale state."""
        try:
            _requests = _get_requests()
            resp = _requests.delete(
                f"{self._addr}/v1/job/{job_id}",
                params={"purge": "true"},
                timeout=5,
            )
            if resp.status_code == 200:
                logger.info(f"  [nomad] Purged old job '{job_id}'")
                time.sleep(1)  # Brief wait for Nomad to clean up
        except Exception:
            pass  # Job may not exist, that's fine

    def _submit_job(
        self,
        name: str,
        image: str,
        command: str,
        datacenter: str,
        cpu: int,
        memory: int,
    ) -> str:
        """Submit a batch job via Nomad HTTP API.
        
        Uses 'raw_exec' driver for simple commands (echo, sh -c)
        to avoid Docker/LXC sysctl conflicts. Falls back to Docker
        for image-based tasks with privileged mode.
        """
        job_id = name.replace(" ", "-").lower()

        # Parse command into args
        cmd_parts = command.split()

        # Decide driver: use exec for simple shell commands
        # to avoid Docker-in-LXC sysctl issues
        # (raw_exec is not healthy on these nodes, exec is)
        use_exec = (
            image in ("busybox:latest", "alpine:latest")
            or command.startswith("echo ")
            or command.startswith("sh -c")
        )

        if use_exec:
            task_config = {
                "Name": "run",
                "Driver": "exec",
                "Config": {
                    "command": "/bin/sh",
                    "args": ["-c", command],
                },
                "Resources": {
                    "CPU": cpu,
                    "MemoryMB": memory,
                },
            }
        else:
            task_config = {
                "Name": "run",
                "Driver": "docker",
                "Config": {
                    "image": image,
                    "command": cmd_parts[0] if cmd_parts else "/bin/sh",
                    "args": cmd_parts[1:] if len(cmd_parts) > 1 else ["-c", "echo done"],
                    "privileged": True,
                    "security_opt": ["seccomp=unconfined"],
                },
                "Resources": {
                    "CPU": cpu,
                    "MemoryMB": memory,
                },
            }

        job_payload = {
            "Job": {
                "ID": job_id,
                "Name": name,
                "Type": "batch",
                "Datacenters": [datacenter],
                "TaskGroups": [
                    {
                        "Name": "main",
                        "Count": 1,
                        "RestartPolicy": {
                            "Attempts": 0,
                            "Mode": "fail",
                        },
                        "Tasks": [task_config],
                    }
                ],
            }
        }

        _requests = _get_requests()
        resp = _requests.post(
            f"{self._addr}/v1/jobs",
            json=job_payload,
            timeout=10,
        )
        resp.raise_for_status()
        return job_id

    def _poll_job(
        self, job_id: str, timeout: int, start_time: float
    ) -> tuple:
        """Poll job status until completion or timeout."""
        poll_interval = 2
        alloc_id = None

        while (time.time() - start_time) < timeout:
            try:
                # Get allocations for this job
                _requests = _get_requests()
                resp = _requests.get(
                    f"{self._addr}/v1/job/{job_id}/allocations",
                    timeout=5,
                )
                resp.raise_for_status()
                allocs = resp.json()

                if allocs:
                    alloc = allocs[0]  # Most recent allocation
                    alloc_id = alloc["ID"]
                    client_status = alloc.get("ClientStatus", "pending")

                    if client_status == "complete":
                        return "complete", alloc_id
                    elif client_status == "failed":
                        return "failed", alloc_id

                time.sleep(poll_interval)

            except Exception as e:
                logger.warning(f"[nomad] Poll error: {e}")
                time.sleep(poll_interval)

        return "timeout", alloc_id

    def _get_alloc_logs(self, alloc_id: str) -> str:
        """Retrieve stdout logs from a completed allocation."""
        try:
            _requests = _get_requests()
            resp = _requests.get(
                f"{self._addr}/v1/client/fs/logs/{alloc_id}",
                params={
                    "task": "run",
                    "type": "stdout",
                    "plain": "true",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.text.strip()
            return f"(log retrieval failed: {resp.status_code})"
        except Exception as e:
            return f"(log retrieval error: {e})"
