"""
Tests for WasmExecutor — sandbox script execution.
"""
import pytest
from src.app.harness.executors.wasm_executor import WasmExecutor


class TestWasmExecutor:
    """Test the WasmExecutor sandbox modes."""

    def setup_method(self):
        self.executor = WasmExecutor()

    def test_simple_script_execution(self):
        """Python script runs in sandbox and captures stdout."""
        step = {
            "id": "test_wasm",
            "type": "wasm_exec",
            "script": "print('hello from sandbox')",
            "sandbox": {"timeout_seconds": 10},
        }
        result = self.executor.execute(step, {})
        assert result.success is True
        assert "hello from sandbox" in result.output
        assert result.metadata.get("mode") == "python_sandbox"

    def test_script_with_computation(self):
        """Script that does actual computation."""
        step = {
            "id": "compute",
            "type": "wasm_exec",
            "script": "import json; print(json.dumps({'sum': sum(range(100))}))",
            "sandbox": {"timeout_seconds": 10},
        }
        result = self.executor.execute(step, {})
        assert result.success is True
        assert "4950" in result.output

    def test_script_timeout(self):
        """Script that exceeds timeout is killed."""
        step = {
            "id": "slow",
            "type": "wasm_exec",
            "script": "import time; time.sleep(30)",
            "sandbox": {"timeout_seconds": 2},
        }
        result = self.executor.execute(step, {})
        assert result.success is False
        assert "timeout" in result.error.lower() or "timed out" in result.error.lower()

    def test_script_error_captured(self):
        """Script with runtime error returns failure."""
        step = {
            "id": "error_script",
            "type": "wasm_exec",
            "script": "raise ValueError('intentional error')",
            "sandbox": {"timeout_seconds": 10},
        }
        result = self.executor.execute(step, {})
        assert result.success is False
        assert result.elapsed_ms >= 0

    def test_validate_missing_fields(self):
        """Validation catches missing script/module."""
        step = {"id": "empty", "type": "wasm_exec"}
        error = self.executor.validate(step)
        assert error is not None
        assert "requires" in error

    def test_validate_valid_script(self):
        """Validation passes for valid script step."""
        step = {"id": "ok", "type": "wasm_exec", "script": "print('ok')"}
        error = self.executor.validate(step)
        assert error is None


class TestContainerWasmFallback:
    """Test ContainerExecutor falls back to WasmExecutor."""

    def test_docker_unavailable_triggers_fallback(self):
        """When Docker daemon is not reachable, container_exec falls back to Wasm."""
        from unittest.mock import patch
        from src.app.harness.executors.container_executor import ContainerExecutor

        executor = ContainerExecutor()
        step = {
            "id": "fallback_test",
            "type": "container_exec",
            "image": "python:3.11-slim",
            "command": "print('fallback worked')",
            "timeout": 10,
        }

        # Mock _get_client to raise RuntimeError (Docker unavailable)
        with patch.object(executor, "_get_client", side_effect=RuntimeError("Docker not installed")):
            result = executor.execute(step, {})

        # Should have fallen back to Wasm
        assert "fallback" in result.metadata
        if result.success:
            assert result.metadata["fallback"] == "wasm"
        else:
            assert result.metadata.get("fallback") == "wasm"
