# 🧠 Mnemosyne — Cognitive Memory Architecture for AI Agents

> **인간의 기억을 모방한 AI 에이전트 인지 메모리 시스템.**  
> 단기기억(STM) → 장기기억(LTM) → 영구기억(PM) 전환, Ebbinghaus 망각곡선 기반 자연 감쇠,  
> 검색 시 강화(Retrieval Boost), 계층적 기억 범위(Scope), 영구기억 각인/상속,  
> 도구사용(Procedural) & 모방(Observational) 카테고리 확장, 시냅틱 에이전트 간 기억 공유를 지원합니다.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.x-green.svg)](https://neo4j.com/)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey.svg)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 76 passed](https://img.shields.io/badge/tests-76%20passed-brightgreen.svg)](#-test-suite)

---

## ✨ Key Features

### 🧠 Cognitive Memory Engine
| Feature | Description |
|---------|-------------|
| **STM → LTM Lifecycle** | 단기기억 자동 평가 → 중요도 기반 장기기억 승격 |
| **Ebbinghaus Decay** | 시간에 따른 자연적 기억 감쇠 (`salience = salience × decay_rate`) |
| **Retrieval Boost** | 검색/접근 시 기억 강화 (인출 강화 효과) |
| **Permanent Memory** | 영구기억 (Imprint 각인 + Frozen LTM) — 감쇠/변경 불가 |
| **Inheritance Chain** | Global → Social → Tribal 영구기억 자동 상속 |
| **Priority Resolution** | 스코프/관리자Pin/에이전트가중치 기반 우선순위 엔진 |
| **Procedural Memory** | 도구 사용(API/MCP/Code) 경험 기록 & 성공률 기반 감쇠 수정 |
| **Observational Memory** | 사용자/에이전트 행동 관찰 & 패턴 학습 |
| **Memory Scopes** | Personal → Tribal → Social → Universal 계층적 범위 |
| **Synaptic Bridge** | 에이전트 간 기억 공유 및 이벤트 발행 |
| **Audit Trail** | 모든 변경의 불변 이력 + 롤백 기능 |

### 🏗️ Infrastructure
| Feature | Description |
|---------|-------------|
| **HybridStorage** | Neo4j(Source of Truth) + Supermemory(Cognitive Memory) 이중 백엔드 |
| **11+ Data Adapters** | PDF, MD, DOCX, CSV, JSON, Parquet, YAML, Webhook, Kafka, REST, Neo4j Import |
| **Circuit Breaker** | 장애 격리 패턴으로 자동 복구 |
| **Outbox Pattern** | 보장된 비동기 전달 + Dead Letter Queue |
| **RBAC + Encryption** | 역할 기반 접근 제어 + AES-256 필드 암호화 |
| **MCP Server** | AI 에이전트가 도구로 직접 호출 가능한 MCP 프로토콜 |

### 📊 Dashboard & APIs
| Feature | Description |
|---------|-------------|
| **166 REST Endpoints** | 메모리 CRUD, 검색, 감사, 범위, 시냅틱, 보안, 성숙도, 영구기억, 카테고리 |
| **Admin Dashboard** | 실시간 메모리 모니터링, 가중치 관리, 탐색 |
| **Data Products** | RAG 코퍼스, Knowledge Graph 스냅샷, Training 데이터셋 내보내기 |
| **External Gateway** | n8n, NiFi, Spark, REST API 연동 |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Mnemosyne System                            │
│                                                                  │
│   ┌──────────────┐     ┌──────────────┐    ┌──────────────┐    │
│   │  Dashboard   │     │  MCP Server  │    │  n8n / NiFi  │    │
│   │  (5 HTML)    │     │  (5 Tools)   │    │  (Webhooks)  │    │
│   └──────┬───────┘     └──────┬───────┘    └──────┬───────┘    │
│          │                    │                    │              │
│   ┌──────┴────────────────────┴────────────────────┴──────┐     │
│   │              Flask REST API (166 endpoints)           │     │
│   │  Memory · PM · Category · Audit · Scope · Synaptic ·  │     │
│   │  Security · Maturity · Reconciliation · Data Products  │     │
│   └──────────────────────┬────────────────────────────────┘     │
│                          │                                       │
│   ┌──────────────────────┼────────────────────────┐             │
│   │           Cognitive Memory Engine             │             │
│   │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │             │
│   │  │  STM   │→│  LTM   │→│  PM    │→│Maturity│ │             │
│   │  │ Buffer │ │ Store  │ │Imprint │ │ Levels │ │             │
│   │  └────────┘ └────────┘ │Frozen  │ └────────┘ │             │
│   │                        └────────┘             │             │
│   │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │             │
│   │  │ Scopes │ │Categor.│ │Priority│ │Inherit │ │             │
│   │  │ Ladder │ │Proc/Obs│ │ Engine │ │ Chain  │ │             │
│   │  └────────┘ └────────┘ └────────┘ └────────┘ │             │
│   │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │             │
│   │  │ Decay  │ │ Boost  │ │ Audit  │ │Synapse │ │             │
│   │  │Ebbingh.│ │Retriev.│ │ Trail  │ │ Bridge │ │             │
│   │  └────────┘ └────────┘ └────────┘ └────────┘ │             │
│   └──────────────────────┬────────────────────────┘             │
│                          │                                       │
│   ┌──────────────────────┼────────────────────────┐             │
│   │              Storage Layer                    │             │
│   │  ┌────────────┐    ┌──────────────────┐       │             │
│   │  │   Neo4j    │    │   Supermemory    │       │             │
│   │  │  (Graph)   │    │  (ASMR Memory)  │       │             │
│   │  │  SoT       │    │  Async Replica  │       │             │
│   │  └────────────┘    └──────────────────┘       │             │
│   │  ┌────────────┐    ┌──────────────────┐       │             │
│   │  │ Circuit    │    │ Outbox Worker    │       │             │
│   │  │ Breaker    │    │ + Dead Letter Q  │       │             │
│   │  └────────────┘    └──────────────────┘       │             │
│   └───────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **Docker** (for Neo4j)
- **Ollama** (optional, for local LLM)

### 1. Clone & Setup

```bash
git clone https://github.com/JungKiBong/mnemosyne.git
cd mnemosyne

# Environment setup
cp .env.example .env
# Edit .env with your Neo4j password and API keys
```

### 2. Start Neo4j

```bash
# Mac local development (Neo4j only)
docker-compose -f docker-compose.mac.yml up -d neo4j

# Full stack (API + Dashboard + Neo4j)
docker-compose up -d
```

### 3. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

### 4. Run the Server

```bash
cd src
FLASK_APP=app FLASK_DEBUG=0 flask run --host=0.0.0.0 --port=5050
```

### 5. Access

| Service | URL |
|---------|-----|
| **Flask API** | http://localhost:5050 |
| **Dashboard** | http://localhost:5050/dashboard |
| **Memory Dashboard** | http://localhost:5050/memory |
| **Synaptic Dashboard** | http://localhost:5050/memory/synaptic |
| **Neo4j Browser** | http://localhost:7474 |

---

## 🧪 Test Suite

```bash
# Run all tests (from project root)
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_resilience.py tests/integration/ tests/e2e/ -v

# Expected: 58 passed ✅
```

### Test Coverage

| Category | Tests | Description |
|----------|-------|-------------|
| **Unit** | 8 | CircuitBreaker, OutboxWorker |
| **Integration** | 25 | STM lifecycle, Decay/Boost, Audit +Rollback, Scope promotion, Reconciliation |
| **E2E** | 25 | Health, Memory CRUD, Search, Audit, Scope, Dashboard, Data Products, Security, Maturity, Reconciliation |

---

## 📁 Project Structure

```
mnemosyne/
├── src/app/
│   ├── storage/
│   │   ├── memory_manager.py          # STM/LTM lifecycle, decay, boost
│   │   ├── memory_scopes.py           # Personal→Tribal→Social→Universal
│   │   ├── synaptic_bridge.py         # Multi-agent memory sharing
│   │   ├── memory_audit.py            # Immutable revision trail + rollback
│   │   ├── reconciliation_service.py  # Neo4j↔SM data consistency
│   │   ├── hybrid_storage.py          # Dual backend with outbox
│   │   ├── neo4j_storage.py           # Graph storage implementation
│   │   ├── search_service.py          # Hybrid search + retrieval boost
│   │   └── supermemory_client.py      # Supermemory SDK wrapper
│   ├── api/                           # 15 blueprint modules → 139 endpoints
│   │   ├── memory.py                  # Memory CRUD & STM operations
│   │   ├── memory_audit.py            # Audit trail & rollback
│   │   ├── memory_scopes.py           # Scope management
│   │   ├── synaptic.py                # Agent memory sharing
│   │   ├── data_product.py            # RAG corpus, snapshots, training
│   │   ├── gateway.py                 # External system integration
│   │   ├── security.py                # RBAC + encryption
│   │   ├── maturity.py                # Knowledge lifecycle model
│   │   ├── reconciliation.py          # Data consistency API
│   │   ├── pipeline.py                # Auto ingest→STM pipeline
│   │   └── tools.py                   # MCP tool REST proxy
│   ├── security/
│   │   ├── memory_rbac.py             # Role-based access control
│   │   ├── memory_encryption.py       # AES-256 field encryption
│   │   └── memory_maturity.py         # Knowledge maturity model
│   ├── services/
│   │   ├── memory_scheduler.py        # Background decay, cleanup, promotion
│   │   ├── memory_pipeline.py         # Ingest→STM auto flow
│   │   ├── observer_agent.py          # Cognitive memory extraction
│   │   └── search_agent.py            # ASMR 3-way retrieval
│   ├── resilience/
│   │   ├── circuit_breaker.py         # Fault isolation
│   │   └── outbox_worker.py           # Async retry + dead letter
│   └── adapters/                      # 11+ data source adapters
├── dashboard/                         # Admin UI (5 HTML pages)
│   ├── index.html                     # System overview
│   ├── memory.html                    # Memory management
│   ├── memory_history.html            # Audit trail viewer
│   ├── synaptic.html                  # Agent network
│   └── maturity.html                  # Knowledge lifecycle
├── mcp_server/                        # MCP protocol server (5 tools)
├── n8n_workflows/                     # n8n automation templates
├── tests/
│   ├── unit/                          # 8 unit tests
│   ├── integration/                   # 25 integration tests
│   └── e2e/                          # 25 E2E API tests
├── docs/                              # Design documents (6 docs)
├── docker-compose.yml                 # Full stack deployment
├── docker-compose.mac.yml             # Mac dev (Neo4j only)
└── .env.example                       # Environment template
```

---

## 🔧 Configuration

```env
# Storage
STORAGE_BACKEND=hybrid          # neo4j | hybrid
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=mirofish

# Supermemory (optional — Neo4j works standalone)
SUPERMEMORY_API_KEY=your-key

# LLM (optional — for observer/search agents)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.1

# Security
WEBHOOK_SECRET=your-webhook-hmac-secret
FLASK_SECRET_KEY=change-me-in-production
```

---

## 📊 Core API Reference

### Memory Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/memory/stm/add` | Add to short-term memory |
| GET | `/api/memory/stm/list` | List STM buffer |
| POST | `/api/memory/stm/evaluate` | Evaluate salience for promotion |
| POST | `/api/memory/stm/promote` | Promote STM → LTM |
| POST | `/api/memory/decay` | Trigger memory decay cycle |
| POST | `/api/memory/boost` | Manual salience boost |
| GET | `/api/memory/overview` | Dashboard overview data |
| GET | `/api/memory/config` | Current engine configuration |

### Audit & History

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/audit/activity` | Recent audit activity |
| GET | `/api/memory/audit/stats` | Audit statistics |
| GET | `/api/memory/audit/history/<uuid>` | Memory revision history |
| POST | `/api/memory/audit/rollback` | Rollback to previous revision |

### Memory Scopes

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/scopes/summary` | Scope distribution stats |
| POST | `/api/memory/scopes/promote` | Promote memory scope level |
| GET | `/api/memory/scopes/candidates` | Auto-promotion candidates |

### Security

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/security/roles` | List RBAC role definitions |
| POST | `/api/security/check` | Check access permissions |
| POST | `/api/security/encrypt` | Encrypt memory field |
| POST | `/api/security/decrypt` | Decrypt memory field |

### Data Products

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/data/rag` | Export RAG corpus |
| GET | `/api/memory/data/snapshot` | Knowledge graph snapshot |
| GET | `/api/memory/data/training` | Training dataset export |
| GET | `/api/memory/data/catalog` | Data product catalog |

### Data Consistency

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reconciliation/check` | Quick health check |
| POST | `/api/reconciliation/run` | Full reconciliation scan |
| GET | `/api/reconciliation/history` | Reconciliation run history |

> 📋 **Full list**: 139 endpoints across 15 API modules. See `src/app/api/` for complete documentation.

---

## 🗺 Development Roadmap

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 0 | Environment Setup | ✅ | Docker, Neo4j, Python, dependencies |
| 1 | HybridStorage | ✅ | Neo4j + Supermemory dual backend |
| 1.5 | Data Adapters | ✅ | 11+ adapters for diverse data sources |
| 2 | Observer Agents | ✅ | Personal/Event/Social cognitive extraction |
| 3 | Search Agents | ✅ | ASMR 3-way parallel retrieval |
| 4 | Production & UX | ✅ | Docker Compose + Dashboard |
| 5 | MCP Server | ✅ | 5 agent-callable tools |
| 7 | Cognitive Memory | ✅ | STM/LTM lifecycle with Ebbinghaus decay |
| 8 | Memory Scopes | ✅ | Hierarchical scope system |
| 9 | Synaptic Bridge | ✅ | Multi-agent memory sharing |
| 10 | Audit Trail | ✅ | Immutable revision history + rollback |
| 11 | Data Products | ✅ | RAG corpus, snapshots, training sets |
| 12 | External Gateway | ✅ | n8n, NiFi, Spark integration |
| 13 | Memory RBAC | ✅ | Role-based access control |
| 14 | Encryption | ✅ | AES-256 field-level encryption |
| 15 | Knowledge Maturity | ✅ | Knowledge lifecycle model |
| — | Reconciliation | ✅ | Neo4j↔SM data consistency engine |

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`PYTHONPATH=src .venv/bin/python -m pytest tests/ -v`)
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.

Based on [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline) and [Supermemory](https://github.com/supermemoryai/supermemory).

---

*Built with 🧠 by the Mnemosyne Project*
