"""Tests for Agent Registry — verifying autonomous agent management."""
import pytest

from src.app.harness.agents import (
    AgentProfile,
    AgentRegistry,
    create_default_agent_registry,
)


@pytest.fixture
def empty_registry():
    return AgentRegistry()


@pytest.fixture
def default_registry():
    return create_default_agent_registry()


class TestAgentProfile:

    def test_profile_initialization(self):
        agent = AgentProfile(
            agent_id="test_id",
            role="Tester",
            description="A test agent",
            domains={"test"},
        )
        assert agent.agent_id == "test_id"
        assert agent.role == "Tester"
        assert not agent.is_external

    def test_is_external(self):
        agent = AgentProfile(
            agent_id="ext",
            role="Ext",
            description="External",
            endpoint_url="https://api.test.local/webhook"
        )
        assert agent.is_external is True


class TestAgentRegistry:

    def test_register_and_get(self, empty_registry):
        agent = AgentProfile(agent_id="alpha", role="A", description="A agent")
        empty_registry.register(agent)
        
        found = empty_registry.get("alpha")
        assert found is not None
        assert found.role == "A"
        
        not_found = empty_registry.get("beta")
        assert not_found is None

    def test_unregister(self, empty_registry):
        agent = AgentProfile(agent_id="alpha", role="A", description="A agent")
        empty_registry.register(agent)
        empty_registry.unregister("alpha")
        assert empty_registry.get("alpha") is None

    def test_list_all(self, empty_registry):
        empty_registry.register(AgentProfile("a", "A", "A"))
        empty_registry.register(AgentProfile("b", "B", "B"))
        
        all_agents = empty_registry.list_all()
        assert len(all_agents) == 2
        ids = {a.agent_id for a in all_agents}
        assert ids == {"a", "b"}

    def test_find_by_domain(self, empty_registry):
        a1 = AgentProfile("eng1", "Eng", "E", domains={"engineering", "ops"})
        a2 = AgentProfile("mkt1", "Mkt", "M", domains={"marketing"})
        a3 = AgentProfile("generic", "Gen", "G", domains=set())  # Generic applies everywhere
        
        empty_registry.register(a1)
        empty_registry.register(a2)
        empty_registry.register(a3)
        
        eng_agents = empty_registry.find_by_domain("engineering")
        ids = {a.agent_id for a in eng_agents}
        assert ids == {"eng1", "generic"}
        
        mkt_agents = empty_registry.find_by_domain("marketing")
        mkt_ids = {a.agent_id for a in mkt_agents}
        assert mkt_ids == {"mkt1", "generic"}

    def test_find_by_tool(self, empty_registry):
        empty_registry.register(AgentProfile("coder", "Code", "C", allowed_tools={"code", "container_exec"}))
        empty_registry.register(AgentProfile("api", "Api", "A", allowed_tools={"api_call"}))
        empty_registry.register(AgentProfile("super", "God", "G", allowed_tools=set()))  # allowed all tools
        
        res = empty_registry.find_by_tool("code")
        ids = set(a.agent_id for a in res)
        assert ids == {"coder", "super"}
        
        res2 = empty_registry.find_by_tool("webhook")
        ids2 = set(a.agent_id for a in res2)
        assert ids2 == {"super"}


class TestDefaultRegistry:

    def test_default_agents_present(self, default_registry):
        all_agents = default_registry.list_all()
        assert len(all_agents) == 3
        
        planner = default_registry.get("sys_planner")
        assert planner is not None
        assert "parallel" in planner.allowed_tools
        
        coder = default_registry.get("sys_coder")
        assert coder is not None
        assert "container_exec" in coder.allowed_tools
