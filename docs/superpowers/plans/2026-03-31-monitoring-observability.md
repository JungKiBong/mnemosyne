# Monitoring & Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement production-grade monitoring by integrating structured JSON logging, request correlation IDs, Prometheus metrics, and a new dashboard endpoint for memory salience trends.

**Architecture:** 
- `python-json-logger` will standardize logs into JSON format for easier aggregation (e.g., in ELK or Datadog). 
- Flask `before_request` hooks will generate an `X-Correlation-ID` for tracking user journeys across logs. 
- The `prometheus_client` library will expose a `/metrics` route, tracking API latency histograms and status code counters.
- A new endpoint `/api/analytics/salience_trend` will query Neo4j for daily memory access trends, returning data suited for D3.js/Chart.js frontends.

**Tech Stack:** Python, Flask, `python-json-logger`, `prometheus_client`, Neo4j.

---

### Task 1: Setup Structured Logging & Correlation IDs

**Files:**
- Modify: `requirements.txt`
- Modify: `src/app/utils/logger.py`
- Modify: `src/app/__init__.py`
- Create: `tests/e2e/test_monitoring.py`

- [ ] **Step 1: Write the failing test**

```python
# Create: tests/e2e/test_monitoring.py
def test_correlation_id_in_response(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert 'X-Correlation-ID' in response.headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/e2e/test_monitoring.py -v`
Expected: FAIL due to missing `X-Correlation-ID` header.

- [ ] **Step 3: Update requirements and logger**

```text
# Modify: requirements.txt (Append to end)
python-json-logger==2.0.7
prometheus_client==0.20.0
```

```python
# Modify: src/app/utils/logger.py
import logging
from pythonjsonlogger import jsonlogger
from flask import has_request_context, request

class CorrelationFilter(logging.Filter):
    def filter(self, record):
        if has_request_context() and hasattr(request, 'correlation_id'):
            record.correlation_id = request.correlation_id
        else:
            record.correlation_id = "N/A"
        return True

def setup_logger(name='mirofish'):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logHandler = logging.StreamHandler()
        # Use JSON formatter
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(levelname)s %(correlation_id)s %(name)s %(message)s'
        )
        logHandler.setFormatter(formatter)
        logHandler.addFilter(CorrelationFilter())
        logger.addHandler(logHandler)
    return logger

def get_logger(name):
    return logging.getLogger(name)
```

- [ ] **Step 4: Add Correlation ID middleware**

```python
# Modify: src/app/__init__.py (in create_app, replace the existing `@app.before_request`)
    import uuid

    @app.before_request
    def set_correlation_id():
        request.correlation_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))

    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Request: {request.method} {request.path}")

    @app.after_request
    def log_response(response):
        response.headers['X-Correlation-ID'] = request.correlation_id
        logger = get_logger('mirofish.request')
        logger.debug(f"Response: {response.status_code}")
        return response
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/e2e/test_monitoring.py::test_correlation_id_in_response -v`
Expected: PASS

- [ ] **Step 6: Commit**

Check `.agent/config.yml` for `auto_commit` setting. If true:
```bash
git add requirements.txt src/app/utils/logger.py src/app/__init__.py tests/e2e/test_monitoring.py
git commit -m "feat(monitoring): add structured json logging and correlation ID"
```
If false: print "Skipping commit (auto_commit: false)."

---

### Task 2: Prometheus Metrics Exporter

**Files:**
- Modify: `src/app/__init__.py`
- Modify: `tests/e2e/test_monitoring.py`

- [ ] **Step 1: Write the failing test**

```python
# Modify: tests/e2e/test_monitoring.py (Append)
def test_prometheus_metrics_endpoint(client):
    response = client.get('/metrics')
    assert response.status_code == 200
    assert 'http_requests_total' in response.data.decode('utf-8')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/e2e/test_monitoring.py::test_prometheus_metrics_endpoint -v`
Expected: FAIL with 404 (endpoint not found)

- [ ] **Step 3: Implement Prometheus metrics**

```python
# Modify: src/app/__init__.py (inside create_app, before returning `app`)
    from prometheus_client import make_wsgi_app, Counter, Histogram
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    import time

    # Metrics definitions
    request_count = Counter('http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'http_status'])
    request_latency = Histogram('http_request_duration_seconds', 'HTTP Request Duration', ['endpoint'])

    @app.before_request
    def start_timer():
        request.start_time = time.time()

    @app.after_request
    def record_metrics(response):
        if request.path != '/metrics':
            latency = time.time() - getattr(request, 'start_time', time.time())
            request_latency.labels(endpoint=request.path).observe(latency)
            request_count.labels(
                method=request.method,
                endpoint=request.path,
                http_status=response.status_code
            ).inc()
        return response

    # Mount prometheus WSGI app on /metrics
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
        '/metrics': make_wsgi_app()
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/e2e/test_monitoring.py::test_prometheus_metrics_endpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

If `auto_commit: true`:
```bash
git add src/app/__init__.py tests/e2e/test_monitoring.py
git commit -m "feat(monitoring): export prometheus metrics at /metrics"
```

---

### Task 3: Dashboard Salience Trend Endpoint

**Files:**
- Modify: `src/app/api/analytics.py`
- Modify: `tests/e2e/test_monitoring.py`

- [ ] **Step 1: Write the failing test**

```python
# Modify: tests/e2e/test_monitoring.py (Append)
def test_salience_trend_endpoint(client):
    response = client.get('/api/analytics/salience_trend')
    assert response.status_code == 200
    data = response.get_json()
    assert 'trend_data' in data
    assert isinstance(data['trend_data'], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/e2e/test_monitoring.py::test_salience_trend_endpoint -v`
Expected: FAIL with 404 (endpoint not found)

- [ ] **Step 3: Implement Salience Trend API**

```python
# Modify: src/app/api/analytics.py (Append)
from flask import current_app

@analytics_bp.route('/salience_trend', methods=['GET'])
def get_salience_trend():
    """Returns memory salience distribution and trend over time."""
    driver = current_app.extensions.get('neo4j_driver')
    if not driver:
        return jsonify({"error": "Neo4j driver not initialized"}), 500

    query = """
    MATCH (e:Entity)
    WHERE e.last_accessed IS NOT NULL
    WITH substring(toString(e.last_accessed), 0, 10) AS access_date, avg(e.salience) AS avg_salience, count(e) AS memory_count
    RETURN access_date, avg_salience, memory_count
    ORDER BY access_date DESC
    LIMIT 30
    """
    
    with driver.session() as session:
        records = session.run(query).data()
    
    return jsonify({
        "status": "success",
        "trend_data": records
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/e2e/test_monitoring.py::test_salience_trend_endpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

If `auto_commit: true`:
```bash
git add src/app/api/analytics.py tests/e2e/test_monitoring.py
git commit -m "feat(analytics): add /salience_trend API for dashboard graphs"
```
