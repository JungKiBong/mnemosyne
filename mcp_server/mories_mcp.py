#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║  Mories MCP Server — Shared Memory for Agents   ║
║  모든 에이전트가 하나의 기억을 공유하는 MCP 서버   ║
╚══════════════════════════════════════════════════╝

Usage:
  python mories_mcp.py                          # stdio mode (for MCP clients)
  MORIES_URL=http://host:5001 python mories_mcp.py  # custom server URL
"""

import os
import json
import logging
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
)

# ─── Configuration ────────────────────────────────
MORIES_URL = os.environ.get("MORIES_URL", "http://localhost:5001")
MORIES_API_KEY = os.environ.get("MORIES_API_KEY", "")
REQUEST_TIMEOUT = int(os.environ.get("MORIES_TIMEOUT", "30"))
AGENT_ID = os.environ.get("MORIES_AGENT_ID", "mcp-agent")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mories-mcp")

# ─── HTTP Client ──────────────────────────────────

def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if MORIES_API_KEY:
        h["Authorization"] = f"Bearer {MORIES_API_KEY}"
    return h


async def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Call Mories REST API and return JSON response."""
    url = f"{MORIES_URL}{path}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        if method == "GET":
            resp = await client.get(url, headers=_headers(), params=body)
        elif method == "POST":
            resp = await client.post(url, headers=_headers(), json=body or {})
        elif method == "DELETE":
            resp = await client.delete(url, headers=_headers())
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text}
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}


# ─── MCP Server ───────────────────────────────────

app = Server("mories")

# ─── Tool Definitions ────────────────────────────

TOOLS = [
    Tool(
        name="mories_search",
        description=(
            "Search the Mories knowledge graph for memories. "
            "Returns relevant facts, entities, and relationships matching the query. "
            "Use this to recall past decisions, bugs, architecture patterns, or any shared knowledge."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "limit": {"type": "integer", "description": "Max results (default: 10)", "default": 10},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="mories_ingest",
        description=(
            "Store new knowledge/memories into the Mories knowledge graph. "
            "Use this after completing tasks, discovering bugs, making architecture decisions, "
            "or any time you want to preserve context for future sessions. "
            "Content is automatically processed into entities, facts, and relationships."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Markdown-formatted content to store. Use structured format: Task, Decisions, Lessons, Next Steps.",
                },
                "source": {
                    "type": "string",
                    "description": "Source identifier (e.g. 'cursor_session', 'claude_desktop')",
                    "default": "mcp-agent",
                },
                "salience": {
                    "type": "number",
                    "description": "Importance score 0.0-1.0 (default: 0.7)",
                    "default": 0.7,
                },
                "scope": {
                    "type": "string",
                    "enum": ["personal", "tribal", "social", "global"],
                    "description": "Visibility scope (default: tribal)",
                    "default": "tribal",
                },
            },
            "required": ["content"],
        },
    ),
    Tool(
        name="mories_stm_add",
        description=(
            "Add content to Short-Term Memory (STM). "
            "STM entries are temporary and will expire unless promoted to LTM. "
            "Use for session context, working notes, or observations that may become important."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to store in STM"},
                "source": {"type": "string", "description": "Source identifier", "default": "mcp-agent"},
                "salience": {"type": "number", "description": "Importance 0.0-1.0", "default": 0.5},
            },
            "required": ["content"],
        },
    ),
    Tool(
        name="mories_stm_promote",
        description=(
            "Promote a Short-Term Memory entry to Long-Term Memory (LTM). "
            "Once promoted, the memory becomes permanent and is integrated into the knowledge graph."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "STM entry UUID to promote"},
            },
            "required": ["id"],
        },
    ),
    Tool(
        name="mories_memory_overview",
        description=(
            "Get an overview of the current memory state: total memories, "
            "STM/LTM counts, top entities, and health status."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="mories_memory_top",
        description=(
            "Get the top N most salient (important) memories. "
            "Useful for understanding what the system considers most critical."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of top memories (default: 10)", "default": 10},
            },
        },
    ),
    Tool(
        name="mories_graph_query",
        description=(
            "Execute a read-only Neo4j Cypher query against the knowledge graph. "
            "Use this for complex queries that go beyond simple search, "
            "e.g., finding relationships between entities, traversing connections, or aggregating data."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "cypher": {
                    "type": "string",
                    "description": "Neo4j Cypher query (read-only). Example: MATCH (e:Entity) RETURN e.name LIMIT 10",
                },
            },
            "required": ["cypher"],
        },
    ),
    Tool(
        name="mories_graph_list",
        description="List all available knowledge graphs (projects/workspaces).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="mories_synaptic_share",
        description=(
            "Share a memory between agents via the Synaptic Bridge. "
            "This enables cross-agent knowledge transfer — one agent's discovery "
            "becomes available to all connected agents."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "memory_uuid": {"type": "string", "description": "UUID of the memory to share"},
                "from_agent": {"type": "string", "description": "Sending agent ID"},
                "to_agent": {"type": "string", "description": "Receiving agent ID (or 'broadcast' for all)"},
                "context": {"type": "string", "description": "Why this memory is being shared"},
            },
            "required": ["memory_uuid", "from_agent", "to_agent"],
        },
    ),
    Tool(
        name="mories_synaptic_agents",
        description="List all agents registered in the Synaptic Bridge network.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="mories_permanent_imprint",
        description=(
            "Imprint a permanent, immutable memory that survives all decay cycles. "
            "Use for critical rules, security policies, core architecture decisions, "
            "or foundational knowledge that must never be forgotten."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to permanently imprint"},
                "category": {
                    "type": "string",
                    "enum": ["rule", "policy", "architecture", "identity", "custom"],
                    "description": "Category of permanent memory",
                    "default": "custom",
                },
                "scope": {
                    "type": "string",
                    "enum": ["personal", "tribal", "social", "global"],
                    "default": "tribal",
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority level 1-10 (10 = highest)",
                    "default": 5,
                },
            },
            "required": ["content"],
        },
    ),
    Tool(
        name="mories_record_preference",
        description="Record a user preference (e.g., 'always speak in Korean').",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain of the preference (e.g. 'communication', 'code_style')"},
                "preference_key": {"type": "string", "description": "Key identifier for the preference"},
                "preference_value": {"type": "string", "description": "The value of the preference"},
                "description": {"type": "string", "description": "Optional description/context"},
                "weight": {"type": "number", "default": 1.0, "description": "Importance weight"},
                "is_negative": {"type": "boolean", "default": False, "description": "Whether this is a negative preference (something to avoid)"},
            },
            "required": ["domain", "preference_key", "preference_value"],
        },
    ),
    Tool(
        name="mories_recall_preferences",
        description="Recall user preferences.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Optional domain filter"},
            },
        },
    ),
    Tool(
        name="mories_record_instruction",
        description="Record an instructional rule (e.g., 'write tests first').",
        inputSchema={
            "type": "object",
            "properties": {
                "rule": {"type": "string", "description": "The instructional rule"},
                "category": {"type": "string", "default": "general", "description": "Category of the rule"},
                "strictness": {"type": "string", "default": "should", "enum": ["must", "should", "suggested"]},
                "description": {"type": "string", "description": "Optional description/context"},
            },
            "required": ["rule"],
        },
    ),
    Tool(
        name="mories_recall_instructions",
        description="Recall instructional rules.",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional category filter"},
            },
        },
    ),
    Tool(
        name="mories_record_reflection",
        description="Record a reflection or lesson learned (e.g., to prevent repeating mistakes).",
        inputSchema={
            "type": "object",
            "properties": {
                "event": {"type": "string", "description": "The event that occurred"},
                "lesson": {"type": "string", "description": "The lesson learned from the event"},
                "domain": {"type": "string", "default": "general"},
                "severity": {"type": "string", "default": "low", "enum": ["low", "medium", "high", "critical"]},
                "description": {"type": "string"},
            },
            "required": ["event", "lesson"],
        },
    ),
    Tool(
        name="mories_recall_reflections",
        description="Recall previously learned reflections/lessons.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Optional domain filter"},
                "severity": {"type": "string", "description": "Optional severity filter"},
            },
        },
    ),
    Tool(
        name="mories_record_conditional",
        description="Record a conditional knowledge rule (e.g., 'If Python 3.9, do not use match').",
        inputSchema={
            "type": "object",
            "properties": {
                "condition": {"type": "object", "description": "JSON object representing the condition (e.g., {\"language\": \"python\", \"version\": \"<3.10\"})"},
                "then_action": {"type": "string", "description": "The action to take or fact that is true"},
                "else_action": {"type": "string", "description": "Optional action if false"},
                "description": {"type": "string", "description": "Optional summary"},
                "subcategory": {"type": "string", "default": "contextual"},
            },
            "required": ["condition", "then_action"],
        },
    ),
    Tool(
        name="mories_recall_conditionals",
        description="Recall conditional knowledge rules, optionally evaluating against a given context.",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {"type": "object", "description": "Optional context object to evaluate conditions against"},
                "subcategory": {"type": "string", "description": "Optional subcategory filter"},
            },
        },
    ),
    Tool(
        name="mories_health",
        description="Check Mories server health, Neo4j connection status, and node count.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="mories_harness_list",
        description="List all harness (evolutionary process) patterns, optionally filtered by domain.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Filter by domain (e.g., 'engineering')"},
                "agent_id": {"type": "string", "description": "Filter by agent ID", "default": "all"},
                "include_low_success": {"type": "boolean", "description": "Include patterns with low success rate", "default": False},
            },
        },
    ),
    Tool(
        name="mories_harness_overview",
        description="Dashboard overview: aggregated stats for harness patterns.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="mories_harness_detail",
        description="Get detailed info for a specific harness pattern.",
        inputSchema={
            "type": "object",
            "properties": {
                "uuid": {"type": "string", "description": "UUID of the harness pattern"},
            },
            "required": ["uuid"],
        },
    ),
    Tool(
        name="mories_harness_record",
        description="Record a new harness pattern.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain or context"},
                "trigger": {"type": "string", "description": "Condition or prompt that triggered the pattern"},
                "tool_chain": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of strings representing the tools used sequentially"
                },
                "description": {"type": "string"},
                "process_type": {"type": "string", "default": "pipeline"},
                "data_flow": {"type": "object"},
                "conditionals": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of objects like {'type': 'retry'|'fallback'|'handoff', 'condition': 'description', 'then_action': 'action'}"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "scope": {"type": "string", "default": "tribal"},
            },
            "required": ["domain", "trigger", "tool_chain"],
        },
    ),
    Tool(
        name="mories_harness_execute",
        description="Record an execution result for a harness pattern.",
        inputSchema={
            "type": "object",
            "properties": {
                "uuid": {"type": "string", "description": "UUID of the harness pattern"},
                "success": {"type": "boolean", "default": True},
                "execution_time_ms": {"type": "integer", "default": 0},
                "result_summary": {"type": "string", "description": "Summary of the execution result"},
                "new_tool_chain": {"type": "array", "items": {"type": "string"}, "description": "Optional new tool chain if the chain changed during execution"},
            },
            "required": ["uuid"],
        },
    ),
    Tool(
        name="mories_harness_evolve",
        description="Evolve a harness pattern with a new tool chain.",
        inputSchema={
            "type": "object",
            "properties": {
                "uuid": {"type": "string", "description": "UUID of the harness pattern"},
                "new_tool_chain": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The new sequence of tools"
                },
                "reason": {"type": "string", "description": "Reason for evolving the pattern"},
            },
            "required": ["uuid", "new_tool_chain", "reason"],
        },
    ),
    Tool(
        name="mories_harness_recommend",
        description="Recommend harness patterns based on a natural-language query. Returns scored results ranked by relevance, success rate, and execution frequency.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query describing the task or process (e.g. 'PR review automation')"},
                "domain": {"type": "string", "description": "Optional domain filter"},
                "cross_domain": {"type": "boolean", "default": True, "description": "Include results from other domains"},
                "limit": {"type": "integer", "default": 5, "description": "Max results to return"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="mories_harness_rollback",
        description="Manually rollback a harness pattern to a specific previous version. Creates a new version entry with the rolled-back tool chain.",
        inputSchema={
            "type": "object",
            "properties": {
                "uuid": {"type": "string", "description": "UUID of the harness pattern"},
                "to_version": {"type": "integer", "description": "Target version number to rollback to"},
            },
            "required": ["uuid", "to_version"],
        },
    ),
    Tool(
        name="mories_harness_generate",
        description="Use AI (LLM) to automatically generate a recommended harness tool_chain and conditionals based on natural language.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query describing the desired automation (e.g. 'PR review automation')"},
                "domain": {"type": "string", "description": "Optional domain context (default: 'general')"}
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="mories_harness_suggest_evolution",
        description="Use AI (LLM) to automatically suggest an evolved tool_chain and conditionals for an existing harness pattern that might have a low success rate.",
        inputSchema={
            "type": "object",
            "properties": {
                "uuid": {"type": "string", "description": "UUID of the harness pattern"},
                "context": {"type": "string", "description": "Optional context or reason for evolution (e.g. 'Fails often due to missing dependency')"}
            },
            "required": ["uuid"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route MCP tool calls to Mories REST API."""
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2, default=str),
        )]
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, ensure_ascii=False),
        )]


async def _dispatch(name: str, args: dict) -> dict:
    """Map tool names to REST API calls."""

    # ── Search ──
    if name == "mories_search":
        return await _api("POST", "/api/search", {
            "query": args["query"],
            "limit": args.get("limit", 10),
        })

    # ── Ingest (STM + promote to LTM) ──
    elif name == "mories_ingest":
        # Step 1: Add to STM
        stm = await _api("POST", "/api/memory/stm/add", {
            "content": args["content"],
            "source": args.get("source", AGENT_ID),
            "salience": args.get("salience", 0.7),
            "scope": args.get("scope", "tribal"),
        })
        if "error" in stm:
            return stm

        # Step 2: Auto-promote to LTM
        stm_id = stm.get("id")
        if stm_id:
            ltm = await _api("POST", "/api/memory/stm/promote", {"id": stm_id})
            return {
                "status": "ingested_and_promoted",
                "stm_id": stm_id,
                "ltm_uuid": ltm.get("ltm_uuid"),
                "content_preview": args["content"][:200],
            }
        return stm

    # ── STM Add ──
    elif name == "mories_stm_add":
        return await _api("POST", "/api/memory/stm/add", {
            "content": args["content"],
            "source": args.get("source", AGENT_ID),
            "salience": args.get("salience", 0.5),
        })

    # ── STM Promote ──
    elif name == "mories_stm_promote":
        return await _api("POST", "/api/memory/stm/promote", {"id": args["id"]})

    # ── Memory Overview ──
    elif name == "mories_memory_overview":
        return await _api("GET", "/api/memory/overview")

    # ── Memory Top ──
    elif name == "mories_memory_top":
        return await _api("GET", "/api/memory/top", {"limit": args.get("limit", 10)})

    # ── Graph Query ──
    elif name == "mories_graph_query":
        return await _api("POST", "/api/query", {"cypher": args["cypher"]})

    # ── Graph List ──
    elif name == "mories_graph_list":
        return await _api("GET", "/api/graphs")

    # ── Synaptic Share ──
    elif name == "mories_synaptic_share":
        return await _api("POST", "/api/synaptic/share", {
            "memory_uuid": args["memory_uuid"],
            "from_agent": args["from_agent"],
            "to_agent": args["to_agent"],
            "context": args.get("context", ""),
        })

    # ── Synaptic Agents ──
    elif name == "mories_synaptic_agents":
        return await _api("GET", "/api/synaptic/agents")

    # ── Permanent Imprint ──
    elif name == "mories_permanent_imprint":
        return await _api("POST", "/api/memory/permanent/imprint", {
            "content": args["content"],
            "category": args.get("category", "custom"),
            "scope": args.get("scope", "tribal"),
            "priority": args.get("priority", 5),
            "agent_id": AGENT_ID,
        })

    # ── Health ──
    elif name == "mories_health":
        return await _api("GET", "/api/health")

    # ── Cognitive Memory Categories ──
    elif name == "mories_record_preference":
        return await _api("POST", "/api/memory/category/preference", {
            "domain": args["domain"],
            "preference_key": args["preference_key"],
            "preference_value": args["preference_value"],
            "description": args.get("description", ""),
            "weight": args.get("weight", 1.0),
            "is_negative": args.get("is_negative", False),
            "agent_id": AGENT_ID,
        })
    elif name == "mories_recall_preferences":
        return await _api("GET", "/api/memory/category/preference", {
            "domain": args.get("domain"),
            "agent_id": AGENT_ID,
        })

    elif name == "mories_record_instruction":
        return await _api("POST", "/api/memory/category/instruction", {
            "rule": args["rule"],
            "category": args.get("category", "general"),
            "strictness": args.get("strictness", "should"),
            "description": args.get("description", ""),
            "agent_id": AGENT_ID,
        })
    elif name == "mories_recall_instructions":
        return await _api("GET", "/api/memory/category/instruction", {
            "category": args.get("category"),
            "agent_id": AGENT_ID,
        })

    elif name == "mories_record_reflection":
        return await _api("POST", "/api/memory/category/reflection", {
            "event": args["event"],
            "lesson": args["lesson"],
            "domain": args.get("domain", "general"),
            "severity": args.get("severity", "low"),
            "description": args.get("description", ""),
            "agent_id": AGENT_ID,
        })
    elif name == "mories_recall_reflections":
        return await _api("GET", "/api/memory/category/reflection", {
            "domain": args.get("domain"),
            "severity": args.get("severity"),
            "agent_id": AGENT_ID,
        })

    elif name == "mories_record_conditional":
        return await _api("POST", "/api/memory/category/conditional", {
            "condition": args["condition"],
            "then_action": args["then_action"],
            "else_action": args.get("else_action"),
            "description": args.get("description", ""),
            "subcategory": args.get("subcategory", "contextual"),
            "agent_id": AGENT_ID,
        })
    elif name == "mories_recall_conditionals":
        return await _api("POST", "/api/memory/category/conditional/search", {
            "context": args.get("context"),
            "subcategory": args.get("subcategory"),
            "agent_id": AGENT_ID,
        })

    # ── Harness Orchestration ──
    elif name == "mories_harness_list":
        return await _api("GET", "/api/analytics/harness/list", {
            "domain": args.get("domain"),
            "agent_id": args.get("agent_id", "all"),
            "include_low_success": str(args.get("include_low_success", False)).lower()
        })

    elif name == "mories_harness_overview":
        return await _api("GET", "/api/analytics/harness/overview")

    elif name == "mories_harness_detail":
        return await _api("GET", f"/api/analytics/harness/{args['uuid']}")

    elif name == "mories_harness_record":
        return await _api("POST", "/api/analytics/harness/record", {
            "domain": args["domain"],
            "trigger": args["trigger"],
            "tool_chain": args["tool_chain"],
            "description": args.get("description", ""),
            "process_type": args.get("process_type", "pipeline"),
            "data_flow": args.get("data_flow", {}),
            "conditionals": args.get("conditionals", []),
            "tags": args.get("tags", []),
            "agent_id": AGENT_ID,
            "scope": args.get("scope", "tribal"),
        })

    elif name == "mories_harness_execute":
        payload = {
            "success": args.get("success", True),
            "execution_time_ms": args.get("execution_time_ms", 0),
            "result_summary": args.get("result_summary", ""),
        }
        if args.get("new_tool_chain"):
            payload["new_tool_chain"] = args["new_tool_chain"]
        return await _api("POST", f"/api/analytics/harness/{args['uuid']}/execute", payload)

    elif name == "mories_harness_evolve":
        return await _api("POST", f"/api/analytics/harness/{args['uuid']}/evolve", {
            "new_tool_chain": args["new_tool_chain"],
            "reason": args["reason"],
        })

    elif name == "mories_harness_recommend":
        params = {"q": args["query"]}
        if args.get("domain"):
            params["domain"] = args["domain"]
        if "cross_domain" in args:
            params["cross_domain"] = "true" if args["cross_domain"] else "false"
        if args.get("limit"):
            params["limit"] = str(args["limit"])
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return await _api("GET", f"/api/analytics/harness/recommend?{query_string}")

    elif name == "mories_harness_rollback":
        return await _api("POST", f"/api/analytics/harness/{args['uuid']}/rollback", {
            "to_version": args["to_version"],
        })

    elif name == "mories_harness_generate":
        return await _api("POST", "/api/analytics/harness/generate", {
            "query": args["query"],
            "domain": args.get("domain", "general"),
        })

    elif name == "mories_harness_suggest_evolution":
        return await _api("POST", f"/api/analytics/harness/{args['uuid']}/suggest_evolution", {
            "context": args.get("context", ""),
        })

    else:
        return {"error": f"Unknown tool: {name}"}


# ─── Entry Point ──────────────────────────────────

async def main():
    logger.info(f"🧠 Mories MCP Server starting — API: {MORIES_URL}")
    logger.info(f"   Agent ID: {AGENT_ID}")
    logger.info(f"   API Key: {'configured' if MORIES_API_KEY else 'none'}")
    logger.info(f"   Tools: {len(TOOLS)}")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def cli_main():
    import asyncio
    asyncio.run(main())

if __name__ == "__main__":
    cli_main()
