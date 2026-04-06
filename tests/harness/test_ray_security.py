import pytest
from src.app.harness.executors.ray_executor import RayExecutor

def test_ray_ast_security_blocks_os():
    executor = RayExecutor()
    evil_script = """
import os
def run(ctx):
    os.system('echo "hacked"')
    return {"status": "bad"}
"""
    result = executor.execute({"script": evil_script}, {})
    assert not result.success
    assert "Security Policy Violation" in result.error
    assert "Blocked AST node Import" in result.error

def test_ray_ast_security_allows_safe_code():
    executor = RayExecutor()
    safe_script = """
def run(ctx):
    return {"status": "ok", "value": 42}
"""
    result = executor.execute({"script": safe_script}, {})
    assert result.success
    if result.output.get("status") == "ray_simulated":
        assert "status" in result.output
    else:
        assert result.output.get("value") == 42
