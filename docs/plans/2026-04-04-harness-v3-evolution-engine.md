# Harness v3 Evolution Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** OpenSpace/CatchMe 인사이트를 적용하여 Harness v2를 3-Mode Self-Evolution, Cost Tracking, Hierarchical Execution Tree를 갖춘 v3로 고도화

**Architecture:** 기존 `harness_runtime.py` (493 lines)를 핵심으로 유지. 3개 신규 모듈 추가. 기존 DSL 하위 호환 보장.

**Tech Stack:** Python 3.11+, SQLite3 (stdlib), JSON Schema, pytest

**Recovery:** 각 Task가 독립 커밋 단위. 중단 시 마지막 커밋에서 재개 가능.

---

## 인사이트 재검토 결과

| # | 항목 | Phase | 근거 |
|---|---|---|---|
| 1 | 3-Mode Evolution (FIX/DERIVED/CAPTURED) | **1** | 현재 evolution 분류 없음. 임팩트 최대 |
| 2 | Quality Metrics Data Model | **1** | _log_step에 elapsed_ms만 존재 |
| 3 | Cost/Token Tracking | **1** | ROI 측정 기반 부재 |
| 4 | Hierarchical Execution Tree | **1** | flat list → 계층 구조 |
| 5 | SQLite Full Migration | **2** | JSON→SQLite 리스크 |
| 6 | Cascade Evolution | **2** | #1 선행 필요 |
| 7 | Quality Dashboard UI | **2** | 데이터 모델 선행 필요 |

---

## File Structure

```
src/app/harness/
├── harness_runtime.py          # MODIFY: v3 hooks 추가
├── evolution_engine.py         # CREATE: 3-Mode Evolution
├── metrics_store.py            # CREATE: SQLite Metrics + Cost
├── execution_tree.py           # CREATE: Hierarchical Tree
├── workflow_dsl_schema.json    # MODIFY: v3 필드 추가
tests/harness/
├── test_evolution_engine.py    # CREATE
├── test_metrics_store.py       # CREATE
├── test_execution_tree.py      # CREATE
├── test_runtime_v3.py          # CREATE: 통합 테스트
```

---

## Task 1: MetricsStore (SQLite 기반 품질/비용 추적)

**Files:** Create `metrics_store.py`, `test_metrics_store.py`

- [ ] Step 1: Write failing tests (3 test cases: record_step, record_run, get_harness_stats)
- [ ] Step 2: Run test → FAIL (ModuleNotFoundError)
- [ ] Step 3: Implement MetricsStore with StepMetric/RunSummary dataclasses + SQLite tables
- [ ] Step 4: Run test → 3 PASSED
- [ ] Step 5: Commit "feat(harness): add MetricsStore with SQLite cost/quality tracking"

**Key Types:**
- `StepMetric(run_id, harness_id, step_id, step_type, success, elapsed_ms, token_input, token_output, cost_usd, error)`
- `RunSummary(run_id, harness_id, domain, success, total_steps, elapsed_ms, total_cost_usd, evolution_mode)`
- `MetricsStore.get_harness_stats()` → success_rate, avg_elapsed, total_cost

---

## Task 2: 3-Mode Evolution Engine

**Files:** Create `evolution_engine.py`, `test_evolution_engine.py`

- [ ] Step 1: Write failing tests (7 cases: classify FIX/DERIVED/CAPTURED/None, suggest_fix, derive, cascade)
- [ ] Step 2: Run test → FAIL
- [ ] Step 3: Implement EvolutionEngine with EvolutionMode enum + classify/suggest/derive/capture/cascade methods
- [ ] Step 4: Run test → 7 PASSED
- [ ] Step 5: Commit "feat(harness): add 3-Mode Evolution Engine (FIX/DERIVED/CAPTURED)"

**Key API:**
- `classify_evolution(harness_id, run_success, error_msg, is_new_pattern, fork_to_domain) → EvolutionMode | None`
- `suggest_fix(harness_id, error_msg, failed_step_id) → recommendation dict`
- `derive(source_harness_id, target_domain) → fork metadata`
- `capture(execution_log, domain) → new pattern dict`
- `should_trigger_cascade(harness_id, threshold) → bool`

---

## Task 3: Hierarchical Execution Tree (CatchMe 패턴)

**Files:** Create `execution_tree.py`, `test_execution_tree.py`

- [ ] Step 1: Write failing tests (4 cases: add_run, summarize, search, to_dict roundtrip)
- [ ] Step 2: Run test → FAIL
- [ ] Step 3: Implement ExecutionTree with TreeNode dataclass, 4-level hierarchy (Domain→Workflow→Run→Step)
- [ ] Step 4: Run test → 4 PASSED
- [ ] Step 5: Commit "feat(harness): add Hierarchical Execution Tree"

**Key API:**
- `add_run(domain, workflow, run_id, steps)` — 계층에 실행 기록 추가
- `summarize(domain)` → total_runs, success_rate, workflows
- `search(query)` → 에러 메시지 기반 검색
- `to_dict() / from_dict()` → JSON 직렬화/역직렬화

---

## Task 4: Runtime v3 통합

**Files:** Modify `harness_runtime.py`, Create `test_runtime_v3.py`

- [ ] Step 1: Write integration tests (3 cases: metrics_summary, execution_tree, evolution_mode on failure)
- [ ] Step 2: Run test → FAIL (KeyError: metrics_summary)
- [ ] Step 3: Modify harness_runtime.py:
  - `__init__`: MetricsStore + EvolutionEngine + ExecutionTree 초기화
  - `_log_step`: StepMetric 기록 추가
  - `run()`: RunSummary 기록 + evolution 분류 + tree 추가 + 결과에 v3 필드 포함
- [ ] Step 4: Run ALL tests → 14+ PASSED
- [ ] Step 5: Commit "feat(harness): integrate v3 Evolution + Metrics + Tree into runtime"

---

## Task 5: DSL Schema v3 업데이트

**Files:** Modify `workflow_dsl_schema.json`

- [ ] Step 1: Add `cost_tracking` (enabled, token_price_input/output) and `evolution` (auto_fix, cascade_threshold, capture_new_patterns) to schema properties
- [ ] Step 2: Commit "feat(harness): update DSL schema to v3"

---

## Task 6: 최종 검증 + Mories LTM 기록

- [ ] Step 1: `pytest tests/harness/ -v --tb=short` → ALL PASSED
- [ ] Step 2: `python run_all_scenarios.py` → 3 scenarios 성공 (하위 호환)
- [ ] Step 3: Mories mories_ingest로 결과 기록
- [ ] Step 4: `git tag v3.0.0-evolution-engine`

---

## Self-Review

- [x] Spec coverage: 3-Mode Evolution ✓, Cost Tracking ✓, Hierarchical Tree ✓
- [x] No placeholders: 모든 API 시그니처 명시
- [x] Type consistency: StepMetric, RunSummary, EvolutionMode, TreeNode 일관
- [x] Backward compatible: 기존 workflow JSON에 v3 필드 없어도 동작
- [x] Recovery: 각 Task 독립 커밋, 중단 시 재개 가능
