# Harness Operations Guide v4

> **Updated:** 2026-04-05  
> **Covers:** Harness v4 (Autonomous Orchestrator + Knowledge Recall + Executor Registry)

---

## 1. Overview

The Mories Harness system is a **universal workflow execution engine** with built-in self-evolution, auto-healing, and cognitive memory integration. It enables AI agents to:

- Execute multi-step workflows defined in JSON DSL
- Automatically classify execution outcomes (SUCCESS / FAILURE / CAPTURED / HEALED)
- Self-repair failed workflows via LLM-powered or rule-based healing
- Store all execution experiences into the Mories Knowledge Graph for cross-domain reuse

## 2. Architecture Summary

```
┌──────────────────────── HarnessOrchestrator ────────────────────────┐
│                                                                      │
│  HarnessRuntime.run()                                               │
│    ├─ Step Executors: code, api_call, webhook, branch, loop,        │
│    │                  parallel, wait, end                            │
│    ├─ MetricsStore (SQLite) — per-step/per-run quality tracking     │
│    ├─ EvolutionEngine — 3-mode classification (FIX/DERIVED/CAPTURED)│
│    └─ ExecutionTree — Domain → Workflow → Run → Step hierarchy      │
│                                                                      │
│  On Failure → Auto-Heal Loop:                                        │
│    LLMHealerEngine (Ollama/vLLM/Dify + 5 rule-based fallbacks)     │
│                                                                      │
│  On Complete → MemoryBridge:                                         │
│    ├─ Neo4jBackend (direct graph write)                             │
│    ├─ McpBackend (MCP/REST/Local)                                   │
│    └─ 4-Type Routing:                                                │
│       SUCCESS  → LTM (high salience)                                 │
│       FAILURE  → Reflection (lesson learned)                         │
│       CAPTURED → Reusable Pattern                                    │
│       HEALED   → Both (reflection + LTM)                            │
└──────────────────────────────────────────────────────────────────────┘
```

## 3. Workflow DSL v3

Workflows are defined as JSON objects following the schema in `harness/workflow_dsl_schema.json`.

### Supported Step Types

| Type | Description | Key Fields |
|------|-------------|------------|
| `code` | Execute a Python function | `action`, `params`, `output_key` |
| `api_call` | Call an external REST API | `url`, `method`, `headers`, `body`, `timeout_seconds` |
| `webhook` | Fire event to n8n/Zapier | `url`, `body`, `timeout_seconds` |
| `branch` | Conditional routing | `condition`, `then`, `else` |
| `loop` | Iteration with max limit | `max_iterations`, `goto` |
| `parallel` | Concurrent step execution | `branches[]` |
| `wait` | Pause for timeout | `timeout_seconds` |
| `container_exec` | Run inside Docker | `image`, `command`, `env` |
| `ray` | Distributed execution via Ray | `script`, `cluster_config` |
| `nomad` | Remote execution via HashiCorp Nomad | `job_spec` |
| `hitl_gate` | Pause for human-in-the-loop feedback | `prompt`, `required_role` |
| `end` | Terminate workflow | — |

### Error Handling

Each step supports `on_error` with four strategies:
- `abort` (default) — Stop execution, raise error
- `skip` — Log error, continue to next step
- `retry` — Retry up to `retry_count` times (default: 3)
- `fallback` — Jump to `fallback_step`

### v3 Extensions

```json
{
  "cost_tracking": {
    "enabled": true,
    "token_price_input": 0.000003,
    "token_price_output": 0.000015
  },
  "evolution": {
    "auto_fix": true,
    "cascade_threshold": 0.5,
    "capture_new_patterns": true
  }
}
```

## 4. Monitoring Orchestration Logic

### A. 🔄 RETRY (재시도)
- **Trigger:** Temporary failures (timeout, rate limit, lock)
- **Action:** Agent retries with same/adjusted parameters
- **Ops Check:** High RETRY frequency → flaky API or load issue

### B. ⚠️ FALLBACK (대체)
- **Trigger:** Definitive failure, data unavailable
- **Action:** Agent switches to alternative tool/method
- **Ops Check:** Consistent FALLBACK → primary path broken

### C. 🤝 HANDOFF (역할 전환)
- **Trigger:** Agent lacks permissions/capabilities
- **Action:** Agent transfers context to specialized agent
- **Ops Check:** Frequent HANDOFF → incorrect routing or missing tools

## 5. Dashboard Features

The Harness Dashboard (`dashboard/harness.html`) provides:

### Pattern Grid
- Visual cards for all registered harness patterns
- Domain filtering and keyword search
- **Failure Alert** badges for patterns with <80% success rate
- Success rate bar indicators

### Detail Modal
- Full tool chain visualization (step flow)
- Data flow diagram (input → intermediate → output)
- Conditionals view (retry/fallback/handoff with icons)
- Statistics panel (exec count, success rate, avg time, cost)
- **Evolution Timeline** with rollback support

### Execution Tree
- Hierarchical view: Domain → Workflow → Run → Step
- Collapsible `<details>` nodes with status icons (✅ ❌ 🔸 🔻)
- Timing metadata per node
- Fetched via `GET /api/analytics/harness/<uuid>/tree`

### AI Evolution Suggestions
- LLM-powered workflow improvement recommendations
- Shows suggested new tool chain + conditionals + reasoning
- Connected to `POST /api/analytics/harness/<uuid>/suggest_evolution`

### Additional Capabilities
- **Recommend Search** — NL query → find similar patterns
- **AI Generate** — LLM generates new harness from description
- **Rollback** — Revert to previous version of a pattern
- **Edit Mode** — Inline editing of domain, trigger, tags

## 6. Memory Integration

### Neo4j Ontology
```
(:HarnessExperience {harness_id, domain, run_id, type, elapsed_ms, summary})
    -[:BELONGS_TO]→ (:Domain {name})

(:HarnessPattern {domain, tool_chain, trigger, execution_count})
    -[:BELONGS_TO]→ (:Domain {name})

(:Reflection {event, lesson, severity, domain})
```

### MemoryBridge Routing
| Experience Type | Memory Action |
|----------------|---------------|
| SUCCESS | → LTM (salience calculated from complexity + type) |
| FAILURE | → Reflection (high severity if >5s elapsed) |
| CAPTURED | → Pattern registration + LTM |
| HEALED | → Reflection + LTM (self-repair documentation) |
| DERIVED | → Pattern registration (cross-domain fork) |

### Scope Mapping
| Domain | Mories Scope |
|--------|-------------|
| engineering, devops, marketing, content, sales | tribal |
| platform, security, compliance | social |
| core | global |
| (others) | personal |

## 7. Auto-Healing Pipeline

```
Failure Detected
    │
    ├─ auto_fix enabled? ─No→ Record FAILURE → End
    │   │Yes
    ├─ LLM available? ─Yes→ LLMHealerEngine.heal_workflow()
    │   │No               │
    │   │                 ├─ Valid JSON fix? ─Yes→ Retry with patched workflow
    │   │                 │No
    │   ↓                 ↓
    └─ Rule-Based Fix (5 patterns):
       1. Nonexistent action → convert to wait step
       2. Timeout → double timeout_seconds
       3. Key error → add default_values
       4. Type error → convert to wait step
       5. Connection error → add retry config
```

## 8. CLI Usage

```bash
# Run a workflow from file
python -m src.app.harness.harness_runtime workflow.json

# Resume from checkpoint
python -m src.app.harness.harness_runtime workflow.json --resume

# Run all test scenarios
python -m src.app.harness.run_all_scenarios
```

## 9. Testing

```bash
# Run all harness tests (excluding live LLM)
python -m pytest tests/harness/ -v --tb=short -k "not WithOllama"

# Run with live LLM healing test
python -m pytest tests/harness/ -v --tb=short
```

**Current test coverage:** 57 tests (ALL PASSED)

| Module | Tests |
|--------|-------|
| MetricsStore | 4 |
| EvolutionEngine | 9 |
| ExecutionTree | 6 |
| Runtime v3 | 4 |
| Backward Compatibility | 4 |
| HarnessOrchestrator | 2 |
| MemoryBridge | 6 |
| Neo4j Integration (E2E) | 6 |
| LLMHealer | 10 |
| Live Integration | 4 |
| Thin Bridge | 2 |
