# 신뢰성 & 보안 설계

> **문서:** 06_reliability_security.md  
> **작성일:** 2026-03-27  
> **근거:** 설계 검토(Design Review)에서 도출된 HIGH/MEDIUM 위험 항목 보완

---

## 1. 에러 처리 & 회복력 (Resilience)

### 1.1 문제: HybridStorage 이중 쓰기 실패

`add_text()`에서 Neo4j는 성공, Supermemory는 실패하면 데이터 불일치가 발생한다.

### 1.2 해결: Circuit Breaker + Outbox 패턴

```
  add_text(graph_id, text)
       │
       ▼
  ┌─────────────────────────────────┐
  │  Neo4j (동기, Source of Truth)   │ ← 반드시 성공해야 진행
  │  episode_id = neo4j.add_text()  │
  └────────────┬────────────────────┘
               │ 성공
               ▼
  ┌─────────────────────────────────┐
  │  Outbox Queue (로컬)             │ ← 나중에 재시도 가능
  │  enqueue({text, graph_id, ...}) │
  └────────────┬────────────────────┘
               │ (비동기 워커)
               ▼
  ┌─────────────────────────────────┐
  │  Supermemory (비동기)            │
  │  + Circuit Breaker              │
  │  + Retry (3회, exponential)     │
  │  + Dead Letter Queue (최종 실패) │
  └─────────────────────────────────┘
```

### 1.3 구현 설계

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Any
from collections import deque
import threading
import time
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # 정상 — 모든 호출 통과
    OPEN = "open"          # 차단 — 즉시 실패 반환
    HALF_OPEN = "half_open"  # 시험 — 1건만 통과시켜 확인


@dataclass
class CircuitBreaker:
    """
    Supermemory API 호출 보호를 위한 Circuit Breaker.
    
    동작:
    - CLOSED: 정상 운영, 실패 시 fail_count 증가
    - fail_count >= threshold → OPEN (모든 호출 차단)
    - recovery_timeout 후 → HALF_OPEN (1건만 시험)
    - 시험 성공 → CLOSED / 시험 실패 → OPEN
    """
    failure_threshold: int = 5
    recovery_timeout: int = 30  # 초
    
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    fail_count: int = field(default=0, init=False)
    last_failure_time: datetime = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_try_reset():
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit Breaker → HALF_OPEN (testing)")
                else:
                    raise CircuitOpenError(
                        f"Circuit is OPEN. Retry after {self.recovery_timeout}s"
                    )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        with self._lock:
            self.fail_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                logger.info("Circuit Breaker → CLOSED (recovered)")
    
    def _on_failure(self):
        with self._lock:
            self.fail_count += 1
            self.last_failure_time = datetime.now()
            if self.fail_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    f"Circuit Breaker → OPEN (failures: {self.fail_count})"
                )
    
    def _should_try_reset(self) -> bool:
        if self.last_failure_time is None:
            return True
        return datetime.now() - self.last_failure_time > timedelta(
            seconds=self.recovery_timeout
        )


class CircuitOpenError(Exception):
    """Circuit Breaker가 열려있을 때 발생하는 예외"""
    pass


@dataclass
class OutboxEntry:
    """Supermemory에 전송할 미처리 항목"""
    action: str          # "add" | "delete" | "profile_update"
    graph_id: str
    text: str
    metadata: dict
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3


class OutboxWorker:
    """
    Outbox 패턴 워커: Supermemory로의 비동기 전송을 처리.
    실패 시 재시도, 최종 실패 시 Dead Letter Queue로 이동.
    """
    
    def __init__(self, supermemory_client, circuit_breaker: CircuitBreaker):
        self.sm = supermemory_client
        self.cb = circuit_breaker
        self.queue: deque[OutboxEntry] = deque()
        self.dead_letter: list[OutboxEntry] = []
        self._running = False
        self._thread = None
    
    def enqueue(self, entry: OutboxEntry):
        self.queue.append(entry)
    
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._running = False
    
    def _process_loop(self):
        while self._running:
            if not self.queue:
                time.sleep(0.5)
                continue
            
            entry = self.queue.popleft()
            try:
                self.cb.call(
                    self.sm.add,
                    content=entry.text,
                    containerTag=entry.graph_id,
                    metadata=entry.metadata
                )
                logger.debug(f"Outbox: sent to SM [{entry.action}] {entry.graph_id}")
            except CircuitOpenError:
                # Circuit 열림 → 뒤로 밀어넣기
                self.queue.appendleft(entry)
                time.sleep(self.cb.recovery_timeout)
            except Exception as e:
                entry.retry_count += 1
                if entry.retry_count < entry.max_retries:
                    backoff = 2 ** entry.retry_count
                    logger.warning(
                        f"Outbox: retry {entry.retry_count}/{entry.max_retries} "
                        f"in {backoff}s — {e}"
                    )
                    time.sleep(backoff)
                    self.queue.appendleft(entry)
                else:
                    logger.error(
                        f"Outbox: DEAD LETTER [{entry.action}] {entry.graph_id} — {e}"
                    )
                    self.dead_letter.append(entry)
    
    def get_dead_letters(self) -> list:
        return self.dead_letter.copy()
    
    def retry_dead_letters(self):
        """관리자가 Dead Letter를 수동 재시도"""
        for entry in self.dead_letter:
            entry.retry_count = 0
            self.queue.append(entry)
        self.dead_letter.clear()
```

### 1.4 HybridStorage 보완 설계

```python
class HybridStorage(GraphStorage):
    """에러 처리가 강화된 HybridStorage"""
    
    def __init__(self, neo4j_storage, supermemory_client):
        self.neo4j = neo4j_storage
        self.sm = supermemory_client
        
        # 회복력 컴포넌트
        self.cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        self.outbox = OutboxWorker(self.sm, self.cb)
        self.outbox.start()
    
    def add_text(self, graph_id, text):
        # 1. Neo4j: 동기, Source of Truth — 실패 시 즉시 예외
        episode_id = self.neo4j.add_text(graph_id, text)
        
        # 2. Supermemory: 비동기 Outbox — 실패해도 Neo4j 결과는 유효
        self.outbox.enqueue(OutboxEntry(
            action="add", graph_id=graph_id,
            text=text, metadata={"episode_id": episode_id}
        ))
        
        return episode_id
    
    def search(self, graph_id, query, limit=10, scope="edges"):
        # Supermemory 검색: Circuit Breaker 보호
        sm_results = []
        try:
            sm_results = self.cb.call(
                self.sm.search.memories,
                q=query, containerTag=graph_id, searchMode="hybrid"
            )
        except (CircuitOpenError, Exception) as e:
            logger.warning(f"SM search failed, Neo4j fallback: {e}")
        
        # Neo4j 검색: 항상 실행 (폴백 보장)
        neo4j_results = self.neo4j.search(graph_id, query, limit, scope)
        
        return self._merge_results(sm_results, neo4j_results)
```

---

## 2. 데이터 일관성

### 2.1 Source of Truth 지정

```
┌──────────────────────────────────────────────┐
│                                              │
│   Neo4j = Source of Truth (SoT)              │
│   ────────────────────────────               │
│   - 모든 쓰기가 Neo4j에 먼저 반영             │
│   - Neo4j 실패 = 전체 실패 (예외 전파)        │
│   - 읽기 시 Neo4j 데이터가 최종 권위           │
│                                              │
│   Supermemory = 보조 저장소 (Auxiliary)       │
│   ────────────────────────────               │
│   - Outbox를 통한 비동기 동기화               │
│   - 실패 시 자동 재시도, 최종 실패 → DLQ       │
│   - 검색 시 보강 데이터로만 사용               │
│   - SM 없이도 시뮬레이션은 정상 동작            │
│                                              │
└──────────────────────────────────────────────┘
```

### 2.2 정합성 검증 배치 (Reconciliation)

```python
class ReconciliationService:
    """주기적으로 Neo4j ↔ Supermemory 데이터 정합성 검증"""
    
    def verify(self, graph_id: str) -> dict:
        neo4j_count = len(self.neo4j.get_all_nodes(graph_id))
        sm_count = self._count_sm_memories(graph_id)
        
        return {
            "graph_id": graph_id,
            "neo4j_nodes": neo4j_count,
            "sm_memories": sm_count,
            "drift_detected": abs(neo4j_count - sm_count) > neo4j_count * 0.1,
            "dead_letters": len(self.outbox.get_dead_letters()),
            "circuit_state": self.cb.state.value
        }
    
    def repair(self, graph_id: str):
        """Neo4j 기준으로 Supermemory 누락분 재전송"""
        # 1. Neo4j에서 모든 텍스트 에피소드 조회
        # 2. SM에서 해당 containerTag 메모리 목록 조회
        # 3. 차이분만 SM에 재전송
        pass
```

---

## 3. 보안

### 3.1 시크릿 관리

```
❌ 현재 (API body에 credential 노출)
POST /api/ingest
{
    "type": "database",
    "uri": "postgresql://user:PASSWORD@host/db"    ← 위험!
}

✅ 보완 (사전 등록된 connection 이름으로 참조)
POST /api/ingest
{
    "type": "database",
    "connection_name": "hr_database",              ← 안전
    "query": "SELECT * FROM employees"
}
```

```python
# .env 또는 별도 secrets 파일
DATA_CONNECTIONS='{
    "hr_database": {
        "type": "postgresql",
        "uri": "postgresql://user:***@host/db"
    },
    "external_neo4j": {
        "type": "neo4j",
        "uri": "bolt://external:7687",
        "user": "neo4j",
        "password": "***"
    }
}'
```

### 3.2 Webhook 인증

```python
import hashlib
import hmac

class WebhookAdapter:
    def __init__(self, secret: str = None):
        self.secret = secret or os.environ.get("WEBHOOK_SECRET")
    
    def register_endpoint(self, app, path="/api/webhook/ingest"):
        @app.route(path, methods=['POST'])
        def webhook_ingest():
            # HMAC 서명 검증
            if self.secret:
                signature = request.headers.get('X-Webhook-Signature')
                expected = hmac.new(
                    self.secret.encode(),
                    request.data,
                    hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(signature or "", expected):
                    return jsonify({"error": "Invalid signature"}), 401
            
            payload = request.get_json()
            self._webhook_queue.put(payload)
            return jsonify({"status": "accepted"}), 202
```

### 3.3 SQL Injection 방지

```python
# ❌ 현재 설계 (취약)
if not query.strip().upper().startswith('SELECT'):
    query = f"SELECT * FROM {query} LIMIT 1000"

# ✅ 보완 (파라미터 바인딩 + Table Allowlist)
class PostgresAdapter:
    ALLOWED_TABLES: set = set()  # .env에서 로드
    
    def ingest(self, source_ref, **kwargs):
        table = kwargs.get('table')
        if table and table not in self.ALLOWED_TABLES:
            raise ValueError(f"Table '{table}' is not in the allowed list")
        
        query = kwargs.get('query')
        if query:
            # SELECT만 허용, CREATE/DROP/DELETE/UPDATE 차단
            forbidden = {'CREATE', 'DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER'}
            tokens = query.strip().upper().split()
            if tokens[0] in forbidden:
                raise ValueError(f"Forbidden SQL operation: {tokens[0]}")
```

---

## 4. 테스트 전략

### 4.1 테스트 피라미드

```
        ┌───────────┐
        │   E2E     │  2~3 시나리오  (시드 → 시뮬 → 리포트)
        │  (Slow)   │
        ├───────────┤
        │Integration│  10+ 테스트   (실제 Neo4j + Mock SM)
        │  (Medium) │
        ├───────────┤
        │   Unit    │  50+ 테스트   (어댑터, 변환, 파서, CB)
        │  (Fast)   │
        └───────────┘
```

### 4.2 Mock 전략

```python
# conftest.py
import pytest

@pytest.fixture
def mock_supermemory():
    """Supermemory API Mock"""
    class MockSM:
        def __init__(self):
            self._memories = {}
        
        def add(self, content, containerTag, **kwargs):
            if containerTag not in self._memories:
                self._memories[containerTag] = []
            self._memories[containerTag].append(content)
            return {"id": f"mem_{len(self._memories[containerTag])}"}
        
        def profile(self, containerTag):
            return {
                "static": ["test trait"],
                "dynamic": ["recent event"]
            }
        
        class search:
            @staticmethod
            def memories(q, containerTag, searchMode="hybrid"):
                return [{"content": "mock result", "score": 0.9}]
    
    return MockSM()

@pytest.fixture
def hybrid_storage(neo4j_test_db, mock_supermemory):
    return HybridStorage(neo4j_test_db, mock_supermemory)
```

### 4.3 핵심 테스트 목록

| 카테고리 | 테스트 | 우선순위 |
|---|---|---|
| **어댑터** | CsvAdapter: 500행 CSV → 자연어 변환 정확성 | P0 |
| **어댑터** | JsonAdapter: 중첩 3레벨 JSON 재귀 변환 | P0 |
| **어댑터** | Neo4jImportAdapter: 외부 그래프 → entities/relations 매핑 | P0 |
| **에러** | Circuit Breaker: 5회 연속 실패 → OPEN 전환 | P0 |
| **에러** | Outbox: SM 실패 → 재시도 3회 → DLQ 이동 | P0 |
| **에러** | HybridStorage: SM 장애 시 Neo4j fallback 동작 | P0 |
| **보안** | Webhook: HMAC 서명 검증 실패 → 401 반환 | P1 |
| **보안** | PostgresAdapter: DROP TABLE 차단 | P1 |
| **성능** | 500 에이전트 프로필 배치 조회 < 10초 | P1 |
| **통합** | CSV 업로드 → NER → Neo4j 노드 생성 E2E | P1 |

---

## 5. 성능 목표 & 벤치마크

### 5.1 SLA 정의

| 시나리오 | 메트릭 | 목표 | 측정 방법 |
|---|---|---|---|
| 에이전트 프로필 조회 (1건) | p99 레이턴시 | < 100ms | `@timed` 데코레이터 |
| 에이전트 프로필 배치 (500건) | 총 시간 | < 10초 | asyncio.gather |
| SM 하이브리드 검색 | p95 레이턴시 | < 300ms | 벤치마크 스크립트 |
| CSV 1,000행 → 텍스트 변환 | 처리 시간 | < 5초 | pytest-benchmark |
| 1라운드 시뮬 (50에이전트) | 총 시간 | < 60초 | 타이머 |
| 동시 스트림 소스 5개 | CPU 사용 | < 30% | 모니터링 |

### 5.2 최적화 전략

```python
# 에이전트 프로필 배치 조회 최적화
import asyncio

class HybridStorage:
    async def get_agent_profiles_batch(self, agent_ids: list) -> dict:
        """500건을 병렬 조회 → ~2초 (직렬 시 ~25초)"""
        tasks = [
            self._async_profile(f"agent_{aid}")
            for aid in agent_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        profiles = {}
        for aid, result in zip(agent_ids, results):
            if isinstance(result, Exception):
                profiles[aid] = {"static": [], "dynamic": []}  # 폴백
            else:
                profiles[aid] = result
        return profiles
    
    # 라운드 내 캐싱
    _profile_cache: dict = {}
    _cache_round: int = -1
    
    def get_agent_profile_cached(self, agent_id, current_round):
        if current_round != self._cache_round:
            self._profile_cache.clear()
            self._cache_round = current_round
        
        if agent_id not in self._profile_cache:
            self._profile_cache[agent_id] = self.get_agent_profile(agent_id)
        return self._profile_cache[agent_id]
```

---

## 6. 관측 가능성 (Observability)

### 6.1 구조화 로깅

```python
import structlog

logger = structlog.get_logger()

class HybridStorage:
    def add_text(self, graph_id, text):
        log = logger.bind(graph_id=graph_id, text_len=len(text))
        
        start = time.time()
        episode_id = self.neo4j.add_text(graph_id, text)
        log.info("neo4j_write", duration_ms=(time.time()-start)*1000)
        
        self.outbox.enqueue(...)
        log.info("outbox_enqueue", episode_id=episode_id)
        
        return episode_id
```

### 6.2 Health Check 확장

```python
@app.route('/health')
def health():
    return {
        "status": "ok",
        "components": {
            "neo4j": neo4j_storage.health_check(),
            "supermemory": {
                "state": hybrid.cb.state.value,
                "fail_count": hybrid.cb.fail_count,
                "dead_letters": len(hybrid.outbox.dead_letter)
            },
            "streams": {
                "active": len(ingestion.active_streams()),
                "threads": len(ingestion._stream_threads)
            }
        }
    }
```

---

## 7. .env 보안 설정 추가

```env
# ===== ★ NEW: 신뢰성 =====
SM_CIRCUIT_BREAKER_THRESHOLD=5        # 연속 실패 N회 → Circuit OPEN
SM_CIRCUIT_BREAKER_TIMEOUT=30         # OPEN → HALF_OPEN 전환 시간(초)
SM_OUTBOX_MAX_RETRIES=3               # 최대 재시도 횟수
SM_OUTBOX_BACKOFF_BASE=2              # 재시도 대기 기본 시간(초)

# ===== ★ NEW: 보안 =====
WEBHOOK_SECRET=                       # Webhook HMAC 시크릿
DATA_CONNECTIONS_FILE=./connections.json  # 외부 DB 연결 설정 파일
POSTGRES_ALLOWED_TABLES=              # 쉼표 구분 허용 테이블 목록

# ===== ★ NEW: 성능 =====
SM_PROFILE_CACHE_TTL=300              # 프로필 캐시 TTL(초)
SM_BATCH_CONCURRENCY=20               # 배치 프로필 조회 동시 요청 수
INGESTION_MAX_TEXT_SIZE=1048576        # 텍스트 최대 크기(1MB)
```
