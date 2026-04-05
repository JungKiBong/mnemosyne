"""
Mories Harness - Multi-Agent Registry

Provides a central registry for defining and managing autonomous agents.
Agents can be standard LLM personas, specialized micro-bots, or external
orchestration endpoints (e.g., n8n workflows, Dify agents) that the Harness
Engine can delegate tasks to dynamically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 1. Agent Profile
# ──────────────────────────────────────────────
@dataclass
class AgentProfile:
    """
    Defines the identity, capabilities, and instructions of a specific agent.
    """
    agent_id: str
    role: str
    description: str
    
    # System instructions or specific prompting context for the agent
    system_instruction: str = ""
    
    # What specific action types or executor types this agent is allowed to request/perform
    allowed_tools: Set[str] = field(default_factory=set)
    
    # Domains or scopes where this agent is competent (e.g. "engineering", "qa")
    domains: Set[str] = field(default_factory=set)
    
    # An optional webhook/API endpoint if this agent runs externally
    endpoint_url: Optional[str] = None
    
    @property
    def is_external(self) -> bool:
        """Determines if this agent delegates to an external service."""
        return self.endpoint_url is not None


# ──────────────────────────────────────────────
# 2. Agent Registry
# ──────────────────────────────────────────────
class AgentRegistry:
    """
    Central repository tracking available autonomous agents.
    Allows the planner to discover and assign tasks based on domains and capabilities.
    """

    def __init__(self):
        self._agents: Dict[str, AgentProfile] = {}

    def register(self, agent: AgentProfile) -> None:
        """Register a new active agent."""
        self._agents[agent.agent_id] = agent
        logger.debug(f"Registered agent: {agent.agent_id} (Role: {agent.role})")

    def unregister(self, agent_id: str) -> None:
        """Remove an agent by ID."""
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> Optional[AgentProfile]:
        """Fetch an agent by ID."""
        return self._agents.get(agent_id)

    def list_all(self) -> List[AgentProfile]:
        """List all registered agents."""
        return list(self._agents.values())

    def find_by_domain(self, domain: str) -> List[AgentProfile]:
        """Discover agents capable of working in a specific domain."""
        # Agents with no domain are considered generic/global
        return [
            a for a in self._agents.values()
            if domain in a.domains or not a.domains
        ]

    def find_by_tool(self, tool_type: str) -> List[AgentProfile]:
        """Discover agents permitted to use a specific tool/action type."""
        return [
            a for a in self._agents.values()
            if tool_type in a.allowed_tools or not a.allowed_tools
        ]


# ──────────────────────────────────────────────
# 3. Default Registry Factory
# ──────────────────────────────────────────────
def create_default_agent_registry() -> AgentRegistry:
    """
    Produce a default registry with some baseline system agents
    for out-of-the-box autonomous operations.
    """
    registry = AgentRegistry()
    
    # 1. Base Planner Agent
    registry.register(AgentProfile(
        agent_id="sys_planner",
        role="Master Planner",
        description="Analyzes goals and breaks them into tasks. Identifies dependencies.",
        system_instruction="You are a system planner. Output strictly structured workflow graphs.",
        allowed_tools={"parallel", "branch", "loop"},
        domains={"global"}
    ))
    
    # 2. Base Coder Agent
    registry.register(AgentProfile(
        agent_id="sys_coder",
        role="Code Execution Expert",
        description="Writes and refines python code nodes.",
        system_instruction="Write robust, sandboxed Python code. Avoid side effects where possible.",
        allowed_tools={"code", "container_exec"},
        domains={"engineering", "data_science"}
    ))
    
    # 3. Base API Integrator
    registry.register(AgentProfile(
        agent_id="sys_integrator",
        role="External API Specialist",
        description="Configures REST and Webhook payloads.",
        system_instruction="Map inputs to JSON API payloads safely and validate responses.",
        allowed_tools={"api_call", "webhook"},
        domains={"ops", "engineering"}
    ))

    return registry
