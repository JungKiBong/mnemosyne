"""
MCP Server configuration.
Reads from environment variables or .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'), override=True)
load_dotenv(os.path.join(os.path.dirname(__file__), '../src/.env'), override=True)


class MCPConfig:
    """MCP Server configuration."""

    # Flask API backend
    API_BASE_URL = os.environ.get('MNEMOSYNE_API_URL', 'http://localhost:5001')

    # Neo4j (direct access for graph_query tool)
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'mirofish')

    # Security
    MCP_API_KEY = os.environ.get('MCP_API_KEY', '')  # Empty = no auth
    READ_ONLY_CYPHER = os.environ.get('MCP_READ_ONLY', 'true').lower() == 'true'
    RATE_LIMIT_PER_MIN = int(os.environ.get('MCP_RATE_LIMIT', '60'))

    # LLM (for search agent)
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'http://192.168.35.86:11434/v1')
    LLM_MODEL = os.environ.get('LLM_MODEL_NAME', 'llama3.1:8b')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL', 'http://192.168.35.86:11434')
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'bge-m3')
