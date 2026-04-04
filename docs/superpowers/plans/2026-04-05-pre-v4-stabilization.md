# Pre-v4 Stabilization & Remaining Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete 7 remaining items from `next_phase_plan.md.resolved` and stabilize codebase before Phase 3A (v4 Autonomous Orchestration)

**Architecture:** Refactoring + feature additions on existing v3 engine. No new architectural layers — pure code quality improvement and missing feature fill-in.

**Tech Stack:** Python 3.10, Flask, SQLite, Neo4j, Pytest

---

### Task 1: Move test_helpers.py to proper location

**Files:**
- Move: `src/app/harness/test_helpers.py` → `tests/harness/helpers/scenario_helpers.py`
- Create: `tests/harness/helpers/__init__.py`
- Modify: All files importing from `src.app.harness.test_helpers`

- [ ] **Step 1: Create helpers directory and copy file**

```bash
mkdir -p tests/harness/helpers
cp src/app/harness/test_helpers.py tests/harness/helpers/scenario_helpers.py
touch tests/harness/helpers/__init__.py
```

- [ ] **Step 2: Refactor global state to instance-based class**

In `tests/harness/helpers/scenario_helpers.py`, replace:

```python
"""
scenario_helpers.py — Harness v3 런타임 테스트용 헬퍼 함수 모듈

외부 의존성 없이 분기/반복/변수 치환 동작을 검증하기 위한 순수 Python 함수들.
Refactored: global state → class instance state.
"""


class ScenarioHelper:
    """Encapsulates test helper state to avoid global mutable state."""

    def __init__(self):
        self._deep_analysis_counter = 0

    def reset(self):
        self._deep_analysis_counter = 0


# Module-level functions remain for backward-compat import
_default = ScenarioHelper()
_deep_analysis_counter = 0


def generate_sensor_data(sensor_name: str, value: float) -> float:
    """센서 데이터를 시뮬레이션으로 생성한다."""
    print(f"  [test_helpers] 센서 '{sensor_name}' 값 생성: {value}")
    return value


def analyze_anomaly(reading: float) -> float:
    """이상치 심각도를 0.0~1.0 스케일로 반환한다."""
    try:
        reading_val = float(reading)
    except (TypeError, ValueError):
        reading_val = 50.0
    severity = min(1.0, max(0.0, (reading_val - 80) / 50))
    print(f"  [test_helpers] 이상 분석 완료: reading={reading_val} → severity={severity:.2f}")
    return severity


def deep_analyze(iteration: str = "auto") -> dict:
    """심층 분석을 수행한다 (반복 카운터 포함)."""
    global _deep_analysis_counter
    _deep_analysis_counter += 1
    result = {
        "iteration": _deep_analysis_counter,
        "finding": f"패턴 #{_deep_analysis_counter} 발견: 온도 스파이크 ↔ 촉매 반응 상관관계",
        "confidence": 0.6 + (_deep_analysis_counter * 0.1)
    }
    print(f"  [test_helpers] 심층 분석 #{_deep_analysis_counter}: {result['finding']}")
    return result
```

- [ ] **Step 3: Update runtime to find helpers in both locations**

In `src/app/harness/harness_runtime.py`, the `_execute_code_step` already uses `importlib.import_module(module_path)` to dynamically resolve modules. Ensure `tests/harness/helpers/scenario_helpers` is importable by keeping the old file as a thin re-export:

Replace `src/app/harness/test_helpers.py` with:

```python
"""
DEPRECATED: Use tests.harness.helpers.scenario_helpers instead.
This file remains for backward-compatible dynamic import from workflow JSON files
that reference 'src.app.harness.test_helpers'.
"""
from tests.harness.helpers.scenario_helpers import (  # noqa: F401
    generate_sensor_data,
    analyze_anomaly,
    deep_analyze,
    ScenarioHelper,
)
```

- [ ] **Step 4: Run all tests to verify no breakage**

Run: `cd /Users/jungkibong/Projects/tmp/mirofish-supermemory && .venv/bin/python3 -m pytest tests/harness/ -v --tb=short -k "not WithOllama"`
Expected: 57 passed (same as before)

- [ ] **Step 5: Commit**

```bash
git add tests/harness/helpers/ src/app/harness/test_helpers.py
git commit -m "refactor: move test_helpers to tests/harness/helpers with class-based state"
```

---

### Task 2: Add API input validation to PUT update_harness_detail

**Files:**
- Modify: `src/app/api/analytics.py:1047-1064`

- [ ] **Step 1: Add schema validation to the PUT handler**

In `src/app/api/analytics.py`, replace the `update_harness_detail` function:

```python
@analytics_bp.route('/harness/<uuid>', methods=['PUT'])
def update_harness_detail(uuid):
    """Update direct harness configuration metadata."""
    try:
        req = request.json
        if not req or not isinstance(req, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400
        
        # Allowed fields for update
        ALLOWED_FIELDS = {"domain", "trigger", "tags", "description", "scope", "tool_chain", "conditionals", "data_flow"}
        unknown_fields = set(req.keys()) - ALLOWED_FIELDS
        if unknown_fields:
            return jsonify({"error": f"Unknown fields: {', '.join(unknown_fields)}"}), 400

        # Type validation
        if "domain" in req and not isinstance(req["domain"], str):
            return jsonify({"error": "domain must be a string"}), 400
        if "trigger" in req and not isinstance(req["trigger"], str):
            return jsonify({"error": "trigger must be a string"}), 400
        if "tags" in req and not isinstance(req["tags"], list):
            return jsonify({"error": "tags must be a list"}), 400
        if "tool_chain" in req and not isinstance(req["tool_chain"], list):
            return jsonify({"error": "tool_chain must be a list"}), 400
        if "conditionals" in req and not isinstance(req["conditionals"], list):
            return jsonify({"error": "conditionals must be a list"}), 400

        # normalize toolchain if it exists  
        if "tool_chain" in req:
            req["tool_chain"] = _normalize_tool_chain(req["tool_chain"])
            
        result = mgr = _get_category_mgr()
        result = mgr.update_harness(uuid, req)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        logger.error(f"Harness update failed: {e}")
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 2: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/harness/ -v --tb=short -k "not WithOllama"`
Expected: 57 passed

- [ ] **Step 3: Commit**

```bash
git add src/app/api/analytics.py
git commit -m "fix: add input validation to PUT harness update endpoint"
```

---

### Task 3: Improve branch condition parser

**Files:**
- Modify: `src/app/harness/harness_runtime.py:423-458`

- [ ] **Step 1: Extract condition parser to a testable function**

Add above the `HarnessRuntime` class:

```python
def _parse_condition(resolved: str) -> bool:
    """
    Parse a simple condition string safely.
    Supports: ==, !=, <, >, <=, >=, null checks, truthy evaluation.
    """
    s = str(resolved).strip()

    # Null/None checks
    for op, expected in [("!=", False), ("==", True)]:
        for null_word in ("null", "None"):
            pattern = f"{op} {null_word}"
            if pattern in s or f"{op}{null_word}" in s:
                val = s.split(op)[0].strip()
                is_null = val in ("None", "null", "", "<UNRESOLVED")
                return is_null if expected else not is_null

    # Comparison operators (order matters: >= before >, <= before <)
    for op, fn in [
        (">=", lambda a, b: a >= b),
        ("<=", lambda a, b: a <= b),
        ("!=", lambda a, b: a != b),
        ("==", lambda a, b: a == b),
        (">",  lambda a, b: a > b),
        ("<",  lambda a, b: a < b),
    ]:
        if op in s:
            parts = s.split(op, 1)
            if len(parts) == 2:
                try:
                    return fn(float(parts[0].strip()), float(parts[1].strip()))
                except ValueError:
                    # String comparison fallback
                    return fn(parts[0].strip(), parts[1].strip())

    # Truthy evaluation
    return bool(s) and s.lower() not in ("false", "0", "none", "null")
```

- [ ] **Step 2: Update _handle_branch to use the new parser**

```python
    def _handle_branch(self, step: dict, current_idx: int) -> int:
        """조건 분기를 처리한다."""
        raw_cond = step.get("condition", "true")
        resolved = _resolve_vars(raw_cond, self.context)

        try:
            cond_result = _parse_condition(resolved)
        except Exception:
            cond_result = False

        target = step.get("then") if cond_result else step.get("else")
        logger.info(f"  [branch] 조건='{raw_cond}' → {cond_result} → goto '{target}'")

        if target and target in self.steps:
            return self.step_order.index(target)
        return current_idx + 1
```

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/harness/ -v --tb=short -k "not WithOllama"`
Expected: 57 passed

- [ ] **Step 4: Commit**

```bash
git add src/app/harness/harness_runtime.py
git commit -m "refactor: extract _parse_condition for safer branch evaluation"
```

---

### Task 4: Standardize imports and fix lazy import inconsistency

**Files:**
- Modify: `src/app/harness/harness_runtime.py` (move `requests` to top-level, already there)
- Modify: `src/app/harness/metrics_store.py` (check import consistency)

- [ ] **Step 1: Audit and fix import patterns in harness_runtime.py**

The file already has `import requests` at the top (line 24). Check for any other inconsistencies:

```bash
cd /Users/jungkibong/Projects/tmp/mirofish-supermemory && grep -n "import requests" src/app/harness/harness_runtime.py src/app/harness/metrics_store.py src/app/harness/orchestration/*.py
```

- [ ] **Step 2: Fix any lazy imports that should be at top-level**

If `metrics_store.py` has lazy imports of standard libraries, move them to top-level. Keep lazy imports only for circular dependency avoidance (e.g., between harness_runtime ↔ metrics_store).

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/harness/ -v --tb=short -k "not WithOllama"`
Expected: 57 passed

- [ ] **Step 4: Commit**

```bash
git add src/app/harness/
git commit -m "refactor: standardize import patterns across harness modules"
```

---

### Task 5: Add Failure Alert webhook notification

**Files:**
- Modify: `src/app/harness/orchestration/harness_orchestrator.py`

- [ ] **Step 1: Add webhook notification method**

In `harness_orchestrator.py`, add after the `_publish_to_memory` method:

```python
    def _notify_failure_webhook(self, harness_id: str, error: str, run_id: str) -> None:
        """Send failure alert to configured webhook endpoint."""
        webhook_url = self.config.get("monitoring", {}).get("webhook_on_failure")
        if not webhook_url:
            return
        try:
            import requests
            requests.post(webhook_url, json={
                "event": "harness_failure",
                "harness_id": harness_id,
                "run_id": run_id,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, timeout=5)
            logger.info(f"Failure webhook sent to {webhook_url}")
        except Exception as e:
            logger.warning(f"Failure webhook failed: {e}")
```

- [ ] **Step 2: Wire it into the failure path of run_once()**

In the `except` block of `run_once()`, after `self._publish_to_memory(...)`, add:

```python
self._notify_failure_webhook(harness_id, str(error), run_id)
```

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/harness/ -v --tb=short -k "not WithOllama"`
Expected: 57+ passed

- [ ] **Step 4: Commit**

```bash
git add src/app/harness/orchestration/harness_orchestrator.py
git commit -m "feat: add failure webhook notification to HarnessOrchestrator"
```

---

### Task 6: Add MetricsStore trend endpoint + inline chart

**Files:**
- Modify: `src/app/harness/metrics_store.py` (add `get_success_trend` method)
- Modify: `src/app/api/analytics.py` (add `/harness/metrics/trend` endpoint)
- Modify: `dashboard/harness.html` (add inline SVG trend chart)

- [ ] **Step 1: Add get_success_trend to MetricsStore**

In `src/app/harness/metrics_store.py`, add:

```python
    def get_success_trend(self, harness_id: str = None, limit: int = 20) -> list:
        """Get recent run success/failure trend for chart visualization."""
        conn = self._get_conn()
        if harness_id:
            rows = conn.execute(
                "SELECT run_id, harness_id, success, total_elapsed_ms, timestamp "
                "FROM run_summaries WHERE harness_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (harness_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT run_id, harness_id, success, total_elapsed_ms, timestamp "
                "FROM run_summaries ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 2: Add API endpoint**

In `src/app/api/analytics.py`, add before the Maturity section:

```python
@analytics_bp.route('/harness/metrics/trend', methods=['GET'])
def harness_metrics_trend():
    """Get success/failure trend data for chart visualization."""
    from ..harness.metrics_store import MetricsStore
    harness_id = request.args.get('harness_id')
    limit = int(request.args.get('limit', '20'))
    try:
        ms = MetricsStore()
        trend = ms.get_success_trend(harness_id=harness_id, limit=limit)
        return jsonify({"status": "success", "trend": trend})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 3: Add inline SVG trend sparkline to dashboard**

In `dashboard/harness.html`, add a `renderTrendChart(containerId, data)` function that draws an inline SVG sparkline (green dots for success, red for failure). Wire it to fetch `/api/analytics/harness/metrics/trend` on page load.

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/harness/ -v --tb=short -k "not WithOllama"`
Expected: 57+ passed

- [ ] **Step 5: Commit**

```bash
git add src/app/harness/metrics_store.py src/app/api/analytics.py dashboard/harness.html
git commit -m "feat: add metrics trend endpoint + inline SVG sparkline chart"
```

---

### Task 7: Add HarnessExperience filter to Knowledge Graph Explorer

**Files:**
- Modify: `dashboard/graph.html` (add Harness filter UI + domain-based coloring)

- [ ] **Step 1: Add filter UI for Harness node types**

In the graph explorer's filter panel, add checkboxes for `HarnessExperience` and `HarnessPattern` node types, and a domain color legend.

- [ ] **Step 2: Add domain-based color mapping**

```javascript
const DOMAIN_COLORS = {
  engineering: '#3b82f6',
  devops: '#06b6d4',
  marketing: '#22c55e',
  content: '#a855f7',
  sales: '#f59e0b',
  platform: '#ef4444',
  default: '#6b7280'
};
```

- [ ] **Step 3: Add deeplink from pattern node → harness detail modal**

When a `HarnessPattern` node is clicked, open `/harness.html?uuid=<pattern_uuid>` or dispatch a custom event to open the detail modal.

- [ ] **Step 4: Run all tests (no backend changes)**

Run: `.venv/bin/python3 -m pytest tests/harness/ -v --tb=short -k "not WithOllama"`
Expected: 57+ passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/graph.html
git commit -m "feat: add HarnessExperience filter + domain colors to Graph Explorer"
```

---

## Execution Order

```
Task 1 (test_helpers move)     ← 안전한 리팩토링
Task 2 (API validation)        ← 안전한 추가
Task 3 (branch parser)         ← 로직 개선
Task 4 (import 정리)           ← 코드 품질
Task 5 (failure webhook)       ← 기능 추가
Task 6 (metrics trend)         ← 차트 기능
Task 7 (graph explorer)        ← UI 개선
```

## Verification

After ALL tasks:
```bash
.venv/bin/python3 -m pytest tests/harness/ -v --tb=short -k "not WithOllama"
# Expected: 57+ passed, 0 failed
```
