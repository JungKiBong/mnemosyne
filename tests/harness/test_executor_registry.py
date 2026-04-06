"""Tests for Executor Registry & built-in executors."""
import pytest
from unittest.mock import patch, MagicMock

from src.app.harness.executors import (
    BaseExecutor,
    ExecutorResult,
    ExecutorRegistry,
    LocalCodeExecutor,
    ApiCallExecutor,
    WebhookExecutor,
    create_default_registry,
)


# ── Fixtures ─────────────────────────────────
@pytest.fixture
def registry():
    return create_default_registry()


@pytest.fixture
def dummy_context():
    return {"env": {"TEST": "1"}, "_meta": {"run_id": "test-001"}}


# ── Registry basics ─────────────────────────
class TestExecutorRegistry:

    def test_default_registry_has_builtins(self, registry):
        assert registry.has("code")
        assert registry.has("api_call")
        assert registry.has("webhook")
        assert not registry.has("nonexistent")

    def test_list_types(self, registry):
        types = registry.list_types()
        assert set(types) == {"code", "api_call", "webhook", "hitl_gate", "ray", "nomad", "container_exec", "wasm_exec"}

    def test_register_custom_executor(self, registry):
        class CustomExec(BaseExecutor):
            executor_type = "custom"
            def execute(self, step, context):
                return ExecutorResult(success=True, output="custom-result")

        registry.register("custom", CustomExec())
        assert registry.has("custom")
        result = registry.execute("custom", {}, {})
        assert result.success is True
        assert result.output == "custom-result"

    def test_unregister(self, registry):
        registry.unregister("webhook")
        assert not registry.has("webhook")

    def test_execute_unknown_raises(self, registry):
        with pytest.raises(KeyError, match="nonexistent"):
            registry.execute("nonexistent", {}, {})

    def test_get_returns_none_for_unknown(self, registry):
        assert registry.get("nonexistent") is None

    def test_get_returns_executor_instance(self, registry):
        executor = registry.get("code")
        assert isinstance(executor, LocalCodeExecutor)


# ── Built-in executors ──────────────────────
class TestLocalCodeExecutor:

    @patch("src.app.harness.harness_runtime._exec_code")
    def test_success(self, mock_exec, dummy_context):
        mock_exec.return_value = {"result": 42}
        executor = LocalCodeExecutor()
        result = executor.execute({"id": "t1", "type": "code"}, dummy_context)
        assert result.success is True
        assert result.output == {"result": 42}
        assert result.elapsed_ms >= 0

    @patch("src.app.harness.harness_runtime._exec_code")
    def test_failure(self, mock_exec, dummy_context):
        mock_exec.side_effect = RuntimeError("code failed")
        executor = LocalCodeExecutor()
        result = executor.execute({"id": "t1", "type": "code"}, dummy_context)
        assert result.success is False
        assert "code failed" in result.error


class TestApiCallExecutor:

    @patch("src.app.harness.harness_runtime._exec_api_call")
    def test_success(self, mock_exec, dummy_context):
        mock_exec.return_value = {"status": 200}
        executor = ApiCallExecutor()
        result = executor.execute({"id": "t1", "type": "api_call"}, dummy_context)
        assert result.success is True
        assert result.output == {"status": 200}

    @patch("src.app.harness.harness_runtime._exec_api_call")
    def test_failure(self, mock_exec, dummy_context):
        mock_exec.side_effect = ConnectionError("timeout")
        executor = ApiCallExecutor()
        result = executor.execute({"id": "t1", "type": "api_call"}, dummy_context)
        assert result.success is False


class TestWebhookExecutor:

    @patch("src.app.harness.harness_runtime._exec_webhook")
    def test_success(self, mock_exec, dummy_context):
        mock_exec.return_value = {"delivered": True}
        executor = WebhookExecutor()
        result = executor.execute({"id": "t1", "type": "webhook"}, dummy_context)
        assert result.success is True


# ── ExecutorResult ──────────────────────────
class TestExecutorResult:

    def test_default_values(self):
        r = ExecutorResult(success=True)
        assert r.output is None
        assert r.error is None
        assert r.elapsed_ms == 0
        assert r.metadata == {}

    def test_full_values(self):
        r = ExecutorResult(
            success=False,
            output="data",
            error="oops",
            elapsed_ms=123,
            metadata={"tool": "docker"},
        )
        assert r.success is False
        assert r.elapsed_ms == 123
        assert r.metadata["tool"] == "docker"
