# 02. 아키텍처 리뷰
> **Date**: 2026-04-06 | **Scope**: 시스템 전체 아키텍처, 설계 원칙, 확장성

---

## 1. 시스템 아키텍처 개요

```
┌──────────────── Presentation Layer ────────────────┐
│  Dashboard (15 HTML)  │  MCP Server (27 tools)     │
│  REST Clients         │  n8n / NiFi Webhooks       │
└───────────────────────┼────────────────────────────┘
                        │
┌───────────────────────┼────────── API Layer ────────┐
│              Flask 3.x (10 Blueprints)              │
│  memory · harness · admin · analytics · graph       │
│  simulation · ingest · terminology · core           │
│  Rate Limiter · CORS · Prometheus Metrics           │
└───────────────────────┼────────────────────────────┘
                        │
┌───────────────────────┼──── Business Logic ─────────┐
│  ┌─────────────────────────────────────────────┐    │
│  │       Cognitive Memory Engine               │    │
│  │  STM Buffer → LTM Store → PM Imprint       │    │
│  │  Ebbinghaus · Boost · Scope · Category     │    │
│  │  Audit Trail · Synaptic Bridge             │    │
│  └─────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────┐    │
│  │       Harness Orchestration Engine (v4)     │    │
│  │  DSL Runtime · Executor Registry            │    │
│  │  Auto-Healer · Memory Bridge · Planner     │    │
│  └─────────────────────────────────────────────┘    │
└───────────────────────┼────────────────────────────┘
                        │
┌───────────────────────┼──── Infrastructure ─────────┐
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Neo4j   │  │ SQLite   │  │ Supermemory      │  │
│  │ (Graph)  │  │ (Metrics)│  │ (Async Replica)  │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Ray     │  │  Nomad   │  │  Wasm            │  │
│  │ (Dist.)  │  │ (Sched.) │  │ (Sandbox)        │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└────────────────────────────────────────────────────┘
```

---

## 2. 설계 원칙 평가

### 2.1 ✅ 잘 지켜진 원칙

| 원칙 | 구현 | 예시 |
|------|------|------|
| **Dependency Injection** | Flask `app.extensions`를 통한 싱글톤 주입 | `neo4j_driver`, `memory_manager`, `rbac` |
| **Lazy Loading** | 인프라 의존성의 지연 로딩 | Ray, Nomad, Wasm executor의 import 분리 |
| **Application Factory** | Flask `create_app()` 패턴 | `src/app/__init__.py` |
| **Blueprint Modularity** | API를 10개 블루프린트로 분리 | `memory_bp`, `harness_analytics_bp` 등 |
| **Singleton Pattern** | MemoryManager 싱글톤 | `get_instance()` + `reset_instance()` |
| **State Checkpointing** | 워크플로우 상태 JSON 파일 저장 | 중断 후 재개 가능 |

### 2.2 ⚠️ 부분적으로 지켜진 원칙

| 원칙 | 현황 | 문제 |
|------|------|------|
| **Separation of Concerns** | 70% | Storage/Service/API 3계층은 잘 분리됨. 그러나 `memory.py` API에 비즈니스 로직 침투 |
| **Interface Abstraction** | 50% | Storage에 `Neo4jStorage`와 `HybridStorage`가 있으나, 공통 인터페이스(ABC) 미정의 |
| **Error Handling** | 60% | 핵심 경로에 try/catch 존재. 그러나 일관된 에러 응답 포맷 미확립 |
| **Configuration Management** | 60% | `.env` 기반이나, 일부 하드코딩된 기본값. 환경별 프로파일 미지원 |

### 2.3 ❌ 미흡한 원칙

| 원칙 | 현황 | 영향 |
|------|------|------|
| **Interface-first Design** | ABC 없음 | Executor/Storage 교체 시 리스크 |
| **Event-Driven Architecture** | Webhook 수준 | 진정한 이벤트 버스/메시지 큐 없음 |
| **Observability** | 메트릭 정의만 | 분산 트레이싱, 구조화 로깅, 알림 미구현 |
| **API Versioning** | 없음 | `/api/v1/` 미사용 → Breaking change 관리 불가 |

---

## 3. 데이터 흐름 분석

### 3.1 메모리 수집 경로 (Ingestion Flow)

```
[MCP Tool: mories_ingest]
       │
       ▼
[REST API /api/memory/stm/add]
       │
       ▼
[MemoryManager.stm_add()]  ← In-memory Dict
       │
       ▼ (salience ≥ 0.7)
[MemoryManager.stm_promote()]  ← Neo4j CREATE
       │
       ▼
[MemoryAudit.record()]  ← 감사 이력
       │
       ▼ (webhook_enabled)
[WebhookPublisher.memory_promoted()]  ← 외부 알림
```

**문제점**:
1. STM 버퍼가 **in-memory Dict** → 서버 재시작 시 유실
2. Neo4j 쓰기 실패 시 STM 항목이 이미 pop됨 → **데이터 손실 가능**
3. Webhook 발행이 동기적 → 외부 서비스 장애 시 지연

### 3.2 하네스 실행 경로 (Harness Execution Flow)

```
[DSL JSON] → [HarnessRuntime.execute()]
                    │
                    ├── step.type == "api_call"  → requests.post()
                    ├── step.type == "code"       → exec(script_code)
                    ├── step.type == "ray_remote"  → RayExecutor
                    ├── step.type == "nomad_job"   → NomadExecutor
                    ├── step.type == "wasm_sandbox" → WasmExecutor
                    ├── step.type == "parallel"     → ParallelExecutor
                    └── step.type == "hitl_gate"    → HITL Suspend
                    │
                    ▼
            [MemoryBridge.ingest_experience()]
                    │
                    ▼
            [MetricsStore.record()]
```

---

## 4. 확장성 분석

### 4.1 수직 확장 (Scale-Up)

| 컴포넌트 | 현재 한계 | 병목 포인트 |
|----------|----------|------------|
| Flask | 단일 프로세스 (Werkzeug) | 동시 요청 처리 수 |
| Neo4j | 단일 인스턴스 | 대규모 그래프 쿼리 시 메모리 |
| STM Buffer | In-memory Dict (100 items max) | 메모리 제한 |
| SQLite Metrics | WAL 모드 | 동시 쓰기 경합 |

### 4.2 수평 확장 (Scale-Out)

| 방향 | 가능성 | 필요 작업 |
|------|--------|----------|
| **API Tier** (Gunicorn + Nginx) | 🟢 쉬움 | `gunicorn -w 4` 적용만으로 가능 |
| **Neo4j Cluster** (Causal Clustering) | 🟡 중간 | 읽기 확장은 쉬움, 쓰기는 리더 의존 |
| **STM 분산** (Redis 전환) | 🟡 중간 | In-memory Dict → Redis 교체 ~2주 |
| **워크플로우 분산** (Ray Cluster) | 🟡 중간 | 코드는 있으나 실 검증 미완 |
| **멀티테넌트** | 🔴 어려움 | 현재 싱글 테넌트 설계 → 전면 재설계 필요 |

---

## 5. 보안 아키텍처 평가

| 영역 | 현황 | 심각도 |
|------|------|--------|
| **인증 (AuthN)** | API Key 헤더 수준 | 🔴 JWT/OAuth 없음 |
| **인가 (AuthZ)** | RBAC 구현됨 | 🟢 역할 기반 제어 |
| **전송 암호화** | HTTP (TLS 미적용) | 🔴 프로덕션 불가 |
| **저장 암호화** | AES-256 필드 암호화 | 🟢 양호 |
| **입력 검증** | Flask request 수준 | 🟡 Pydantic/Marshmallow 미사용 |
| **Code Injection** | `exec()` 1건 | 🟡 Wasm 샌드박스로 대체 가능 |
| **CORS** | `*` 허용 (개발 모드) | 🟡 프로덕션 시 제한 필요 |
| **Rate Limiting** | Flask-Limiter 적용 | 🟢 양호 |
| **Audit Trail** | 모든 변경 기록 | 🟢 우수 |

---

## 6. 아키텍처 개선 권고

### 🔴 즉시 (1개월 내)

1. **STM 영속화**: In-memory Dict → Redis or SQLite WAL
2. **API 응답 표준화**: 통일된 에러 포맷 `{status, data, error, timestamp}`
3. **API 버전닝 도입**: `/api/v1/memory/...`

### 🟡 단기 (3개월 내)

4. **Storage ABC 정의**: `AbstractMemoryStorage` 인터페이스 → Neo4j/Supermemory/Mock 구현
5. **이벤트 버스 도입**: 내부 Pub/Sub (asyncio.Queue 또는 Redis Streams)
6. **Pydantic 스키마**: 모든 API 입출력에 스키마 유효성 검증

### 🟢 중기 (6개월 내)

7. **인증 재설계**: JWT + OAuth2 + 멀티테넌트 지원
8. **분산 트레이싱**: OpenTelemetry 통합
9. **gRPC/WebSocket**: 실시간 메모리 이벤트 스트리밍

---

## 7. 아키텍처 성숙도 판정

```
Level 1: Monolith (단순 단일 서비스)          ← 여기에서...
Level 2: Modular Monolith (모듈화된 단일체)   ← ★ 현재 위치
Level 3: Service-Oriented (서비스 지향)       ← 다음 목표
Level 4: Microservices (마이크로서비스)
Level 5: Event-Driven Platform (이벤트 기반 플랫폼)
```

**현재 Level 2 (Modular Monolith)**: 잘 분리된 블루프린트와 DI 패턴이 있으나, 단일 프로세스에서 실행. Level 3 전환에 필요한 인프라 프리미티브(메시지 큐, API Gateway)가 부재.
