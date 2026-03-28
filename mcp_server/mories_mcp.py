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
MORIES_URL = os.environ.get("MORIES_URL", "http://192.168.35.86:5001")
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
        name="mories_health",
        description="Check Mories server health, Neo4j connection status, and node count.",
        inputSchema={"type": "object", "properties": {}},
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


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
