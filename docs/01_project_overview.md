# 프로젝트 개요: MiroFish × Supermemory 통합

> **프로젝트명:** MiroFish-SuperMemory (코드명: **Mories** — 기억의 여신)  
> **작성일:** 2026-03-27  
> **상태:** 설계 단계

---

## 1. 프로젝트 비전

MiroFish-Offline의 **다중 에이전트 사회 시뮬레이션 엔진**과 Supermemory의 **ASMR(Agentic Search and Memory Retrieval) 기반 인지적 메모리 시스템**을 통합하여, **장기 기억과 시간 추론 능력을 갖춘 차세대 군집 지능 시뮬레이션 플랫폼**을 구축한다.

### 핵심 가치

| 기존 MiroFish-Offline 한계 | 통합 후 해결 |
|---|---|
| 벡터 0.7 + BM25 0.3 하이브리드 검색의 시간 추론 한계 | ASMR Search Agent의 시간 타임라인 재구성 |
| 시뮬레이션 라운드가 길어지면 과거/현재 정보 혼동 | Supermemory 자동 망각(Forgetfulness) + 모순 해결 |
| 에이전트 메모리가 시뮬레이션 내에서만 유효 (인메모리) | Supermemory 영구 메모리 + 사용자 프로필 |
| NER 기반 수동적 지식 추출 | Observer Agent의 능동적 인지 추출 (6축 병렬) |

---

## 2. 참조 프로젝트

| 프로젝트 | 경로 | 역할 |
|---|---|---|
| **MiroFish-Offline** | `references/MiroFish-Offline/` | 시뮬레이션 엔진 베이스 코드 |
| **Supermemory** | `references/supermemory/` | 메모리 API & ASMR 아키텍처 참조 |

---

## 3. 기술 스택 (계획)

| 계층 | 기술 |
|---|---|
| **시뮬레이션 엔진** | MiroFish-Offline (Flask, CAMEL-AI/OASIS) |
| **메모리 백엔드** | Supermemory API (또는 Self-hosted Supermemory) |
| **로컬 LLM** | Ollama (Qwen2.5, nomic-embed-text) |
| **지식 그래프 (폴백)** | Neo4j CE 5.15 |
| **프론트엔드** | Next.js (기존 MiroFish-Offline 프론트엔드 확장) |
| **배포** | Docker Compose |

---

## 4. 폴더 구조

```
mirofish-supermemory/
├── docs/                                ← 설계문서
│   ├── 01_project_overview.md           ← 이 문서
│   ├── 02_architecture_design.md        ← 통합 아키텍처 설계
│   ├── 03_integration_plan.md           ← 단계별 구현 계획
│   ├── 04_api_mapping.md                ← API 매핑 (GraphStorage ↔ Supermemory)
│   ├── 05_data_sources_design.md        ← 데이터 소스 확장 & 스트림 연계
│   ├── 06_reliability_security.md       ← 신뢰성 & 보안 설계
│   ├── 07_troubleshooting_and_deployment.md  ← 트러블슈팅 및 배포
│   ├── 08_project_handover.md           ← 인수인계 및 규칙 가이드
│   └── 09_harness_operations_guide.md   ← 하네스(Harness) 운영 및 모니터링 가이드
│
├── references/                          ← 참조 프로젝트 (git clone)
│   ├── MiroFish-Offline/                ← nikmcfly/MiroFish-Offline
│   └── supermemory/                     ← supermemoryai/supermemory
│
├── src/                                 ← 통합 코드 (구현 시 생성)
│   ├── storage/
│   │   ├── hybrid_storage.py            ← HybridStorage 구현
│   │   └── supermemory_client.py        ← Supermemory SDK 래퍼
│   ├── adapters/
│   │   ├── base.py                      ← SourceAdapter 추상 인터페이스
│   │   ├── file_adapters.py             ← PDF/DOCX/XLSX/HTML
│   │   ├── structured_adapters.py       ← CSV/JSON/Parquet
│   │   ├── stream_adapters.py           ← Kafka/WebSocket/Webhook
│   │   └── db_adapters.py              ← Neo4j Import/PostgreSQL/REST
│   ├── agents/
│   │   ├── observer_agent.py            ← ASMR Observer (3개 병렬)
│   │   └── search_agent.py             ← ASMR Search (3개 병렬)
│   ├── services/
│   │   ├── ingestion_service.py         ← DataIngestionService
│   │   └── reconciliation_service.py    ← Neo4j ↔ SM 정합성 검증
│   ├── resilience/
│   │   ├── circuit_breaker.py           ← Circuit Breaker
│   │   └── outbox_worker.py            ← Outbox 패턴 워커
│   └── config.py                        ← 확장 설정
│
└── tests/                               ← 테스트
    ├── unit/
    ├── integration/
    ├── e2e/
    └── fixtures/
```

---

## 5. 핵심 용어 정리

| 용어 | 설명 |
|---|---|
| **ASMR** | Agentic Search and Memory Retrieval — 벡터 DB 없이 에이전트가 직접 읽고 추론하는 메모리 검색 |
| **GraphStorage** | MiroFish-Offline의 추상 스토리지 인터페이스 (현재 Neo4jStorage만 구현) |
| **Observer Agent** | ASMR의 수집 에이전트 — 대화에서 구조화 지식 병렬 추출 |
| **Search Agent** | ASMR의 검색 에이전트 — 사실/맥락/시간을 전문적으로 검색 |
| **containerTag** | Supermemory에서 사용자/에이전트를 구분하는 태그 |
| **GraphMemoryUpdater** | MiroFish-Offline에서 시뮬레이션 활동을 그래프에 실시간 반영하는 서비스 |
| **ReportAgent** | 시뮬레이션 후 분석 보고서를 생성하는 에이전트 |
