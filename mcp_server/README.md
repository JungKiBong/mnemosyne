# Mories MCP Server

The Mories MCP Server exposes the Mories memory system to any compatible Model Context Protocol (MCP) client (like Claude Desktop, Cursor, and n8n). By integrating this server, AI agents can read, write, and share memories natively through the Mories Knowledge Graph.

## Overview

The `mcp_server/` directory contains tools and scripts to quickly mount the Mories memory engine as an external capability for your LLM agents. 

We currently bundle two implementations:

1. **`mories_mcp.py` (Recommended for Local Agents)**: Built on the official Python MCP SDK. Provides the full Mories Cognitive Protocol, giving agents access to Short-Term Memory (STM), Long-Term Memory (LTM), and the Synaptic Bridge for cross-agent sharing. 
2. **`server.py` (Module Mode / SSE Mode)**: A custom JSON-RPC implementation supporting both `stdio` and `SSE` (Server-Sent Events) transports over HTTP. This is useful for orchestrators like n8n or web-based clients that cannot use standard I/O pipes.

---

## 🚀 Quick Start (Claude Desktop / Cursor)

The easiest way to get started is by using the `setup.sh` script, which will verify your environment and provide the exact configuration needed for your MCP client.

### Prerequisites
- Python 3.10+
- A running instance of the Mories REST API (`http://localhost:5001`)

### Setup Script
```bash
cd mcp_server
./setup.sh
```
This script will:
1. Ensure the required dependencies (`mcp`, `httpx`) are installed.
2. Verify that the Mories API is reachable.
3. Validate the MCP server syntax.
4. Output the snippet you need to add to your client's configuration file.

### Claude Desktop Configuration
Add the following to your `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mories": {
      "command": "python3",
      "args": ["/absolute/path/to/mirofish-supermemory/mcp_server/mories_mcp.py"],
      "env": {
        "MORIES_URL": "http://localhost:5001",
        "MORIES_AGENT_ID": "claude-desktop"
      }
    }
  }
}
```

Restart Claude Desktop, and Claude will now have access to the Mories knowledge graph!

---

## 🛠 Available Tools (`mories_mcp.py`)

When using the primary `mories_mcp.py` server, the following capabilities are exposed:

- **`mories_search`**: Search the knowledge graph for past memories, architecture decisions, and task history using natural language.
- **`mories_ingest`**: Process markdown-formatted content into the knowledge graph (automatically extracts entities, facts, and relationships).
- **`mories_stm_add`**: Add contextual observations or session details to Short-Term Memory (STM).
- **`mories_stm_promote`**: Promote verified or critical STM entries into permanent Long-Term Memory (LTM).
- **`mories_memory_overview` & `mories_memory_top`**: Retrieve metrics and top salient memories about the current graph's state.
- **`mories_graph_query`**: Execute read-only Neo4j Cypher queries for deep graph traversal and aggregations.
- **`mories_synaptic_share`**: Transmit a memory from one agent to another (or broadcast) across the Synaptic Bridge.
- **`mories_permanent_imprint`**: Imprint an immutable rule or policy that bypasses standard memory decay cycles.

---

## 🌐 Running in SSE Mode (n8n, Dify)

If you are integrating Mories with a web-based orchestrator that requires an HTTP endpoint instead of a local process, use the `server.py` implementation in SSE mode.

```bash
# Start the SSE MCP Server on port 3100
cd /path/to/mirofish-supermemory
python3 -m mcp_server.server --transport sse --port 3100
```
This will expose:
- `POST http://localhost:3100/mcp`: The MCP JSON-RPC endpoint.
- `GET http://localhost:3100/health`: Server health and node counts.
- `GET http://localhost:3100/tools`: Available tools list.

### Configuration (`.env` or Env Vars)
When running the `server.py` engine, it relies on the project's `.env` configuration (see `mcp_server/config.py`):

| Variable | Default | Description |
|---|---|---|
| `MORIES_API_URL` | `http://localhost:5001` | URL of the Mories REST API |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt connection URI |
| `MCP_API_KEY` | *(empty)* | Optional API key to restrict MCP operations |
| `MCP_READ_ONLY` | `true` | Enforce read-only access for raw Cypher queries |
| `MCP_RATE_LIMIT`| `60` | Max capability calls per minute per client |

---

## Development & Testing

You can use the official MCP Inspector to interactively debug the server:

```bash
npx @modelcontextprotocol/inspector python3 mcp_server/mories_mcp.py
```
