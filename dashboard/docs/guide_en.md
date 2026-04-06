# 📖 Mories Operation Guide

> A practical guide for system operation, management, and troubleshooting.

## 1. System Requirements

| Component | Minimum | Recommended |
| --- | --- | --- |
| Python | 3.12+ | 3.13+ |
| Neo4j | 5.x | 5.x (Docker) |
| RAM | 4GB | 8GB+ |
| Disk | 2GB | 10GB+ |
| Ollama (Optional) | — | llama3.1, nomic-embed-text |

---

## 2. Installation & Execution

### 2.1 Basic Installation
```bash
# 1. Clone the project
git clone https://github.com/JungKiBong/mories.git
cd mories

# 2. Set environment variables
cp .env.example .env
nano .env  # Update NEO4J_PASSWORD etc.

# 3. Start Neo4j
docker-compose -f docker-compose.mac.yml up -d neo4j

# 4. Setup Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt

# 5. Run Server
cd src
FLASK_APP=app FLASK_DEBUG=0 flask run --host=0.0.0.0 --port=5050
```

### 2.2 Docker Full Stack
```bash
docker-compose up -d --build
# API: localhost:5050, Neo4j: localhost:7474, Dashboard: localhost:5050/dashboard
```

### 2.3 Backup & Restore
Instructions for safely backing up and restoring Neo4j data in a Docker environment.
```bash
# Backup (Dump)
docker exec -it mirofish-neo4j neo4j-admin database dump system --to-path=/backups
docker exec -it mirofish-neo4j neo4j-admin database dump neo4j --to-path=/backups

# Copy to host machine
docker cp mirofish-neo4j:/backups/neo4j.dump ./neo4j_backup.dump

# Restore (requires container restart into maintenance mode, or an empty DB)
docker exec -it mirofish-neo4j neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
```

---

## 3. Understanding the Cognitive Memory Engine

### 3.1 End-to-End Scenario
The lifecycle of data from ingestion to agent retrieval:
1. **Ingestion:** Information from external tools (n8n, webhooks) enters via the Gateway API (`POST /api/gateway/webhook`).
2. **Short-Term Memory (STM):** The data resides in the STM buffer for up to 24 hours (`stm_ttl`).
3. **Evaluation:** An sentiment analyzer or reviewer assigns a `salience` (importance score, 0-1.0).
4. **Long-Term Memory (LTM):** If `salience` is 0.3 or higher, the memory is permanently saved (Promoted).
5. **Retrieval:** An AI agent queries via the `memory_search` MCP tool. Returned results temporarily increase in salience and access counts (Boost).
6. **Decay:** Unused memories slowly degrade by 5% every day.

### 3.2 Core Concepts

| Concept | Description | Parameters |
| --- | --- | --- |
| **Salience** | Memory importance (0.0 to 1.0) | Initial value determined by evaluation |
| **Decay Rate** | Daily degradation rate | Default: 0.95 (5% loss daily) |
| **Boost Amount** | Boost given upon retrieval | Default: +0.15 |
| **STM TTL** | Short-Term Memory lifespan | Default: 86,400s (24h) |
| **Promote Threshold**| LTM Promotion limit | salience ≥ 0.3 |

### 3.3 Scope & Maturity
* **Scope:** `Personal → Tribal → Social → Universal` (Promotion is one-way, requires salience > 0.7)
* **Maturity:** `Draft → Reviewed → Validated → Certified → Archived`

---

## 4. Dashboard Usage

| Page | URL | Description |
| --- | --- | --- |
| System Overview | `/dashboard` | Overall system metrics |
| Memory Management | `/memory` | Manage STM/LTM, Decay, Boost, Scope |
| Audit Trail | `/memory_history` | Change history + Rollback capability |
| Synaptic Network | `/synaptic` | Agent-to-Agent connection visualization |

*The dashboard source code defaults to the `/dashboard/` folder, distributed statically via Nginx. Substantial CSS or JS updates should increment the version string (`?v=X`) to invalidate cache.*

---

## 5. MCP Server Integration & Agent Specs

Mories embeds a native Model Context Protocol (MCP) server for seamless AI Agent integration. Agent developers can utilize the JSON-RPC tool specifications below.

### 5.1 `memory_search`
Search Long-Term Memory (LTM) by semantic meaning or keywords.
* **Parameters**: `query` (string, required) - Search intent, `limit` (int, optional, default: 5) - Number of results.
* **Example**: `{"method": "memory_search", "params": {"query": "authentication logic issues"}}`

### 5.2 `memory_store`
Store new knowledge from the Agent into Short-Term Memory (STM).
* **Parameters**: `content` (string, required) - Knowledge payload, `metadata` (object, optional) - Tags and additional details.
* **Example**: `{"method": "memory_store", "params": {"content": "The error code is ERR_102."}}`

### 5.3 `memory_boost`
Manually boost the importance score of a specific memory.
* **Parameters**: `memory_id` (string, required), `reason` (string, optional)

### 5.4 REST MCP Proxy
If using HTTP webhooks manually:
```bash
curl -X POST http://localhost:5050/api/mcp \
  -H "Content-Type: application/json" \
  -d '{"method": "memory_search", "params": {"query": "architecture"}}'
```

---

## 6. Security Settings

### 6.1 RBAC (Role-Based Access Control)
```bash
# Check Access Permission
curl -X POST http://localhost:5050/api/security/check \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "agent-1", "resource": "memory-uuid", "action": "read"}'
```

### 6.2 Field Encryption (AES-256)
```bash
# Encrypt specific fields
curl -X POST http://localhost:5050/api/security/encrypt \
  -H "Content-Type: application/json" \
  -d '{"uuid": "<memory-uuid>", "fields": ["content"]}'
```

---

## 7. Data Reconciliation & Troubleshooting

### 7.1 Data Reconciliation
Detects schema mismatches, orphaned structures, or memories not updated in 30 days.
```bash
# Analyze and Autofix
curl -X POST http://localhost:5050/api/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{"auto_fix": true}'
```

### 7.2 Troubleshooting
* **Neo4j Connection Failed**: Check container status with `docker logs mirofish-neo4j` and verify `NEO4J_URI` inside `.env`.
* **Decay Scheduler Stopped**: Verify via `curl http://localhost:5050/api/health` that `"scheduler": "running"`. If stopped, invoke a manual run using `curl -X POST http://localhost:5050/api/v1/memory/decay -d '{"dry_run": false}'`.

---
*Last updated: 2026-04-01*
