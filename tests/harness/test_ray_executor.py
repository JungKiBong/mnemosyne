import pytest
from unittest.mock import patch, MagicMock
from src.app.harness.executors.ray_executor import RayExecutor

class TestRayExecutor:
    @patch("src.app.harness.executors.ray_executor._get_ray")
    def test_ray_initialization(self, mock_get_ray):
        mock_ray = MagicMock()
        mock_ray.is_initialized.return_value = False
        mock_get_ray.return_value = mock_ray
        
        executor = RayExecutor()
        assert executor._ray is mock_ray
        
        # Test connecting to cluster
        executor._ensure_connected()
        mock_ray.init.assert_called_once()
    
    @patch("src.app.harness.executors.ray_executor._get_ray")
    def test_ray_execute_success(self, mock_get_ray):
        mock_ray = MagicMock()
        mock_ray.is_initialized.return_value = True
        mock_get_ray.return_value = mock_ray
        
        executor = RayExecutor()
        
        # Setup mock for self._ray.remote decorator and remote function
        mock_remote_wrapper = MagicMock()
        mock_remote_func = MagicMock()
        mock_remote_wrapper.return_value = mock_remote_func
        mock_ray.remote.return_value = mock_remote_wrapper
        
        # Setup wait and get
        mock_ray.wait.return_value = ([MagicMock()], [])  # ready, not_ready
        mock_ray.get.return_value = {"status": "success", "data": "output_value"}
        
        step = {
            "script": "def run(ctx):\n    return {'status': 'ok'}",
            "timeout": 10
        }
        result = executor.execute(step, {})
        
        assert result.success is True
        assert result.output["status"] == "success"
        mock_ray.wait.assert_called_once()
        mock_ray.get.assert_called_once()

    @patch("src.app.harness.executors.ray_executor._get_ray")
    def test_ray_execute_timeout(self, mock_get_ray):
        mock_ray = MagicMock()
        mock_ray.is_initialized.return_value = True
        mock_get_ray.return_value = mock_ray
        
        executor = RayExecutor()
        
        mock_remote_wrapper = MagicMock()
        mock_remote_wrapper.return_value = MagicMock()
        mock_ray.remote.return_value = mock_remote_wrapper
        
        # Setup wait to return empty ready list
        mock_ray.wait.return_value = ([], [MagicMock()])  # ready, not_ready
        
        step = {
            "script": "def run(ctx):\n    return {'status': 'ok'}",
            "timeout": 2
        }
        result = executor.execute(step, {})
        
        assert result.success is False
        assert "timed out" in result.error
        
    def test_ray_simulate_fallback(self):
        # We don't mock get_ray, if Ray is not installed it should fallback
        # If it is installed, we mock is_initialized to False
        with patch("src.app.harness.executors.ray_executor._get_ray") as mock_get_ray:
            mock_ray = MagicMock()
            mock_ray.is_initialized.return_value = False
            # Make init fail to force simulation
            mock_ray.init.side_effect = RuntimeError("Failed to connect")
            mock_get_ray.return_value = mock_ray
            
            executor = RayExecutor()
            step = {"script": "def run(ctx): pass"}
            result = executor.execute(step, {})
            
            assert result.success is True
            assert result.output["status"] == "ray_simulated"
