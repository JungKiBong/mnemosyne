"""
Container Executor — Run code inside Docker containers.

DSL step format:
    {
        "id": "analysis",
        "type": "container_exec",
        "image": "python:3.11-slim",
        "command": "python /src/analyze.py",
        "volumes": {"/host/data": {"bind": "/data", "mode": "ro"}},
        "env": {"API_KEY": "xxx"},
        "timeout": 120,
        "output_key": "analysis_result"
    }
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from src.app.harness.executors import BaseExecutor, ExecutorResult

logger = logging.getLogger(__name__)


def _get_docker_client():
    """Lazy-load Docker SDK client."""
    try:
        import docker
        return docker.from_env()
    except ImportError:
        raise RuntimeError(
            "docker package not installed. Run: pip install docker"
        )
    except Exception as e:
        raise RuntimeError(f"Cannot connect to Docker daemon: {e}")


class ContainerExecutor(BaseExecutor):
    """
    Execute a command inside a Docker container and capture stdout/stderr.

    Falls back gracefully if Docker is unavailable.
    """

    executor_type = "container_exec"

    def __init__(self, docker_client=None):
        """
        Args:
            docker_client: Optional pre-configured docker.DockerClient.
                           If None, creates one from environment.
        """
        self._client = docker_client

    def _get_client(self):
        if self._client is None:
            self._client = _get_docker_client()
        return self._client

    def validate(self, step: dict) -> Optional[str]:
        if not step.get("image"):
            return "container_exec step requires 'image' field"
        if not step.get("command"):
            return "container_exec step requires 'command' field"
        return None

    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        image = step.get("image", "python:3.11-slim")
        command = step.get("command", "echo 'no command'")
        volumes = step.get("volumes", {})
        env_vars = step.get("env", {})
        timeout = step.get("timeout", 120)

        # Merge env from context if needed
        if context.get("env"):
            merged_env = {**context["env"], **env_vars}
        else:
            merged_env = env_vars

        start = time.time()
        try:
            client = self._get_client()
            logger.info(
                f"  [container_exec] Running '{command}' in {image} "
                f"(timeout={timeout}s)"
            )

            container = client.containers.run(
                image=image,
                command=command,
                volumes=volumes,
                environment=merged_env,
                detach=True,
                remove=False,
                network_mode="bridge",
            )

            # Wait for completion
            result = container.wait(timeout=timeout)
            exit_code = result.get("StatusCode", -1)

            # Capture logs
            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )

            # Cleanup
            try:
                container.remove(force=True)
            except Exception:
                pass

            elapsed_ms = int((time.time() - start) * 1000)

            if exit_code == 0:
                return ExecutorResult(
                    success=True,
                    output=stdout.strip(),
                    elapsed_ms=elapsed_ms,
                    metadata={
                        "exit_code": exit_code,
                        "image": image,
                        "stderr": stderr.strip() if stderr.strip() else None,
                    },
                )
            else:
                return ExecutorResult(
                    success=False,
                    output=stdout.strip(),
                    error=f"Container exited with code {exit_code}: {stderr.strip()}",
                    elapsed_ms=elapsed_ms,
                    metadata={"exit_code": exit_code, "image": image},
                )

        except RuntimeError as e:
            # Docker not available
            elapsed_ms = int((time.time() - start) * 1000)
            return ExecutorResult(
                success=False,
                error=f"Docker unavailable: {e}",
                elapsed_ms=elapsed_ms,
                metadata={"fallback": True},
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return ExecutorResult(
                success=False,
                error=f"Container execution failed: {e}",
                elapsed_ms=elapsed_ms,
            )
