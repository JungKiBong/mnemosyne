# Troubleshooting & Deployment Guide

## 1. Mories Navigation & GUI Integrity
- **Nginx Caching**: If updates to dashboard HTML (`/Users/.../dashboard/`) are not reflecting correctly, ensure Nginx blocks static HTML caching.
  - Fix: Implemented `try_files` and `add_header Cache-Control "no-cache"` inside `nginx.conf`.
- **API Connectivity**: Visual graphs require backend `/api/query` support. Errors occurring here (`500 Internal Server`) generally point to missing modules or incorrect database credentials.

## 2. Docker & Environment Variable Precedence
- **Neo4j DB Resolution**: The `config.py` uses `python-dotenv`. A critical bug happens when `override=True` forces a hardcoded `localhost` string from the `.env` file instead of Docker's `neo4j:7687`.
  - Fix: Changed to `load_dotenv(override=False)` so that dynamic Docker `environment:` overrides take higher precedence in runtime.

## 3. MCP Server Module Resolution in Container Builds
- **ModuleNotFoundError ('mcp_server')**: When building `mirofish-api` via `src/Dockerfile`, the `mcp_server` root package isn't copied.
  - Fix: Rather than recreating massive Python build layers, the `mcp_server` was explicitly mounted via `volumes` inside `docker-compose.yml`:
  ```yaml
    volumes:
      - ./uploads:/app/uploads
      - ./mcp_server:/mcp_server
  ```
- **Cypher Execution Crash**: Ensure frontend `toggleLoader()` correctly validates DOM ids before querying, to prevent silent JS `TypeError` crashes mid-fetch.
