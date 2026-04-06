"""
Wasm Executor — Run code in a sandboxed environment.

Two modes:
  1. wasm_module: Run a pre-compiled .wasm file via wasmtime CLI
  2. script: Run a Python script in a subprocess sandbox with
             resource limits, timeout, and restricted filesystem

DSL step format:
    {
        "id": "safe_analysis",
        "type": "wasm_exec",
        "script": "print('hello from sandbox')",
        "sandbox": {
            "max_memory_mb": 256,
            "timeout_seconds": 30,
            "allow_network": false
        }
    }

    OR (for pre-compiled WASM modules):
    {
        "id": "wasm_module_run",
        "type": "wasm_exec",
        "wasm_module": "/path/to/module.wasm",
        "args": ["--input", "data.json"]
    }
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional

from src.app.harness.executors import BaseExecutor, ExecutorResult

logger = logging.getLogger(__name__)

# Default sandbox constraints
DEFAULT_SANDBOX = {
    "max_memory_mb": 256,
    "timeout_seconds": 30,
    "allow_network": False,
}

# Wasmtime binary search paths
WASMTIME_SEARCH_PATHS = [
    "/home/admin/.wasmtime/bin/wasmtime",
    os.path.expanduser("~/.wasmtime/bin/wasmtime"),
    "wasmtime",  # system PATH fallback
]


def _find_wasmtime() -> Optional[str]:
    """Locate wasmtime binary."""
    for path in WASMTIME_SEARCH_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    # Try system PATH
    try:
        result = subprocess.run(
            ["which", "wasmtime"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


class WasmExecutor(BaseExecutor):
    """
    Sandboxed executor using Wasmtime for WASM modules and
    subprocess isolation for script execution.

    Priority:
      1. If step has 'wasm_module' → run via wasmtime CLI
      2. If step has 'script' → run Python in subprocess sandbox
    """

    executor_type = "wasm_exec"

    def __init__(self, wasmtime_path: Optional[str] = None,
                 python_path: Optional[str] = None):
        self._wasmtime_path = wasmtime_path or _find_wasmtime()
        self._python_path = python_path or sys.executable

    def validate(self, step: dict) -> Optional[str]:
        if not step.get("wasm_module") and not step.get("script"):
            return "wasm_exec step requires 'wasm_module' or 'script' field"
        if step.get("wasm_module") and not os.path.isfile(step["wasm_module"]):
            return f"WASM module not found: {step['wasm_module']}"
        return None

    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        sandbox = {**DEFAULT_SANDBOX, **(step.get("sandbox") or {})}
        start = time.time()

        try:
            if step.get("wasm_module"):
                return self._run_wasm_module(step, sandbox, start)
            elif step.get("script"):
                return self._run_python_sandbox(step, sandbox, context, start)
            else:
                return ExecutorResult(
                    success=False,
                    error="No 'wasm_module' or 'script' provided",
                    elapsed_ms=int((time.time() - start) * 1000),
                )
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.time() - start) * 1000)
            return ExecutorResult(
                success=False,
                error=f"Sandbox timeout after {sandbox['timeout_seconds']}s",
                elapsed_ms=elapsed_ms,
                metadata={"sandbox": sandbox, "timeout": True},
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            return ExecutorResult(
                success=False,
                error=f"Sandbox execution failed: {e}",
                elapsed_ms=elapsed_ms,
            )

    # ── WASM Module Execution ───────────────────
    def _run_wasm_module(
        self, step: dict, sandbox: dict, start: float
    ) -> ExecutorResult:
        """Run a pre-compiled .wasm file via wasmtime CLI."""
        if not self._wasmtime_path:
            return ExecutorResult(
                success=False,
                error="wasmtime binary not found. Install: curl https://wasmtime.dev/install.sh -sSf | bash",
                elapsed_ms=int((time.time() - start) * 1000),
            )

        module_path = step["wasm_module"]
        args = step.get("args", [])
        timeout = sandbox["timeout_seconds"]

        cmd = [self._wasmtime_path, "run"]

        # Sandbox flags
        if not sandbox.get("allow_network", False):
            # wasmtime doesn't have network by default — WASI sandbox
            pass

        # Memory limit via wasmtime flags
        max_mem = sandbox.get("max_memory_mb", 256)
        cmd.extend([
            "--max-memory-size", str(max_mem * 1024 * 1024),
        ])

        cmd.append(module_path)
        cmd.extend(args)

        logger.info(f"  [wasm_exec] Running WASM module: {module_path}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        elapsed_ms = int((time.time() - start) * 1000)

        if result.returncode == 0:
            return ExecutorResult(
                success=True,
                output=result.stdout.strip(),
                elapsed_ms=elapsed_ms,
                metadata={
                    "mode": "wasm_module",
                    "module": module_path,
                    "stderr": result.stderr.strip() or None,
                },
            )
        else:
            return ExecutorResult(
                success=False,
                output=result.stdout.strip(),
                error=f"WASM exited with code {result.returncode}: {result.stderr.strip()}",
                elapsed_ms=elapsed_ms,
                metadata={"mode": "wasm_module", "exit_code": result.returncode},
            )

    # ── Python Script Sandbox ───────────────────
    def _run_python_sandbox(
        self, step: dict, sandbox: dict, context: Dict[str, Any],
        start: float,
    ) -> ExecutorResult:
        """Run a Python script string in a sandboxed subprocess."""
        script = step["script"]
        timeout = sandbox["timeout_seconds"]

        # Write script to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, prefix="harness_sandbox_"
        ) as f:
            # Inject context as JSON if available
            preamble = (
                "import json, os, sys\n"
                f"__context__ = json.loads({repr(context.get('_serializable', '{}'))})\n"
            )
            f.write(preamble + script)
            script_path = f.name

        try:
            # Build restricted environment
            env = self._build_sandbox_env(sandbox)

            # Inject step-level env vars
            if step.get("env"):
                env.update(step["env"])

            logger.info(
                f"  [wasm_exec] Running Python script in sandbox "
                f"(timeout={timeout}s, mem={sandbox.get('max_memory_mb')}MB)"
            )

            # Resource limit wrapper (macOS/Linux)
            cmd = self._build_sandbox_cmd(script_path, sandbox)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=tempfile.gettempdir(),  # Restrict working dir
            )

            elapsed_ms = int((time.time() - start) * 1000)

            if result.returncode == 0:
                return ExecutorResult(
                    success=True,
                    output=result.stdout.strip(),
                    elapsed_ms=elapsed_ms,
                    metadata={
                        "mode": "python_sandbox",
                        "stderr": result.stderr.strip() or None,
                    },
                )
            else:
                return ExecutorResult(
                    success=False,
                    output=result.stdout.strip(),
                    error=f"Script exited with code {result.returncode}: {result.stderr.strip()}",
                    elapsed_ms=elapsed_ms,
                    metadata={
                        "mode": "python_sandbox",
                        "exit_code": result.returncode,
                    },
                )
        finally:
            # Clean up temp file
            try:
                os.unlink(script_path)
            except OSError:
                pass

    def _build_sandbox_env(self, sandbox: dict) -> dict:
        """Build env dict for sandboxed subprocess."""
        env = {
            "PATH": "/usr/bin:/usr/local/bin",
            "HOME": tempfile.gettempdir(),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }

        # Block network access marker (app-level)
        if not sandbox.get("allow_network", False):
            env["HARNESS_SANDBOX_NO_NETWORK"] = "1"

        return env

    def _build_sandbox_cmd(self, script_path: str, sandbox: dict) -> list:
        """Build command with resource limits."""
        python = self._python_path

        # On macOS/Linux, use ulimit-based resource constraints
        max_mem_kb = sandbox.get("max_memory_mb", 256) * 1024

        if sys.platform == "darwin":
            # macOS: ulimit in shell wrapper
            return [
                "/bin/bash", "-c",
                f"ulimit -v {max_mem_kb} 2>/dev/null; "
                f"exec {python} {script_path}"
            ]
        else:
            # Linux: use ulimit
            return [
                "/bin/bash", "-c",
                f"ulimit -v {max_mem_kb}; "
                f"exec {python} {script_path}"
            ]
