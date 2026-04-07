import pytest
from unittest.mock import patch, MagicMock
from src.app.harness.executors.nomad_executor import NomadExecutor
import requests


class TestNomadExecutor:

    def setup_method(self):
        self.executor = NomadExecutor(nomad_addr="http://fake-nomad:4646")

    def test_validate_missing_name(self):
        step = {"type": "nomad", "job_spec": {}}
        err = self.executor.validate(step)
        assert "requires job_spec.name" in err

    def test_validate_success(self):
        step = {"type": "nomad", "job_spec": {"name": "test-job"}}
        err = self.executor.validate(step)
        assert err is None

    @patch("requests.post")
    @patch("requests.get")
    @patch("requests.delete")
    def test_execute_success(self, mock_delete, mock_get, mock_post):
        # Mocks
        mock_delete.return_value = MagicMock(status_code=200)

        # Submit job response
        mock_post_resp = MagicMock(status_code=200)
        mock_post.return_value = mock_post_resp

        # Poll allocs response
        mock_get_allocs = MagicMock(status_code=200)
        mock_get_allocs.json.return_value = [{"ID": "alloc-123", "ClientStatus": "complete"}]
        
        # Get logs response
        mock_get_logs = MagicMock(status_code=200, text="hello from nomad\n")

        # Configure get side_effect based on URL
        def get_side_effect(url, *args, **kwargs):
            if "/allocations" in url:
                return mock_get_allocs
            elif "/logs/" in url:
                return mock_get_logs
            return MagicMock(status_code=404)
        mock_get.side_effect = get_side_effect

        step = {
            "type": "nomad",
            "job_spec": {"name": "hello-job", "command": "echo 'hi'"},
            "timeout": 10
        }

        result = self.executor.execute(step, {})

        assert result.success is True
        assert "hello from nomad" in result.output
        assert result.metadata["alloc_id"] == "alloc-123"

    @patch("requests.post")
    @patch("requests.get")
    @patch("requests.delete")
    def test_execute_failed_job(self, mock_delete, mock_get, mock_post):
        mock_delete.return_value = MagicMock(status_code=200)
        mock_post.return_value = MagicMock(status_code=200)

        mock_get_allocs = MagicMock(status_code=200)
        mock_get_allocs.json.return_value = [{"ID": "alloc-fail", "ClientStatus": "failed"}]
        
        mock_get_logs = MagicMock(status_code=200, text="exit code 1")

        def get_side_effect(url, *args, **kwargs):
            if "/allocations" in url:
                return mock_get_allocs
            elif "/logs/" in url:
                return mock_get_logs
            return MagicMock(status_code=200)
        mock_get.side_effect = get_side_effect

        step = {"type": "nomad", "job_spec": {"name": "fail-job"}, "timeout": 10}
        result = self.executor.execute(step, {})

        assert result.success is False
        assert "failed" in result.error
        assert "exit code 1" in result.output

    @patch("requests.post")
    @patch("requests.delete")
    def test_execute_connection_error(self, mock_delete, mock_post):
        mock_delete.side_effect = requests.ConnectionError("Could not connect")
        mock_post.side_effect = requests.ConnectionError("Could not connect")
        
        step = {"type": "nomad", "job_spec": {"name": "conn-job"}, "timeout": 10}
        result = self.executor.execute(step, {})

        assert result.success is False
        assert "Cannot connect to Nomad" in result.error
