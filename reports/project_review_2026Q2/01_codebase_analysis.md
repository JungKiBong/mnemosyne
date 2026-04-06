# 01. 코드베이스 상세 분석
> **Date**: 2026-04-06 | **Scope**: src/app/, mcp_server/, dashboard/, tests/

---

## 1. 코드 규모 총괄

| 영역 | Python 파일 | LOC | 비고 |
|------|------------|-----|------|
| **src/app/** (앱 코어) | 100+ | 39,973 | 핵심 비즈니스 로직 |
| **tests/** | 49 | 6,962 | 단위/통합/E2E/하네스 |
| **mcp_server/** | 6 | 1,776 | MCP 프로토콜 서버 |
| **dashboard/** (HTML/JS/CSS) | 15 | 9,261 | 관리자 대시보드 |
| **합계** | ~170 | **~58,000** | |

---

## 2. 모듈별 세부 분석

### 2.1 Storage Layer (9,598 LOC — 24%)

| 파일 | LOC | 역할 | 복잡도 평가 |
|------|-----|------|------------|
| `memory_categories.py` | 2,410 | 인지 기억 카테고리 (Procedural, Observational 등) | 🔴 **과도하게 큰 단일 파일** — 분리 필요 |
| `permanent_memory.py` | 982 | 영구기억 (Imprint, Frozen) | 🟢 적정 |
| `memory_manager.py` | 809 | STM/LTM 라이프사이클 핵심 엔진 | 🟢 잘 구조화됨 |
| `neo4j_storage.py` | 813 | Neo4j CRUD 기본 작업 | 🟢 적정 |
| `data_product.py` | 782 | RAG 코퍼스, 스냅샷, 트레이닝셋 내보내기 | 🟡 리팩터링 고려 |
| `reconciliation_service.py` | 602 | Neo4j ↔ Supermemory 데이터 정합 | 🟢 적정 |
| `terminology_service.py` | 542 | 용어 거버넌스 | 🟢 적정 |
| `memory_audit.py` | 456 | 변경 이력 + 롤백 | 🟢 적정 |
| `synaptic_bridge.py` | 416 | 다중 에이전트 기억 공유 | 🟢 적정 |
| `memory_scopes.py` | 316 | Personal→Tribal→Social→Global 스코프 | 🟢 적정 |
| 기타 9개 | ~2,470 | 검색, 하이브리드, 임베딩, NER, 스키마 | 🟢 |

**핵심 관찰**: 
- `memory_categories.py`가 2,410 LOC로 단일 최대 파일. 10개 이상의 카테고리가 한 파일에 혼재함
- 전반적으로 Storage 레이어는 **잘 분리**되어 있으나, God Object 패턴이 일부 관찰됨

### 2.2 Services Layer (11,997 LOC — 30%)

| 파일 | LOC | 역할 | 복잡도 평가 |
|------|-----|------|------------|
| `report_agent.py` | 2,579 | 보고서 생성 에이전트 | 🔴 **극단적 파일 크기** — 모듈 분리 필수 |
| `simulation_runner.py` | 1,788 | 시뮬레이션 실행 엔진 | 🔴 **과도한 단일 책임** |
| `graph_tools.py` | 1,496 | 그래프 분석 유틸리티 | 🟡 큰 편 — 분리 고려 |
| `oasis_profile_generator.py` | 1,140 | OASIS 소셜 프로필 생성 | 🟡 레거시 기능, 코어 미사용 |
| `simulation_config_generator.py` | 987 | 시뮬레이션 설정 생성기 | 🟡 레거시 기능 |
| `simulation_manager.py` | 531 | 시뮬레이션 관리자 | 🟢 |
| `graph_memory_updater.py` | 488 | 그래프 메모리 갱신 | 🟢 |
| `ontology_generator.py` | 408 | 온톨로지 자동 생성 | 🟢 |
| 기타 12개 | ~2,580 | 파이프라인, 스케줄러, 텍스트 처리 등 | 🟢 |

**핵심 관찰**:
- **시뮬레이션 관련 코드 (~4,500 LOC)가 전체 서비스의 37%** 를 차지하지만, 인지 메모리 코어 기능은 아님
- `report_agent.py`는 원본 MiroFish에서 이관된 레거시 — 코어 리팩터링 시 분리/삭제 후보

### 2.3 API Layer (8,323 LOC — 21%)

| 파일 | LOC | 역할 |
|------|-----|------|
| `simulation.py` | 2,715 | 시뮬레이션 API 엔드포인트 |
| `analytics.py` | 1,375 | 메모리 분석/성숙도/보고서 |
| `memory.py` | 1,309 | 메모리 CRUD, STM/LTM 작업 |
| `ingest.py` | 714 | 데이터 수집 파이프라인 |
| `graph.py` | 659 | 그래프 CRUD, Cypher 쿼리 |
| `admin.py` | 538 | 관리자 기능, API 키 |
| `core.py` | 450 | 헬스체크, 라우팅, 정적파일 |
| `harness_analytics.py` | 476 | 하네스 트렌드/분석 |
| `terminology.py` | 87 | 용어 거버넌스 API |

### 2.4 Harness Layer (4,962 LOC — 12%)

| 디렉토리/파일 | LOC | 역할 |
|-------------|-----|------|
| `harness_runtime.py` | 661 | 워크플로우 런타임 엔진 (v2) |
| `executors/` (~7 files) | ~1,400 | Ray, Nomad, Wasm, Container, Parallel, HITL |
| `orchestration/` (~5 files) | ~1,300 | Auto-Healer, Memory Bridge, MCP Backend |
| `memory/` (~2 files) | ~360 | Tool Memory Index, Workflow Recall |
| `planner/` | ~340 | 자율 계획 엔진 |
| `evolution_engine.py` | 160 | 패턴 진화 엔진 |
| `metrics_store.py` | 200 | 실행 메트릭 저장 |
| DSL/기타 | ~540 | JSON Schema, 시나리오 헬퍼 |

### 2.5 Security & Resilience (1,452 LOC — 4%)

| 파일 | LOC | 역할 |
|------|-----|------|
| `memory_encryption.py` | 470 | AES-256 필드 암호화 |
| `memory_rbac.py` | 380 | 역할 기반 접근 제어 |
| `memory_maturity.py` | 393 | 지식 성숙도 모델 |
| `circuit_breaker.py` | 110 | 장애 격리 패턴 |
| `outbox_worker.py` | 49 | 비동기 재시도 + DLQ |

---

## 3. 테스트 현황

### 3.1 테스트 분포

| 유형 | 파일 수 | 테스트 수 | Pass | Fail | Error |
|-------|--------|----------|------|------|-------|
| **Harness** | 26 | 128 | 120 | 1 | 7 |
| **Unit** | 6 | ~20* | 미실행 | - | - |
| **Integration** | 5 | ~25* | 미실행 | - | - |
| **E2E** | 9 | ~35* | 미실행 | - | - |

*Unit/Integration/E2E 테스트는 Neo4j 연결 필요로 이번 감사에서 미실행

### 3.2 테스트 품질 분석

**강점**:
- 하네스 모듈의 테스트 커버리지가 매우 두터움 (26개 파일, 2,729 LOC)
- DSL 스키마 유효성, Executor 레지스트리, LLM Healer, Memory Bridge 등 핵심 경로 모두 테스트

**약점**:
- Unit/Integration 테스트가 실제 Neo4j 인스턴스에 의존 — **CI/CD 파이프라인 구축 불가**
- Mock/Stub 패턴이 하네스에만 적용, 코어 메모리 엔진에는 미적용
- `test_container_executor.py`: Docker 소켓 의존으로 환경별 실패
- E2E Neo4j 통합 테스트 7건이 연결 오류로 ERROR 상태

### 3.3 코드 품질 지표

| 지표 | 값 | 판정 |
|------|---|------|
| TODO/FIXME 마커 | 2건 | 🟢 매우 적음 |
| `exec()` 사용 | 1건 (`ray_executor.py:109`) | 🟡 보안 리스크 |
| 하드코딩된 IP | 3건 (MCP 서버, 환경설정) | 🟡 환경 변수화 필요 |
| 중복 코드 패턴 | 중간 수준 (Cypher 쿼리 구성) | 🟡 쿼리 빌더 패턴 도입 필요 |
| 타입 힌트 | 80% 이상 적용 | 🟢 양호 |
| 독스트링 | 핵심 클래스 90% 이상 | 🟢 양호 |

---

## 4. 의존성 분석

### 4.1 핵심 의존성 (필수)

| 패키지 | 버전 | 용도 | 라이선스 |
|--------|------|------|---------|
| Flask | ≥3.0.0 | 웹 프레임워크 | BSD |
| neo4j | ≥5.15.0 | 그래프 DB 드라이버 | Apache 2.0 |
| requests | ≥2.28.0 | HTTP 클라이언트 | Apache 2.0 |
| openai | ≥1.0.0 | LLM API | MIT |
| prometheus_client | - | 메트릭 수집 | Apache 2.0 |

### 4.2 선택적 의존성 (무거움)

| 패키지 | 용도 | 크기 | 코어 필수 여부 |
|--------|------|------|---------------|
| camel-oasis/camel-ai | 소셜 시뮬레이션 | ~500MB+ | ❌ 레거시 |
| PyMuPDF | PDF 처리 | ~50MB | ❌ 어댑터 전용 |
| torch | ML 프레임워크 | ~2GB+ | ❌ 임베딩 전용 |
| pandas | 데이터 분석 | ~50MB | ❌ 내보내기 전용 |

**핵심 문제**: `requirements.txt`에 선택적 의존성이 필수로 포함됨 → 설치 시간 10분 이상, 디스크 3GB+ 사용

### 4.3 권장 조치
1. `requirements.txt`를 `core`, `ml`, `simulation`, `adapters`로 분리
2. `pip install mories[core]` / `mories[ml]` 패턴 도입
3. torch/camel-oasis 의존성을 선택적 extras로 전환

---

## 5. 레거시 코드 분석

### MiroFish 원본 잔존 코드

프로젝트가 MiroFish-Offline에서 Supermemory로 통합되면서, 원래 "지식 그래프 시각화" 목적의 코드가 상당량 잔존합니다.

| 모듈 | LOC | 상태 | 권고 |
|------|-----|------|------|
| `report_agent.py` | 2,579 | 🔴 레거시 | 분리/삭제 — 코어 메모리와 무관 |
| `simulation_*.py` (3개) | ~3,300 | 🔴 레거시 | OASIS 시뮬레이션 → 별도 패키지 |
| `oasis_profile_generator.py` | 1,140 | 🔴 레거시 | 코어 미사용 |
| `simulation.py` (API) | 2,715 | 🔴 레거시 | 분리 필요 |
| **소계** | ~9,734 | | 전체 코어의 **24%가 레거시** |

### 레거시 제거 시 효과
- 코어 LOC: 39,973 → **~30,239** (24% 감소)
- 의존성: torch, camel-oasis, scipy, pandas 제거 가능
- 설치 크기: 3GB+ → **~200MB**
- 유지보수 부담 대폭 감소

---

## 6. 요약

### 코드베이스 건강도: ⭐⭐⭐ (3/5)

**강점**: 모듈화 된 아키텍처, 풍부한 기능 세트, 양호한 타입 힌트와 독스트링  
**약점**: 레거시 코드 혼재, 거대 파일 존재, 선택적 의존성 미분리, CI/CD 파이프라인 부재

**최우선 개선 3건**:
1. 레거시 시뮬레이션 코드 분리 (즉시 24% LOC 감소)
2. `requirements.txt` extras 분리 (설치 시간 90% 단축)
3. Neo4j Mock 기반 단위 테스트 재설계 (CI/CD 해금)
