# 04. 하네스 오케스트레이션 엔진 심층 분석
> **Date**: 2026-04-06 | **Scope**: Harness v4 아키텍처, DSL, Executor, 자율 진화 메커니즘

---

## 1. 하네스 시스템 개요

### 1.1 설계 철학

> "워크플로우 실행이 단순한 작업 완료가 아니라, **시스템의 인지적 성장**으로 이어지는 자율 진화형 엔진"

```
┌─ Harness v4 Loop ─────────────────────────────────────────────┐
│                                                                  │
│  [Define]     [Execute]     [Learn]      [Evolve]              │
│  DSL JSON  →  Runtime   →  Memory   →   AI Healer            │
│               Engine       Bridge       Evolution              │
│     ↑                                       │                    │
│     └───────────────── Feedback ────────────┘                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 모듈 구성 (4,962 LOC)

```
src/app/harness/
├── harness_runtime.py          # 661 LOC — 워크플로우 런타임 (v2 엔진)
├── workflow_dsl_schema.json    # 355 LOC — JSON Schema v4
├── evolution_engine.py         # 160 LOC — 패턴 진화 로직
├── execution_tree.py           # 188 LOC — 실행 트리 시각화
├── metrics_store.py            # 200 LOC — SQLite 기반 메트릭
├── executors/                  # ~1,400 LOC — 7종 실행 엔진
│   ├── __init__.py             # 211 LOC — Executor Registry
│   ├── ray_executor.py         # 175 LOC — Ray 분산 실행
│   ├── nomad_executor.py       # 297 LOC — Nomad 스케줄링
│   ├── wasm_executor.py        # 307 LOC — Wasm 샌드박스
│   ├── container_executor.py   # 163 LOC — Docker 컨테이너
│   ├── parallel_executor.py    # 165 LOC — 병렬 실행
│   └── hitl_executor.py        # 85 LOC — Human-in-the-Loop
├── orchestration/              # ~1,300 LOC — 오케스트레이션 코어
│   ├── harness_orchestrator.py # 215 LOC — 작업 지시 허브
│   ├── llm_healer.py           # 280 LOC — LLM 자동 복구
│   ├── memory_bridge.py        # 270 LOC — 기억 다리
│   ├── neo4j_memory_backend.py # 370 LOC — Neo4j 메모리 저장소
│   └── mories_mcp_backend.py   # 165 LOC — MCP API 백엔드
├── memory/                     # ~360 LOC — 도구 기억 인덱스
│   ├── tool_memory_index.py    # 210 LOC — 도구별 성공률 추적
│   └── workflow_recall.py      # 150 LOC — 워크플로우 리콜
├── planner/                    # ~340 LOC — 자율 계획기
│   └── autonomous_planner.py   # 340 LOC — LLM 기반 계획 생성
├── agents/                     # 에이전트 인터페이스 (확장용)
└── workflows/                  # 사전 정의 워크플로우 예시
```

---

## 2. DSL (Domain Specific Language) 분석

### 2.1 DSL v4 스키마

```json
{
  "harness_id": "uuid",
  "domain": "engineering",
  "trigger": "자연어 트리거 조건",
  "steps": [
    {
      "id": "step_1",
      "type": "api_call | code | branch | loop | parallel | wait | webhook | hitl_gate | ray_remote | nomad_job | wasm_sandbox | container_exec",
      "params": { ... },
      "on_error": { "retry": 3, "fallback_step": "step_fallback" }
    }
  ],
  "state_storage": { "type": "json_file | sqlite | memory" }
}
```

### 2.2 지원되는 Step 타입 (12종)

| Type | 구현 상태 | 실행 환경 | 보안 수준 |
|------|----------|----------|----------|
| `api_call` | ✅ 완성 | requests.post/get | 🟡 URL 검증 없음 |
| `code` | ✅ 완성 | `exec()` 실행 | 🔴 **보안 위험** |
| `branch` | ✅ 완성 | 조건부 분기 | 🟢 안전 |
| `loop` | ✅ 완성 | 반복 실행 | 🟢 안전 |
| `parallel` | ✅ 완성 | ThreadPoolExecutor | 🟢 안전 |
| `wait` | ✅ 완성 | time.sleep | 🟢 안전 |
| `webhook` | ✅ 완성 | requests.post | 🟡 |
| `hitl_gate` | ✅ 완성 | Suspend/Resume | 🟢 안전 |
| `ray_remote` | ✅ 코드완성 | Ray Cluster | 🟡 미검증 |
| `nomad_job` | ✅ 코드완성 | Nomad Scheduler | 🟡 미검증 |
| `wasm_sandbox` | ✅ 코드완성 | Wasmtime subprocess | 🟢 샌드박스 격리 |
| `container_exec` | ✅ 코드완성 | Docker API | 🟡 권한 필요 |

### 2.3 DSL 강점과 한계

**강점**:
- 12종 step type으로 대부분의 자동화 시나리오 커버 가능
- `${step_id.output_key}` 변수 치환으로 데이터 파이프라이닝
- `on_error`로 step-level 장애 처리
- 상태 체크포인트로 중단/재개 가능

**한계**:
- JSON 기반 DSL → 개발자 경험(DX) 미흡 (YAML이나 Python DSL 대비)
- 조건 파서가 문자열 기반 (`==`, `!=`, `<`, `>`) → 복잡한 논리 표현 불가
- Sub-workflow 호출 미지원
- 타임아웃 설정이 step 수준에서만 가능 (전체 워크플로우 타임아웃 없음)
- 동적 step 생성 (반복 횟수 동적 결정 등) 제한적

---

## 3. Executor Registry 분석

### 3.1 레지스트리 아키텍처

```python
EXECUTOR_REGISTRY = {
    "ray_remote": RayExecutor,
    "nomad_job": NomadExecutor,
    "wasm_sandbox": WasmExecutor,
    "container_exec": ContainerExecutor,
    "parallel": ParallelExecutor,
    "hitl_gate": HitlExecutor,
    "code": PythonCodeExecutor,
    "api_call": ApiCallExecutor,
}
```

### 3.2 각 Executor 상세 분석

#### RayExecutor (175 LOC)
- **Lazy import**: ✅ `import ray`는 실행 시에만
- **기능**: 원격 Ray 클러스터에 Python 함수 제출
- **검증 상태**: ⚠️ 단위 테스트 통과, 실 클러스터 E2E 미완
- **보안**: 🟡 `exec()` → Script Injection 가능성
- **개선 필요**: Script 실행을 Wasm 또는 Docker 샌드박스 내부로 이동

#### NomadExecutor (297 LOC)
- **Lazy import**: ✅ `_get_requests()` 패턴 (이번 세션에서 수정)
- **기능**: HashiCorp Nomad에 배치 Job 제출, 상태 폴링
- **검증 상태**: ⚠️ Mock 테스트만 통과
- **주요 설정**: `NOMAD_ADDR`, `NOMAD_TOKEN`, `NOMAD_DOCKER_IMAGE`
- **개선 필요**: Parameterized Job 지원, Resource 제한 설정

#### WasmExecutor (307 LOC)
- **기능**: Wasmtime으로 격리된 Wasm 모듈 실행
- **보안**: ✅ 최고 수준 — 사실상 OS 수준 격리
- **검증 상태**: ✅ 7/7 Mock 테스트 통과
- **한계**: Wasm 바이너리 사전 컴파일 필요, 복잡한 I/O 불가
- **잠재력**: 🟢 가장 안전한 코드 실행 경로 — 기본 `code` step의 대체재

#### ContainerExecutor (163 LOC)
- **기능**: Docker API로 격리된 컨테이너 내 작업 실행
- **검증 상태**: ⚠️ Docker 소켓 의존 → 환경 불일치로 1건 실패
- **개선 필요**: Docker 소켓 없는 환경에서의 Graceful fallback

---

## 4. 자율 진화 메커니즘

### 4.1 Memory Bridge — 실행 경험의 기억화

```
[워크플로우 실행 완료]
        │
        ▼
[MemoryBridge.ingest_experience()]
        │
        ├── 결과 → Neo4j/:HarnessExecution 노드로 저장
        ├── 도구 사용 → ToolMemoryIndex 성공률 갱신
        └── 실패 패턴 → Reflection으로 기록
        │
        ▼
[ToolMemoryIndex.get_tool_reliability()]
    → 다음 실행 시 도구 선택에 반영
```

**평가**: 이 메커니즘은 **Mories의 가장 혁신적인 설계**입니다. 다만 현재는 도구 성공률 → 감쇠 수정에만 피드백이 연결되어 있고, **실행 경험 → 워크플로우 구조 자체의 자동 수정**까지는 아직 미구현.

### 4.2 LLM Healer — AI 기반 자동 복구

```
[Step 실행 실패]
        │
        ▼
[on_error.retry 소진]
        │
        ▼
[LLMHealer.diagnose_and_heal()]
        │
        ├── LLM에 에러 컨텍스트 전달
        ├── 수정된 step 파라미터 또는 대체 전략 생성
        └── 수정된 워크플로우로 재실행
```

**평가**: 개념적으로 우수하나, 실제 LLM 호출 비용과 latency가 실행 경로에 추가됨. 프로덕션에서는 **캐시된 복구 패턴** (이전 성공 치유 기록 재사용) 도입이 필요.

### 4.3 Evolution Engine — 패턴 버전 관리

```
harness_pattern v1 ──[evolve]──→ v2 ──[evolve]──→ v3
                                           │
                                  [rollback to v1]
```

**평가**: 깃과 유사한 버전 관리가 Neo4j 그래프에 구현됨. 진화 이력 추적, 롤백, AI 기반 진화 제안까지 갖춤. **다만 "자동 진화 트리거" (성공률 N% 이하 시 자동 진화) 는 아직 수동.**

---

## 5. 테스트 현황 (하네스 전용)

| 테스트 파일 | 테스트 수 | 결과 | 커버 범위 |
|------------|----------|------|---------|
| `test_dsl_schema.py` | 8 | ✅ | DSL 유효성 검증 |
| `test_executor_registry.py` | 5 | ✅ | 모든 Executor 등록 확인 |
| `test_wasm_executor.py` | 7 | ✅ | Wasm 실행/에러/타임아웃 |
| `test_parallel_executor.py` | 5 | ✅ | 병렬 실행/에러 전파 |
| `test_harness_orchestrator.py` | 6 | ✅ | 오케스트레이터 통합 |
| `test_llm_healer.py` | 8 | ✅ | Auto-Healing 시나리오 |
| `test_memory_bridge.py` | 5 | ✅ | 경험 수집/기억화 |
| `test_tool_memory.py` | 12 | ✅ | 도구 성공률/추천 |
| `test_task_dag.py` | 8 | ✅ | DAG 빌드/사이클 감지 |
| `test_human_feedback.py` | 5 | ✅ | 사용자 피드백 수집 |
| `test_autonomous_planner.py` | 6 | ✅ | LLM 계획 생성 |
| `test_evolution_engine.py` | 4 | ✅ | 진화/롤백 |
| `test_execution_tree.py` | 6 | ✅ | 실행 트리 시각화 |
| `test_metrics_store.py` | 5 | ✅ | SQLite 메트릭 저장 |
| `test_hitl_gate.py` | 4 | ✅ | HITL 게이트 |
| `test_runtime_v3.py` | 4 | ✅ | 런타임 호환성 |
| `test_backward_compatibility.py` | 3 | ✅ | v2/v3 호환 |
| `test_thin_bridge.py` | 2 | ✅ | Dify/n8n 연동 |
| `test_container_executor.py` | 3 | ⚠️ 1 FAIL | Docker 소켓 의존 |
| `test_e2e_neo4j_integration.py` | 7 | ❌ ERROR | Neo4j 연결 필요 |
| **합계** | **~128** | **120P/1F/7E** | |

---

## 6. 프로덕트화 갭 (Gap to Production)

### 🔴 Critical Gaps

| 갭 | 현재 | 프로덕션 요구사항 | 예상 공수 |
|---|------|-----------------|---------|
| **보안 샌드박스** | `exec()` 직접 실행 | Wasm/Container 내 격리 실행 | 2주 |
| **분산 E2E 검증** | Mock 테스트만 | Ray/Nomad 클러스터 부하 테스트 | 4주 |
| **워크플로우 모니터링** | SQLite 로그만 | 실시간 대시보드 + 알림 | 3주 |
| **실패 복구 검증** | 단위 테스트만 | Chaos Engineering 수준 검증 | 4주 |

### 🟡 Important Gaps

| 갭 | 예상 공수 |
|---|---------|
| Sub-workflow 호출 | 2주 |
| 동적 step 생성 | 1주 |
| 워크플로우 타임아웃 | 3일 |
| YAML DSL 지원 | 1주 |
| Python DSL (Fluent API) | 3주 |
| 자동 진화 트리거 | 1주 |
| 복구 패턴 캐싱 | 2주 |

---

## 7. 결론: 하네스의 가능성

### "메모리 통합 오케스트레이션"은 진정한 차별화 포인트

LangGraph, Temporal, n8n 중 어느 것도 **실행 경험을 인지 기억으로 축적하여 시스템 스스로 개선하는 폐쇄 루프**를 제공하지 않습니다. 이것이 Mories Harness의 핵심 가치입니다.

그러나 이 가치를 실현하려면:

1. **보안 샌드박스 강화** (`exec()` → Wasm 기본값)
2. **분산 실행의 실증** (단순 Mock이 아닌 실 클러스터 운영)
3. **개발자 DX** (JSON DSL → Python Fluent API)
4. **자동 진화 루프 완성** (성공률 기반 자동 트리거)

이 네 가지가 선행되어야 합니다. 현재 상태는 **"아이디어가 코드로 구현되어 있지만, 실전 검증이 부족한 R&D 프로토타입"** 수준입니다.
