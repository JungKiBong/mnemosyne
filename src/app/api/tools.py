"""
MCP Tools API — Agent-facing tool execution endpoint

Endpoints:
  GET  /api/tools/list          — List all available memory tools (schemas)
  POST /api/tools/execute       — Execute a tool by name
  GET  /api/tools/schemas/openai — Export OpenAI Function Calling schemas
  GET  /api/tools/schemas/mcp   — Export MCP-compatible schemas
"""

import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger('mirofish.api.tools')

tools_bp = Blueprint('tools', __name__, url_prefix='/api/tools')

# Singleton toolkit
_toolkit = None

def _get_toolkit():
    global _toolkit
    if _toolkit is None:
        from ..tools.memory_tools import MoriesToolkit
        _toolkit = MoriesToolkit()
    return _toolkit


@tools_bp.route('/list', methods=['GET'])
def list_tools():
    """List all available memory tools with descriptions."""
    tk = _get_toolkit()
    tools = []
    for name in tk.get_tool_names():
        desc = tk.get_tool_description(name)
        tools.append({
            "name": desc["name"],
            "description": desc["description"],
            "category": desc["category"],
            "parameter_count": len(desc["parameters"]),
        })
    return jsonify({"tools": tools, "count": len(tools)})


@tools_bp.route('/execute', methods=['POST'])
def execute_tool():
    """
    Execute a memory tool.

    Body: {"tool": "memory_store", "arguments": {"content": "...", "source": "agent"}}
    """
    data = request.get_json(force=True)
    tool_name = data.get('tool')
    arguments = data.get('arguments', {})

    if not tool_name:
        return jsonify({"error": "tool name is required"}), 400

    tk = _get_toolkit()
    result = tk.execute(tool_name, arguments)

    if result.get("status") == "error":
        return jsonify(result), 500

    return jsonify(result)


@tools_bp.route('/schemas/openai', methods=['GET'])
def openai_schemas():
    """Export all tools as OpenAI Function Calling schemas."""
    tk = _get_toolkit()
    schemas = tk.get_all_schemas("openai")
    return jsonify({"tools": schemas, "format": "openai_function_calling"})


@tools_bp.route('/schemas/mcp', methods=['GET'])
def mcp_schemas():
    """Export all tools as MCP-compatible schemas."""
    tk = _get_toolkit()
    schemas = tk.get_all_schemas("mcp")
    return jsonify({"tools": schemas, "format": "mcp"})
