"""Tests for ContainerExecutor — Docker sandbox execution (mocked)."""
import pytest
from unittest.mock import MagicMock, patch

from src.app.harness.executors.container_executor import ContainerExecutor


# ── Fixtures ─────────────────────────────────
@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client with configurable container behavior."""
    client = MagicMock()
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.side_effect = lambda stdout=True, stderr=False: (
        b"Hello from container\n" if stdout else b""
    )
    container.remove.return_value = None
    client.containers.run.return_value = container
    return client, container


@pytest.fixture
def dummy_context():
    return {"env": {"GLOBAL_VAR": "1"}, "_meta": {"run_id": "cnt-001"}}


@pytest.fixture
def container_step():
    return {
        "id": "test_container",
        "type": "container_exec",
        "image": "python:3.11-slim",
        "command": "python -c 'print(42)'",
        "timeout": 60,
    }


# ── Success ──────────────────────────────────
class TestContainerSuccess:

    def test_basic_execution(self, mock_docker_client, container_step, dummy_context):
        client, container = mock_docker_client
        executor = ContainerExecutor(docker_client=client)

        result = executor.execute(container_step, dummy_context)

        assert result.success is True
        assert "Hello from container" in result.output
        assert result.metadata["exit_code"] == 0
        assert result.metadata["image"] == "python:3.11-slim"

        # Verify Docker API was called correctly
        client.containers.run.assert_called_once()
        call_kwargs = client.containers.run.call_args
        assert call_kwargs[1]["image"] == "python:3.11-slim"
        assert call_kwargs[1]["detach"] is True

    def test_env_merged_from_context(self, mock_docker_client, dummy_context):
        client, _ = mock_docker_client
        executor = ContainerExecutor(docker_client=client)
        step = {
            "id": "env_test",
            "type": "container_exec",
            "image": "alpine",
            "command": "env",
            "env": {"STEP_VAR": "hello"},
        }
        executor.execute(step, dummy_context)
        call_kwargs = client.containers.run.call_args[1]
        assert call_kwargs["environment"]["GLOBAL_VAR"] == "1"
        assert call_kwargs["environment"]["STEP_VAR"] == "hello"


# ── Failure ──────────────────────────────────
class TestContainerFailure:

    def test_nonzero_exit(self, mock_docker_client, container_step, dummy_context):
        client, container = mock_docker_client
        container.wait.return_value = {"StatusCode": 1}
        container.logs.side_effect = lambda stdout=True, stderr=False: (
            b"output\n" if stdout else b"Error: file not found\n"
        )
        executor = ContainerExecutor(docker_client=client)

        result = executor.execute(container_step, dummy_context)

        assert result.success is False
        assert "exited with code 1" in result.error
        assert result.metadata["exit_code"] == 1

    def test_docker_unavailable(self, container_step, dummy_context):
        """When Docker SDK can't connect, return graceful fallback."""
        executor = ContainerExecutor(docker_client=None)
        # _get_docker_client will fail because docker daemon isn't available in test
        with patch(
            "src.app.harness.executors.container_executor._get_docker_client",
            side_effect=RuntimeError("Cannot connect to Docker daemon"),
        ):
            result = executor.execute(container_step, dummy_context)

        assert result.success is False
        assert "Docker unavailable" in result.error
        assert result.metadata.get("fallback") is True

    def test_timeout_exception(self, mock_docker_client, container_step, dummy_context):
        client, container = mock_docker_client
        container.wait.side_effect = Exception("Container timed out")
        executor = ContainerExecutor(docker_client=client)

        result = executor.execute(container_step, dummy_context)

        assert result.success is False
        assert "Container execution failed" in result.error


# ── Validation ───────────────────────────────
class TestContainerValidation:

    def test_missing_image(self):
        executor = ContainerExecutor()
        err = executor.validate({"id": "x", "type": "container_exec", "command": "ls"})
        assert err is not None
        assert "image" in err

    def test_missing_command(self):
        executor = ContainerExecutor()
        err = executor.validate({"id": "x", "type": "container_exec", "image": "alpine"})
        assert err is not None
        assert "command" in err

    def test_valid_step(self):
        executor = ContainerExecutor()
        err = executor.validate({
            "id": "x",
            "type": "container_exec",
            "image": "python:3.11",
            "command": "python main.py",
        })
        assert err is None
