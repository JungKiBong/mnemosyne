"""Tests for DSL v4 JSON schema validation."""
import json
import os
import pytest

SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../src/app/harness/workflow_dsl_schema.json",
)
FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "../fixtures/v4_scenario_complex.json")


@pytest.fixture
def schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


@pytest.fixture
def fixture_scenario():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def test_schema_loads_cleanly(schema):
    """Schema should be valid JSON with expected top-level keys."""
    assert schema["title"] == "Mories Harness v4 Workflow DSL"
    assert "definitions" in schema
    assert "step" in schema["definitions"]


def test_schema_has_all_executor_types(schema):
    """Step type enum should include all v4 executor types."""
    step_types = schema["definitions"]["step"]["properties"]["type"]["enum"]
    expected = {"code", "api_call", "webhook", "branch", "loop", "parallel",
                "wait", "end", "container_exec", "hitl_gate", "ray", "nomad", "wasm_exec"}
    assert set(step_types) == expected


def test_schema_defines_sandbox(schema):
    """Sandbox definition should have memory and timeout constraints."""
    sandbox = schema["definitions"]["sandbox"]["properties"]
    assert "max_memory_mb" in sandbox
    assert "timeout_seconds" in sandbox
    assert "allow_network" in sandbox


def test_schema_defines_nomad_job_spec(schema):
    """Nomad job spec should define name, image, command, cpu, memory."""
    nomad = schema["definitions"]["nomad_job_spec"]["properties"]
    assert "name" in nomad
    assert "command" in nomad
    assert "cpu" in nomad


def test_schema_defines_ray_parameters(schema):
    """Ray parameters should define num_cpus and memory."""
    ray = schema["definitions"]["ray_parameters"]["properties"]
    assert "num_cpus" in ray
    assert "memory" in ray


def test_fixture_scenario_has_required_fields(fixture_scenario):
    """Complex scenario should have harness_id, domain, steps."""
    assert "harness_id" in fixture_scenario or "scenario_id" in fixture_scenario
    assert "domain" in fixture_scenario
    assert "steps" in fixture_scenario
    assert len(fixture_scenario["steps"]) >= 1


def test_fixture_step_types_are_valid(schema, fixture_scenario):
    """All steps in fixture should have types from the schema enum."""
    valid_types = set(schema["definitions"]["step"]["properties"]["type"]["enum"])
    for step in fixture_scenario["steps"]:
        assert step.get("type") in valid_types, (
            f"Step '{step.get('id')}' has invalid type '{step.get('type')}'"
        )


def test_schema_jsonschema_validation():
    """If jsonschema is available, validate fixture against schema."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
        return

    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    with open(FIXTURE_PATH) as f:
        scenario = json.load(f)

    # Should not raise
    jsonschema.validate(instance=scenario, schema=schema)
