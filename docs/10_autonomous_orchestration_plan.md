# Autonomous Agentic Orchestration — Enhancement Plan

> **Version:** 1.0  
> **Date:** 2026-04-05  
> **Scope:** Mories Harness v3 → v4 (Autonomous Agent Workflow Engine)

---

## Part 1: Current Code Health Assessment

### 1.1 Test Status
- **57 tests PASSED** (1 deselected: Ollama live test)
- Core modules: MetricsStore, EvolutionEngine, ExecutionTree, MemoryBridge, LLMHealer: ALL GREEN

### 1.2 Identified Code Issues

| # | Severity | Location | Issue | Fix |
|---|----------|----------|-------|-----|
| 1 | ⚠️ Medium | `harness_runtime.py:476` | `_handle_parallel()` — 순차 에뮬레이션만 구현, 실제 병렬 처리 없음 | `asyncio.gather` 또는 `concurrent.futures.ThreadPoolExecutor` 적용 |
| 2 | ⚠️ Medium | `harness_runtime.py:279` | `'step_id' in dir()` — 변수 존재 확인에 `dir()` 사용 (비표준) | `locals().get('step_id', 'unknown')` 로 변경 |
| 3 | 🟡 Low | `harness_runtime.py:210-212` | v3 import가 `__init__` 내부에서 수행 (재귀적 호출 시 비효율) | 모듈 상단으로 이동 또는 `lazy_import` 패턴 |
| 4 | 🟡 Low | `harness_runtime.py:300-301` | `run()` 메서드 내부에서도 `from ... import RunSummary` 반복 | 상단 import 통합 |
| 5 | ⚠️ Medium | `workflow_dsl_schema.json:4` | Schema title이 "v2"로 유지, 실제는 v3 필드 포함 | "v3"로 업데이트 |
| 6 | 🟡 Low | `harness_orchestrator.py:51` | `memory_bridge or MemoryBridge()` — backend=None인 MemoryBridge 기본 생성시 publish 호출이 NoneType 에러 유발 가능 | 초기화 시 guard 추가 |
| 7 | 🔴 High | `dashboard/harness.html:636` | `suggestEvolve` querySelector 내부에서 동적 uuid 바인딩 시 DOM에 동일 onclick 문자열이 정확히 매칭되지 않을 수 있음 | `data-uuid` attribute 기반 선택으로 변경 |
| 8 | 🟡 Low | `analytics.py` | API 파일이 1339줄로 비대화 (maturity + reconciliation + harness 통합) | 하네스 API를 별도 Blueprint로 분리 고려 |

### 1.3 Architecture Gaps for Autonomous Orchestration

현재 아키텍처에서 자율 에이전트 오케스트레이션을 위해 **빠져 있는 핵심 계층**:

```
┌─────────────────────────────────────────────────────────────────────┐
│ MISSING LAYERS (현재 없음)                                           │
├─────────────────────────────────────────────────────────────────────┤
│ 1. Agent Registry          — 에이전트 ID/역할/능력 등록              │
│ 2. Task Planner            — 워크플로우 DAG 자동 분해 + 할당          │
│ 3. True Parallel Executor  — asyncio / Ray / Docker 기반 병렬 실행   │
│ 4. HITL Gate               — 사람 승인/피드백 대기 (approval step)     │
│ 5. Remote Executor         — Nomad/Docker/Ray job dispatch           │
│ 6. Tool Memory Index       — 도구별 성공률/비용/속도 통계연동          │
│ 7. Autonomous Planner      — 결과 기반 다음 액션 자율 선택            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Part 2: Autonomous Agentic Orchestration Architecture (v4)

### 2.1 Target Architecture

```
                     ┌────────────────────────────────────────────────────┐
                     │            Autonomous Orchestration Layer          │
                     │                                                    │
                     │  ┌──────────┐  ┌──────────┐  ┌─────────────────┐  │
                     │  │ Agent    │  │ Task     │  │Autonomous       │  │
                     │  │ Registry │→ │ Planner  │→ │Planner (LLM)    │  │
                     │  │ (roles,  │  │ (DAG     │  │(결과 기반 자율    │  │
                     │  │ caps,    │  │  분해,   │  │ 다음 작업 선택)   │  │
                     │  │ tools)   │  │  할당)   │  │                  │  │
                     │  └──────────┘  └──────────┘  └─────────────────┘  │
                     │        ↓              ↓              ↓             │
                     │  ┌─────────────────────────────────────────────┐  │
                     │  │           Execution Engine (v4)              │  │
                     │  │  ┌────────┐ ┌────────┐ ┌────────┐          │  │
                     │  │  │Serial  │ │Parallel│ │Branch  │          │  │
                     │  │  │Execute │ │Execute │ │Execute │          │  │
                     │  │  └────────┘ └────────┘ └────────┘          │  │
                     │  │  ┌────────┐ ┌────────┐ ┌────────┐          │  │
                     │  │  │Loop    │ │HITL    │ │Autono- │          │  │
                     │  │  │Execute │ │Gate    │ │mous    │          │  │
                     │  │  │        │ │(human) │ │Select  │          │  │
                     │  │  └────────┘ └────────┘ └────────┘          │  │
                     │  └─────────────────────────────────────────────┘  │
                     │        ↓              ↓              ↓             │
                     │  ┌─────────────────────────────────────────────┐  │
                     │  │           Remote Execution Backends          │  │
                     │  │  ┌────────┐ ┌────────┐ ┌────────┐          │  │
                     │  │  │Local   │ │Docker  │ │Ray     │          │  │
                     │  │  │Process │ │Container│ │Cluster │          │  │
                     │  │  └────────┘ └────────┘ └────────┘          │  │
                     │  │  ┌────────┐ ┌────────┐                      │  │
                     │  │  │Nomad   │ │SSH     │                      │  │
                     │  │  │Job     │ │Remote  │                      │  │
                     │  │  └────────┘ └────────┘                      │  │
                     │  └─────────────────────────────────────────────┘  │
                     │        ↓              ↓              ↓             │
                     │  ┌─────────────────────────────────────────────┐  │
                     │  │           Mories Memory Layer               │  │
                     │  │  ┌────────────┐ ┌──────────────┐            │  │
                     │  │  │MemoryBridge│ │Tool Memory   │            │  │
                     │  │  │(Experience │ │Index (도구별  │            │  │
                     │  │  │ routing)   │ │성공률/비용)   │            │  │
                     │  │  └────────────┘ └──────────────┘            │  │
                     │  │  ┌────────────┐ ┌──────────────┐            │  │
                     │  │  │Neo4j KG    │ │Human Feedback│            │  │
                     │  │  │(patterns,  │ │Memory (HITL  │            │  │
                     │  │  │ experience)│ │ 경험 학습)    │            │  │
                     │  │  └────────────┘ └──────────────┘            │  │
                     │  └─────────────────────────────────────────────┘  │
                     └────────────────────────────────────────────────────┘
```

### 2.2 신규 DSL Step Types

기존 8가지(`code`, `api_call`, `webhook`, `branch`, `loop`, `parallel`, `wait`, `end`)에 추가:

| Step Type | 설명 | 핵심 필드 |
|-----------|------|-----------|
| `agent_dispatch` | 특정 에이전트에게 태스크 할당 | `agent_id`, `task`, `timeout` |
| `hitl_gate` | 사람 승인/피드백 대기 | `prompt`, `approval_required`, `timeout` |
| `autonomous_select` | LLM이 실행 결과 분석 후 다음 액션 자율 선택 | `candidates[]`, `context_keys`, `selection_strategy` |
| `container_exec` | Docker 컨테이너 내 코드 실행 | `image`, `command`, `volumes`, `env` |
| `ray_submit` | Ray cluster에 작업 제출 | `runtime_env`, `entrypoint`, `resources` |
| `nomad_job` | HashiCorp Nomad에 작업 디스패치 | `job_spec`, `nomad_addr`, `token` |

### 2.3 Agent Registry 설계

```python
@dataclass
class AgentProfile:
    agent_id: str               # "researcher-01"
    role: str                   # "data_analyst"
    capabilities: List[str]     # ["python", "sql", "web_search"]
    tools: List[str]            # ["mcp_neo4j", "mcp_n8n", "docker_exec"]
    max_concurrent_tasks: int   # 3
    endpoint: Optional[str]     # "http://agent-01:8080" (원격 에이전트)
    status: str                 # "idle" | "busy" | "offline"
    success_rate: float         # Mories에서 자동 계산
    avg_latency_ms: int
```

### 2.4 Autonomous Planner (자율 선택 메커니즘)

핵심 루프: **Observe → Orient → Decide → Act** (OODA)

```python
class AutonomousPlanner:
    """결과 기반으로 다음 작업을 자율 선택하는 LLM 플래너."""
    
    def plan_next(
        self,
        current_result: dict,      # 방금 완료된 스텝 결과
        candidates: List[dict],    # 가능한 다음 액션 목록
        execution_history: list,   # 지금까지의 실행 히스토리
        memory_context: dict,      # Mories에서 관련 기억 검색 결과
        human_feedback: Optional[str],  # HITL 피드백 (있을 경우)
    ) -> dict:
        """
        Returns: {"selected_action": str, "reason": str, "confidence": float}
        """
```

### 2.5 Tool Memory Index (도구 기억+통계 연동)

현재 MetricsStore의 StepMetric을 확장하여 도구별 글로벌 통계를 추적:

```python
@dataclass
class ToolMemoryRecord:
    tool_name: str
    tool_type: str              # "mcp", "api", "docker", "ray", "nomad"
    total_executions: int
    success_rate: float
    avg_latency_ms: int
    avg_cost_usd: float
    last_failure_reason: str
    reliability_score: float     # 0.0~1.0 (종합 신뢰도)
    domains_used: List[str]      # 어떤 도메인에서 사용됐는지
```

---

## Part 3: Phased Implementation Roadmap

### Phase 3A: 핵심 인프라 (Execution Engine v4)

| # | 모듈 | 파일 | 설명 | 예상 공수 |
|---|------|------|------|-----------|
| 1 | True Parallel Executor | `harness/executors/parallel_executor.py` | `asyncio.gather` + `ThreadPoolExecutor` 실제 병렬 실행 | 4h |
| 2 | Container Executor | `harness/executors/container_executor.py` | Docker SDK를 통한 컨테이너 내 코드 실행 + 결과 수집 | 6h |
| 3 | Ray Executor | `harness/executors/ray_executor.py` | Ray job submit + 결과 polling | 4h |
| 4 | Nomad Executor | `harness/executors/nomad_executor.py` | Nomad HTTP API로 job dispatch + 결과 polling | 4h |
| 5 | Executor Registry | `harness/executors/__init__.py` | step_type → executor 매핑 (pluggable) | 2h |

### Phase 3B: 에이전트 + 자율 계획

| # | 모듈 | 파일 | 설명 | 예상 공수 |
|---|------|------|------|-----------|
| 6 | Agent Registry | `harness/agents/agent_registry.py` | 에이전트 등록/조회/상태관리 | 4h |
| 7 | Task Planner (DAG) | `harness/planning/task_planner.py` | 워크플로우를 DAG로 분해 + 에이전트 할당 | 6h |
| 8 | Autonomous Planner | `harness/planning/autonomous_planner.py` | LLM 기반 OODA 자율 선택 | 6h |
| 9 | HITL Gate | `harness/gates/hitl_gate.py` | 사람 승인/피드백 대기 (webhooks + polling) | 4h |
| 10 | Tool Memory Index | `harness/memory/tool_memory_index.py` | 도구별 성공률/비용/속도 통계 | 4h |

### Phase 3C: 기억 연동 + 자기개선

| # | 모듈 | 파일 | 설명 | 예상 공수 |
|---|------|------|------|-----------|
| 11 | Human Feedback Memory | `orchestration/human_feedback_memory.py` | HITL 피드백을 Mories KG에 저장 + 학습 | 4h |
| 12 | Workflow Recall Engine | `orchestration/workflow_recall.py` | 새 태스크 - 유사 과거 워크플로우 자동 검색/추천 | 4h |
| 13 | Cross-Domain Transfer | `orchestration/cross_domain_transfer.py` | 한 도메인의 성공 패턴을 다른 도메인으로 포크 | 3h |
| 14 | DSL Schema v4 | `harness/workflow_dsl_schema_v4.json` | 신규 step types 반영 | 2h |
| 15 | E2E Integration Tests | `tests/harness/test_autonomous_*.py` | 전체 파이프라인 통합 테스트 | 6h |

### 총 예상 공수: ~63시간 (3 Phases)

---

## Part 4: Decision Matrix — 작업 우선순위

```
   높은 가치 / 빠른 구현              높은 가치 / 복잡한 구현
   ┌─────────────────────┬──────────────────────┐
   │ ★ True Parallel     │ ★ Autonomous Planner │
   │ ★ Container Exec    │ ★ Task Planner (DAG) │
   │ ★ Tool Memory Index │ ★ Cross-Domain Xfer  │
   │ ★ DSL v4 Schema     │                      │
   ├─────────────────────┼──────────────────────┤
   │   HITL Gate         │   Nomad Executor     │
   │   Agent Registry    │   Ray Executor       │
   │   HF Memory         │   Workflow Recall    │
   └─────────────────────┴──────────────────────┘
   낮은 가치 / 빠른 구현              낮은 가치 / 복잡한 구현
```

**추천 실행 순서:**
1. **Phase 3A-1~2**: True Parallel + Container Executor (가장 즉각적 가치)
2. **Phase 3A-5 + 3B-10**: Executor Registry + Tool Memory Index (기억 연동)
3. **Phase 3B-9**: HITL Gate (사람 피드백)
4. **Phase 3B-6~8**: Agent Registry + Task Planner + Autonomous Planner (자율 핵심)
5. **Phase 3A-3~4**: Ray + Nomad (원격 인프라)
6. **Phase 3C-11~15**: 기억 고도화 + 테스트

---

## Part 5: DSL v4 Example — Autonomous Multi-Agent Workflow

```json
{
  "harness_id": "auto-research-pipeline",
  "version": 4,
  "domain": "data_science",
  "description": "자율 연구 파이프라인 — 데이터 수집, 분석, 보고서 생성",
  "agents": {
    "researcher": {"role": "data_collector", "tools": ["web_search", "api_call"]},
    "analyst": {"role": "data_analyst", "tools": ["python", "docker_exec"]},
    "writer": {"role": "report_writer", "tools": ["llm_generate", "api_call"]}
  },
  "steps": [
    {
      "id": "collect_data",
      "type": "agent_dispatch",
      "agent_id": "researcher",
      "task": "Collect latest papers on ${env.TOPIC}",
      "output_key": "papers"
    },
    {
      "id": "analyze_parallel",
      "type": "parallel",
      "executor": "ray",
      "branches": ["statistical_analysis", "sentiment_analysis"],
      "join_strategy": "wait_all"
    },
    {
      "id": "statistical_analysis",
      "type": "container_exec",
      "image": "python:3.11-slim",
      "command": "python /app/stats.py --data ${collect_data.papers}",
      "output_key": "stats_result"
    },
    {
      "id": "sentiment_analysis",
      "type": "container_exec",
      "image": "python:3.11-slim",
      "command": "python /app/sentiment.py --data ${collect_data.papers}",
      "output_key": "sentiment_result"
    },
    {
      "id": "review_gate",
      "type": "hitl_gate",
      "prompt": "분석 결과를 검토해주세요. 보고서 생성을 진행할까요?",
      "approval_required": true,
      "show_data": ["stats_result", "sentiment_result"],
      "timeout_seconds": 3600
    },
    {
      "id": "decide_next",
      "type": "autonomous_select",
      "candidates": [
        {"id": "generate_report", "condition": "approval == true"},
        {"id": "refine_analysis", "condition": "feedback contains '재분석'"},
        {"id": "end_pipeline", "condition": "approval == false"}
      ],
      "context_keys": ["stats_result", "sentiment_result", "review_gate.feedback"],
      "selection_strategy": "llm_reasoning"
    },
    {
      "id": "generate_report",
      "type": "agent_dispatch",
      "agent_id": "writer",
      "task": "Generate comprehensive report from ${stats_result} and ${sentiment_result}",
      "output_key": "report"
    },
    {
      "id": "deploy_report",
      "type": "nomad_job",
      "job_spec": {
        "ID": "report-publisher",
        "Type": "batch",
        "TaskGroups": [{
          "Tasks": [{
            "Driver": "docker",
            "Config": {"image": "report-publisher:latest"},
            "Env": {"REPORT_PATH": "${generate_report.report}"}
          }]
        }]
      }
    },
    {"id": "end_pipeline", "type": "end"}
  ],
  "evolution": {
    "auto_fix": true,
    "capture_new_patterns": true,
    "autonomous_learning": true
  },
  "memory": {
    "recall_similar_before_run": true,
    "store_human_feedback": true,
    "tool_memory_tracking": true
  }
}
```

---

## Part 6: Key Design Principles

1. **Mories-First** — 모든 실행 경험(성공/실패/HITL피드백/자율결정)은 Mories KG로 자동 라우팅
2. **Executor is Pluggable** — Local/Docker/Ray/Nomad 백엔드 자유 교체
3. **Memory-Guided Autonomy** — 자율 선택 시 과거 기억(유사 워크플로우 성공/실패)을 LLM 컨텍스트로 주입
4. **HITL as Memory** — 사람 피드백이 단순 approval이 아닌 "경험 기억"으로 축적되어 향후 자동화에 반영
5. **Tool Memory = Agent Brain** — 도구를 사용할 때마다 성공률/비용/지연 통계가 Tool Memory Index에 축적, 에이전트가 도구 선택 시 참고
6. **Backward Compatible** — 기존 v3 DSL은 v4에서도 그대로 동작
