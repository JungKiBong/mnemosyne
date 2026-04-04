# Mories Harness v3 — 세션 핸드오버 문서
**생성일:** 2026-04-04  
**프로젝트:** mirofish-supermemory  
**이전 대화 ID:** `7a6e7749-52a2-4131-8562-e42f37f1fa11`

---

## 1. 프로젝트 개요

**Mories**는 AI 에이전트를 위한 **인지 기억(Cognitive Memory) 시스템**입니다.  
현재 세션에서는 **Harness v3 Evolution Engine** — 하네스(워크플로우) 실행 경험을 Mories Knowledge Graph에 자동 유입하여 범용적으로 지식을 재활용하는 인프라를 구축했습니다.

---

## 2. 완료된 작업 (Phase 1~2 전체 완료)

### Phase 1: v3 Core Engine ✅
| # | 모듈 | 파일 | 테스트 |
|---|------|------|--------|
| 1 | MetricsStore (SQLite) | `harness/metrics_store.py` | 4/4 |
| 2 | EvolutionEngine (3-Mode) | `harness/evolution_engine.py` | 9/9 |
| 3 | ExecutionTree (Hierarchy) | `harness/execution_tree.py` | 6/6 |
| 4 | Runtime v3 Integration | `harness/harness_runtime.py` | 4/4 |
| 5 | DSL Schema v3 | `harness/workflow_dsl_schema.json` | valid |
| 6 | Backward Compatibility | — | 4/4 |

### Phase 2: Orchestration + Memory Bridge ✅
| # | 모듈 | 파일 | 테스트 |
|---|------|------|--------|
| 7 | HarnessOrchestrator | `orchestration/harness_orchestrator.py` | 2/2 |
| 8 | MemoryBridge | `orchestration/memory_bridge.py` | 6/6 |
| 9 | MoriesMcpBackend | `orchestration/mories_mcp_backend.py` | — |
| 10 | Neo4jMemoryBackend | `orchestration/neo4j_memory_backend.py` | 6/6 (E2E) |
| 11 | LLMHealerEngine | `orchestration/llm_healer.py` | 10/10 |

**총 테스트: 51개 (50 fast + 1 LLM live) — ALL PASSED**

---

## 3. 아키텍처

```
                    ┌── HarnessOrchestrator ──┐
                    │  HarnessRuntime.run()    │
                    │    ├─ MetricsStore       │← SQLite 품질/비용 추적
                    │    ├─ EvolutionEngine    │← FIX/DERIVED/CAPTURED
                    │    └─ ExecutionTree      │← Domain→WF→Run→Step
                    │                          │
                    │  실패 시 Auto-Heal:      │
                    │    LLMHealerEngine       │← Ollama/vLLM/Dify
                    │    ├─ LLM + Rule-Based   │
                    │                          │
                    │  결과 → MemoryBridge     │
                    │    ├─ Neo4jBackend       │← Direct Graph
                    │    ├─ McpBackend         │← MCP/REST/Local
                    │    └─ 4-Type Routing:    │
                    │       SUCCESS → LTM      │
                    │       FAILURE → Reflection│
                    │       CAPTURED → Pattern  │
                    │       HEALED → Both       │
                    └──────────────────────────┘
```

### Neo4j Harness Ontology
- `(:HarnessExperience)-[:BELONGS_TO]->(:Domain)`
- `(:HarnessPattern)-[:BELONGS_TO]->(:Domain)` (MERGE, 카운터 누적)
- `(:Reflection {event, lesson, severity})`

---

## 4. 다음 세션에서 할 작업 (Phase 3)

| 우선순위 | 항목 | 설명 |
|----------|------|------|
| **Done** | Dashboard UI 연동 | Dashboard 내 metrics.db (Cost, 평균 시간 등) 연동 및 수동 Edit 인터페이스 구축 완료 |
| **Done** | 외부 API Step (api_call) | Dify Agent App 호환 검증 완료 (Thin Bridge) |
| **Done** | 웹훅 Step (webhook) | n8n 이벤트 핸들링 검증 완료 (Thin Bridge) |
| **Canceled**| 병렬 처리 (parallel) | Mories 내부의 복잡한 실행(Bloatware) 방지를 위해 외부(n8n 등) 위임 |
| **Canceled**| Harness 스킬 자동화 고도화 | 복잡도 증가 방지를 위해 우선순위 하향 및 폐기 |

---

## 5. 핵심 설계 결정 (반드시 유지)

1. **MemoryBridge는 도메인 무관** — 어떤 시나리오든 동일 인터페이스
2. **Backend Protocol은 pluggable** — Neo4j/MCP/REST/Local 자동 전환
3. **4가지 경험 유형** (SUCCESS/FAILURE/CAPTURED/HEALED) → Mories 인지 채널로 자동 라우팅
4. **LLM Healer는 graceful degradation** — LLM 불가 시 5가지 rule-based 폴백 자동 적용
5. **기억 공간 분리** — Neo4j에는 관계/패턴만, SQLite에는 실행 데이터/로그

---

## 6. 환경 설정

| 항목 | 값 |
|------|-----|
| Python | `.venv/bin/python3` (3.10.13) |
| Neo4j | `bolt://localhost:7687` (user: `neo4j`, pw: `mirofish`) |
| Ollama | `http://localhost:11434/v1` |
| LLM 모델 | `qwen3:8b` (healer), `qwen3.5:9b` (available) |
| 프로젝트 루트 | `/Users/jungkibong/Projects/tmp/mirofish-supermemory` |
| 가상환경 | `/Users/jungkibong/Projects/tmp/mirofish-supermemory/.venv` |

---

## 7. 관련 파일 경로

### 소스
```
src/app/harness/
├── harness_runtime.py
├── metrics_store.py
├── evolution_engine.py
├── execution_tree.py
├── workflow_dsl_schema.json
└── orchestration/
    ├── harness_orchestrator.py
    ├── memory_bridge.py
    ├── neo4j_memory_backend.py
    ├── mories_mcp_backend.py
    └── llm_healer.py
```

### 테스트 (별도 디렉토리 — 삭제 용이)
```
tests/harness/
├── test_backward_compatibility.py
├── test_e2e_neo4j_integration.py
├── test_evolution_engine.py
├── test_execution_tree.py
├── test_harness_orchestrator.py
├── test_llm_healer.py
├── test_memory_bridge.py
├── test_metrics_store.py
└── test_runtime_v3.py
```

### 관리 문서
```
.agent/
├── mories_handover.md          ← 이 파일
├── troubleshooting_log.md      ← 트러블슈팅 이력
└── ...
```

---

## 8. 관련 커밋 이력

```
c4c2005 feat(orchestration): E2E Neo4j integration tests + LLM Healer with Ollama
1c00793 feat(orchestration): universal MemoryBridge + Neo4j/MCP backends
426a208 feat(orchestration): HarnessOrchestrator Auto-healing + Mories Sync
db1ad1e feat(harness): complete v3 Evolution Engine — 27 tests
20b1018 feat(harness): add v3 DSL schema fields
4d2474a feat(harness): integrate v3 Evolution + Metrics + Tree into runtime
15c05bf feat(harness): add Hierarchical Execution Tree
2a64e11 feat(harness): add 3-Mode Evolution Engine
89a5a9a feat(harness): add MetricsStore with SQLite
```
