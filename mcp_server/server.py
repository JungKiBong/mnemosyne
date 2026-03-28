"""
Mnemosyne MCP Server — Main entry point.

Supports two transport modes:
  - stdio  (default): For Claude Desktop, Cursor, etc.
  - sse    : For web-based clients and n8n

Usage:
  # stdio mode (Claude Desktop / Cursor)
  python -m mcp_server.server

  # SSE mode (n8n / web clients)
  python -m mcp_server.server --transport sse --port 3100

Configuration via .env or environment variables:
  MNEMOSYNE_API_URL  = http://localhost:5001  (Flask API base)
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
logger = logging.getLogger("mnemosyne.mcp")

# ---------------------------------------------------------------------------
#  Tool definitions for MCP protocol
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "mnemosyne_search",
        "description": (
            "Search the Mnemosyne hybrid memory system. "
            "Queries Neo4j knowledge graph via fulltext and vector indexes. "
            "Returns entities, facts, and episodes matching the query."
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
            },
            "required": ["query"],
        },
    },
    {
        "name": "mnemosyne_ingest",
        "description": (
            "Ingest data into Mnemosyne knowledge graph. "
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
        "name": "mnemosyne_profile",
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
        "name": "mnemosyne_graph_query",
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
        "name": "mnemosyne_stream",
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

def dispatch_tool(name: str, arguments: dict) -> Any:
    """Dispatch a tool call to the appropriate function."""
    from .tools import (
        mnemosyne_search,
        mnemosyne_ingest,
        mnemosyne_profile,
        mnemosyne_graph_query,
        mnemosyne_stream,
    )

    tool_map = {
        "mnemosyne_search": mnemosyne_search,
        "mnemosyne_ingest": mnemosyne_ingest,
        "mnemosyne_profile": mnemosyne_profile,
        "mnemosyne_graph_query": mnemosyne_graph_query,
        "mnemosyne_stream": mnemosyne_stream,
    }

    func = tool_map.get(name)
    if func is None:
        return {"error": f"Unknown tool: {name}"}

    try:
        return func(**arguments)
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
#  JSON-RPC handler (MCP protocol core)
# ---------------------------------------------------------------------------

def handle_jsonrpc(message: dict) -> dict | None:
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
                    "name": "mnemosyne-memory",
                    "version": "0.5.0",
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

        result = dispatch_tool(tool_name, arguments)
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
    logger.info("Mnemosyne MCP Server starting (stdio mode)")
    logger.info("API backend: %s", MCPConfig.API_BASE_URL)
    logger.info("Neo4j: %s", MCPConfig.NEO4J_URI)
    logger.info("Read-only: %s", MCPConfig.READ_ONLY_CYPHER)

    from .config import MCPConfig  # noqa: reimport for globals

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

        response = handle_jsonrpc(message)
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

    app = Flask("mnemosyne-mcp-sse")

    @app.route("/mcp", methods=["POST"])
    def mcp_endpoint():
        """Handle MCP JSON-RPC over HTTP POST."""
        # API key auth
        if MCPConfig.MCP_API_KEY:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {MCPConfig.MCP_API_KEY}":
                return jsonify({"error": "Unauthorized"}), 401

        message = request.get_json(silent=True)
        if not message:
            return jsonify({"error": "Invalid JSON"}), 400

        response = handle_jsonrpc(message)
        if response is None:
            return "", 204
        return jsonify(response)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "service": "mnemosyne-mcp-server",
            "version": "0.5.0",
            "tools": len(TOOL_DEFINITIONS),
            "read_only": MCPConfig.READ_ONLY_CYPHER,
        })

    @app.route("/tools", methods=["GET"])
    def list_tools():
        """List available tools (convenience endpoint)."""
        return jsonify({"tools": TOOL_DEFINITIONS})

    logger.info("Mnemosyne MCP Server starting (SSE/HTTP mode)")
    logger.info("Listening on http://%s:%d/mcp", host, port)
    logger.info("Tools endpoint: http://%s:%d/tools", host, port)
    app.run(host=host, port=port, debug=False)


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Mnemosyne MCP Server")
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
