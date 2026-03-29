"""
Mories MCP Server — Main entry point.

Supports two transport modes:
  - stdio  (default): For Claude Desktop, Cursor, etc.
  - sse    : For web-based clients and n8n

Usage:
  # stdio mode (Claude Desktop / Cursor)
  python -m mcp_server.server

  # SSE mode (n8n / web clients)
  python -m mcp_server.server --transport sse --port 3100

Configuration via .env or environment variables:
  MORIES_API_URL  = http://localhost:5001  (Flask API base)
  NEO4J_URI          = bolt://localhost:7687
  MCP_API_KEY        = (optional, for access control)
  MCP_READ_ONLY      = true
  MCP_RATE_LIMIT     = 60
"""

import sys
import json
import logging
import argparse
import asyncio
from typing import Any

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("mories.mcp")

# ---------------------------------------------------------------------------
#  Tool definitions for MCP protocol
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "mories_search",
        "description": (
            "Search the Mories memory system. Returns a COMPACT INDEX "
            "(~50-100 tokens/result) with type icons and relevance scores. "
            "Filter by status for task tracking. "
            "Use mories_detail for full content, mories_timeline for context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "graph_id": {
                    "type": "string",
                    "description": "Optional: scope search to a specific graph/project",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 10,
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: pending, in_progress, completed, blocked",
                    "enum": ["pending", "in_progress", "completed", "blocked"],
                    "default": "",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "mories_detail",
        "description": (
            "Retrieve FULL content of a specific memory by UUID. "
            "Use after mories_search to get complete details for selected items. "
            "Returns all properties, relationships, and full text."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "Memory/entity UUID from mories_search results",
                },
                "include_relations": {
                    "type": "boolean",
                    "description": "Include connected nodes/relationships",
                    "default": True,
                },
            },
            "required": ["uuid"],
        },
    },
    {
        "name": "mories_timeline",
        "description": (
            "Get temporal neighborhood of a memory. "
            "Shows what happened before/after a specific memory "
            "for narrative context. Use after mories_search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "Center memory UUID",
                },
                "window": {
                    "type": "integer",
                    "description": "Number of items before/after center",
                    "default": 5,
                },
            },
            "required": ["uuid"],
        },
    },
    {
        "name": "mories_update_status",
        "description": (
            "Update status/priority/assignment on a memory node. "
            "Lightweight Whiteboard — replaces deleted Orchestration Blackboard. "
            "Use with mories_search(status=...) for task tracking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "Target node UUID",
                },
                "status": {
                    "type": "string",
                    "description": "New status",
                    "enum": ["pending", "in_progress", "completed", "blocked"],
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority (1=highest)",
                },
                "assigned_to": {
                    "type": "string",
                    "description": "Agent UUID to assign",
                    "default": "",
                },
            },
            "required": ["uuid"],
        },
    },
    {
        "name": "mories_ingest",
        "description": (
            "Ingest data into Mories knowledge graph. "
            "Supports 11 adapters: PDF, CSV, JSON, MD, DOCX, HTML, XLSX, "
            "Parquet, YAML, Webhook, and Kafka."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "graph_id": {
                    "type": "string",
                    "description": "Target graph/project ID",
                },
                "source_ref": {
                    "type": "string",
                    "description": "File path or URL to ingest",
                    "default": "",
                },
                "text_content": {
                    "type": "string",
                    "description": "Raw text to ingest directly",
                    "default": "",
                },
                "source_type": {
                    "type": "string",
                    "description": "Adapter hint: auto, csv, json, pdf, md, etc.",
                    "default": "auto",
                },
            },
            "required": ["graph_id"],
        },
    },
    {
        "name": "mories_profile",
        "description": (
            "Look up an agent's profile from the knowledge graph. "
            "Returns traits, dynamic state, relationships, and interaction count."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Agent's display name (e.g. 'Alice Chen')",
                    "default": "",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent's UUID (alternative to name)",
                    "default": "",
                },
                "graph_id": {
                    "type": "string",
                    "description": "Optional graph scope",
                    "default": "",
                },
            },
        },
    },
    {
        "name": "mories_graph_query",
        "description": (
            "Execute a read-only Cypher query on the Neo4j knowledge graph. "
            "Use for custom traversals, aggregations, and pattern matching. "
            "WRITE operations are blocked for security."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cypher": {
                    "type": "string",
                    "description": "Cypher query (READ-ONLY enforced)",
                },
                "params": {
                    "type": "object",
                    "description": "Query parameters",
                    "default": {},
                },
                "limit": {
                    "type": "integer",
                    "description": "Safety limit if no LIMIT in query",
                    "default": 50,
                },
            },
            "required": ["cypher"],
        },
    },
    {
        "name": "mories_stream",
        "description": (
            "Control stream ingestion adapters for real-time data. "
            "Actions: start, stop, list. "
            "Supports Webhook, Kafka, and REST polling sources."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "One of: start, stop, list",
                    "enum": ["start", "stop", "list"],
                },
                "graph_id": {
                    "type": "string",
                    "description": "Target graph ID (for start)",
                    "default": "",
                },
                "source_ref": {
                    "type": "string",
                    "description": "Stream source URI",
                    "default": "",
                },
                "config": {
                    "type": "object",
                    "description": "Stream configuration",
                    "default": {},
                },
            },
            "required": ["action"],
        },
    },
]

# ---------------------------------------------------------------------------
#  Tool dispatcher
# ---------------------------------------------------------------------------

def dispatch_tool(name: str, arguments: dict, allowed_scopes: list[str] = None) -> Any:
    """Dispatch a tool call to the appropriate function."""
    from .tools import (
        mories_search,
        mories_detail,
        mories_timeline,
        mories_update_status,
        mories_ingest,
        mories_profile,
        mories_graph_query,
        mories_stream,
    )

    tool_map = {
        "mories_search": mories_search,
        "mories_detail": mories_detail,
        "mories_timeline": mories_timeline,
        "mories_update_status": mories_update_status,
        "mories_ingest": mories_ingest,
        "mories_profile": mories_profile,
        "mories_graph_query": mories_graph_query,
        "mories_stream": mories_stream,
    }

    func = tool_map.get(name)
    if func is None:
        return {"error": f"Unknown tool: {name}"}

    # Inject allowed_scopes into arguments (tools.py will handle it if supported)
    if allowed_scopes is not None:
        arguments["_allowed_scopes"] = allowed_scopes

    try:
        return func(**arguments)
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
#  JSON-RPC handler (MCP protocol core)
# ---------------------------------------------------------------------------

def handle_jsonrpc(message: dict, allowed_scopes: list[str] = None) -> dict | None:
    """Process a single JSON-RPC 2.0 message (MCP protocol)."""
    method = message.get("method", "")
    msg_id = message.get("id")
    params = message.get("params", {})

    # --- Lifecycle ---
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "mories-memory",
                    "version": "0.7.0",
                },
            },
        }

    if method == "notifications/initialized":
        return None  # notification, no response

    # --- Tool listing ---
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOL_DEFINITIONS},
        }

    # --- Tool execution ---
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        logger.info("Tool call: %s(%s)", tool_name, json.dumps(arguments, ensure_ascii=False)[:200])

        result = dispatch_tool(tool_name, arguments, allowed_scopes)
        result_text = json.dumps(result, ensure_ascii=False, indent=2)

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": result_text,
                    }
                ],
            },
        }

    # --- Ping ---
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    # --- Unknown method ---
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}",
        },
    }


# ---------------------------------------------------------------------------
#  stdio transport
# ---------------------------------------------------------------------------

def run_stdio():
    """Run MCP server over stdio (for Claude Desktop, Cursor, etc.)."""
    logger.info("Mories MCP Server starting (stdio mode)")
    from .config import MCPConfig  # noqa: reimport for globals

    logger.info("API backend: %s", MCPConfig.API_BASE_URL)
    logger.info("Neo4j: %s", MCPConfig.NEO4J_URI)
    logger.info("Read-only: %s", MCPConfig.READ_ONLY_CYPHER)

    allowed_scopes = ['*']
    if MCPConfig.MCP_API_KEY:
        import httpx
        try:
            resp = httpx.post(
                f"{MCPConfig.API_BASE_URL}/api/security/keys/verify",
                json={"api_key": MCPConfig.MCP_API_KEY},
                timeout=5.0
            )
            if resp.status_code == 200 and resp.json().get("valid"):
                allowed_scopes = resp.json().get("principal", {}).get("allowed_scopes", [])
                logger.info(f"Verified stdio MCP API Key. Scopes: {allowed_scopes}")
            else:
                logger.warning("MCP_API_KEY failed verification. Access denied.")
                allowed_scopes = []
        except Exception as e:
            logger.error("Auth verification failed: %s", e)
            allowed_scopes = []

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            error_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(error_resp) + "\n")
            sys.stdout.flush()
            continue

        response = handle_jsonrpc(message, allowed_scopes)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


# ---------------------------------------------------------------------------
#  SSE transport (for n8n and web clients)
# ---------------------------------------------------------------------------

def run_sse(host: str = "0.0.0.0", port: int = 3100):
    """Run MCP server as SSE HTTP endpoint (for n8n / web clients)."""
    try:
        from flask import Flask, request, jsonify, Response
    except ImportError:
        logger.error("Flask required for SSE mode: pip install flask")
        sys.exit(1)

    from .config import MCPConfig

    app = Flask("mories-mcp-sse")

    @app.route("/mcp", methods=["POST"])
    def mcp_endpoint():
        """Handle MCP JSON-RPC over HTTP POST."""
        import httpx
        from .config import MCPConfig
        
        allowed_scopes = ['*']  # Default if no auth required

        # API key auth validation
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if MCPConfig.MCP_API_KEY and token == MCPConfig.MCP_API_KEY:
            allowed_scopes = ['*']  # Admin bypass
        elif token:
            try:
                resp = httpx.post(
                    f"{MCPConfig.API_BASE_URL}/api/security/keys/verify",
                    json={"api_key": token},
                    timeout=5.0
                )
                if resp.status_code == 200 and resp.json().get("valid"):
                    allowed_scopes = resp.json().get("principal", {}).get("allowed_scopes", [])
                else:
                    return jsonify({"error": "Unauthorized / Revoked key"}), 401
            except Exception as e:
                logger.error("Auth verification failed: %s", e)
                return jsonify({"error": "Auth verification failed"}), 500
        elif MCPConfig.MCP_API_KEY and not token:
            return jsonify({"error": "Unauthorized: API Key required"}), 401

        message = request.get_json(silent=True)
        if not message:
            return jsonify({"error": "Invalid JSON"}), 400

        response = handle_jsonrpc(message, allowed_scopes)
        if response is None:
            return "", 204
        return jsonify(response)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "service": "mories-mcp-server",
            "version": "0.7.0",
            "tools": len(TOOL_DEFINITIONS),
            "read_only": MCPConfig.READ_ONLY_CYPHER,
        })

    @app.route("/tools", methods=["GET"])
    def list_tools():
        """List available tools (convenience endpoint)."""
        return jsonify({"tools": TOOL_DEFINITIONS})

    logger.info("Mories MCP Server starting (SSE/HTTP mode)")
    logger.info("Listening on http://%s:%d/mcp", host, port)
    logger.info("Tools endpoint: http://%s:%d/tools", host, port)
    app.run(host=host, port=port, debug=False)


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Mories MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3100,
        help="Port for SSE mode (default: 3100)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for SSE mode (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        run_stdio()
    else:
        run_sse(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
