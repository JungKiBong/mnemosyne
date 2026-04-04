"""
Harness Executor Framework (v4)

Pluggable executor system for the Harness Runtime engine.
Maps step types → executor implementations for local, container, Ray, and remote execution.
"""

from __future__ import annotations

import importlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 1. Executor Result
# ──────────────────────────────────────────────
@dataclass
class ExecutorResult:
    """Standardised outcome of every executor call."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    elapsed_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────
# 2. Base Executor
# ──────────────────────────────────────────────
class BaseExecutor(ABC):
    """
    Abstract base for all step executors.

    Subclasses implement `execute()` and optionally override `validate()`.
    """

    executor_type: str = "base"

    @abstractmethod
    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        """
        Execute a single step.

        Args:
            step: step definition from the workflow DSL
            context: mutable runtime context dict

        Returns:
            ExecutorResult with outcome
        """
        ...

    def validate(self, step: dict) -> Optional[str]:
        """
        Validate step config before execution.
        Returns error string if invalid, else None.
        """
        return None


# ──────────────────────────────────────────────
# 3. Built-in Executors (wrap legacy helpers)
# ──────────────────────────────────────────────
class LocalCodeExecutor(BaseExecutor):
    """Runs a Python callable specified by module + function path."""

    executor_type = "code"

    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        from src.app.harness.harness_runtime import _exec_code
        start = time.time()
        try:
            result = _exec_code(step, context)
            return ExecutorResult(
                success=True,
                output=result,
                elapsed_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return ExecutorResult(
                success=False,
                error=str(e),
                elapsed_ms=int((time.time() - start) * 1000),
            )


class ApiCallExecutor(BaseExecutor):
    """Calls an external REST API."""

    executor_type = "api_call"

    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        from src.app.harness.harness_runtime import _exec_api_call
        start = time.time()
        try:
            result = _exec_api_call(step, context)
            return ExecutorResult(
                success=True,
                output=result,
                elapsed_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return ExecutorResult(
                success=False,
                error=str(e),
                elapsed_ms=int((time.time() - start) * 1000),
            )


class WebhookExecutor(BaseExecutor):
    """Fires a webhook (n8n / Zapier / generic)."""

    executor_type = "webhook"

    def execute(self, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        from src.app.harness.harness_runtime import _exec_webhook
        start = time.time()
        try:
            result = _exec_webhook(step, context)
            return ExecutorResult(
                success=True,
                output=result,
                elapsed_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return ExecutorResult(
                success=False,
                error=str(e),
                elapsed_ms=int((time.time() - start) * 1000),
            )


# ──────────────────────────────────────────────
# 4. Executor Registry
# ──────────────────────────────────────────────
class ExecutorRegistry:
    """
    Pluggable registry that maps `step_type` → `BaseExecutor` instance.

    Usage:
        registry = ExecutorRegistry()
        registry.register("code", LocalCodeExecutor())
        result = registry.execute("code", step, context)
    """

    def __init__(self):
        self._executors: Dict[str, BaseExecutor] = {}

    # ── Registration ──
    def register(self, step_type: str, executor: BaseExecutor) -> None:
        self._executors[step_type] = executor
        logger.debug(f"Registered executor: {step_type} → {executor.__class__.__name__}")

    def unregister(self, step_type: str) -> None:
        self._executors.pop(step_type, None)

    def has(self, step_type: str) -> bool:
        return step_type in self._executors

    def get(self, step_type: str) -> Optional[BaseExecutor]:
        return self._executors.get(step_type)

    def list_types(self) -> list:
        return list(self._executors.keys())

    # ── Execution ──
    def execute(self, step_type: str, step: dict, context: Dict[str, Any]) -> ExecutorResult:
        """Look up executor and run. Raises KeyError if step_type unknown."""
        executor = self._executors.get(step_type)
        if executor is None:
            raise KeyError(f"No executor registered for step_type '{step_type}'")
        return executor.execute(step, context)


# ──────────────────────────────────────────────
# 5. Default Registry Factory
# ──────────────────────────────────────────────
def create_default_registry() -> ExecutorRegistry:
    """
    Create an ExecutorRegistry pre-loaded with all built-in executors.

    Returns:
        ExecutorRegistry with code, api_call, webhook executors registered.
    """
    registry = ExecutorRegistry()
    registry.register("code", LocalCodeExecutor())
    registry.register("api_call", ApiCallExecutor())
    registry.register("webhook", WebhookExecutor())
    return registry
