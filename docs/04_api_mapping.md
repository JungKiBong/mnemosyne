# API 매핑: GraphStorage ↔ Supermemory

> **문서:** 04_api_mapping.md  
> **작성일:** 2026-03-27

---

## 1. GraphStorage 인터페이스 전체 메서드

`references/MiroFish-Offline/backend/app/storage/graph_storage.py` (127줄, 14개 추상 메서드)

---

## 2. 메서드별 상세 매핑

### 2.1 Graph Lifecycle

#### `create_graph(name, description) → str`

| 구현 | 코드 |
|---|---|
| **Neo4j** | 그래프 전용 네임스페이스 레이블 생성 |
| **Supermemory** | `containerTag` 생성 (graph_id와 동일) |
| **Hybrid** | Neo4j에 구조 생성 + Supermemory에 containerTag 생성 |

```python
# HybridStorage 구현
def create_graph(self, name, desc=""):
    graph_id = self.neo4j.create_graph(name, desc)
    # Supermemory: containerTag로 시드 컨텍스트 저장
    self.sm.add(
        content=f"Simulation graph created: {name}. {desc}",
        containerTag=graph_id
    )
    return graph_id
```

#### `delete_graph(graph_id) → None`

```python
def delete_graph(self, graph_id):
    self.neo4j.delete_graph(graph_id)
    # Supermemory: 해당 containerTag의 모든 메모리 삭제
    # (API에 bulk delete가 있는지 확인 필요)
```

---

### 2.2 Ontology Management

#### `set_ontology(graph_id, ontology) → None`

```python
def set_ontology(self, graph_id, ontology):
    # 온톨로지는 구조적 스키마 → Neo4j에만 저장
    self.neo4j.set_ontology(graph_id, ontology)
    
    # Supermemory에는 요약본 저장 (에이전트가 세계관 이해하도록)
    ontology_summary = self._summarize_ontology(ontology)
    self.sm.add(
        content=f"World ontology: {ontology_summary}",
        containerTag=graph_id
    )
```

#### `get_ontology(graph_id) → Dict`

```python
def get_ontology(self, graph_id):
    return self.neo4j.get_ontology(graph_id)
```

---

### 2.3 Data Ingestion

#### `add_text(graph_id, text) → str`

**가장 중요한 메서드** — 모든 데이터가 이 메서드를 통해 들어옴

```python
def add_text(self, graph_id, text):
    # 1. Neo4j: NER → 노드/엣지 생성 (기존 로직)
    episode_id = self.neo4j.add_text(graph_id, text)
    
    # 2. Supermemory: 에이전트 메모리에 추가
    #    - 에이전트별 containerTag가 있으면 해당 태그로
    #    - 전체 시뮬레이션 컨텍스트면 graph_id로
    agent_tag = self._extract_agent_tag(text)  # "Agent_42: ..." → "agent_42"
    tag = agent_tag if agent_tag else graph_id
    
    self.sm.add(content=text, containerTag=tag)
    
    return episode_id
```

#### `add_text_batch(graph_id, chunks, batch_size, progress_callback) → List[str]`

```python
def add_text_batch(self, graph_id, chunks, batch_size=3, progress_callback=None):
    episode_ids = self.neo4j.add_text_batch(graph_id, chunks, batch_size, progress_callback)
    
    # Supermemory: 배치로 추가
    for chunk in chunks:
        agent_tag = self._extract_agent_tag(chunk)
        tag = agent_tag if agent_tag else graph_id
        self.sm.add(content=chunk, containerTag=tag)
    
    return episode_ids
```

#### `wait_for_processing(episode_ids, ...) → None`

```python
def wait_for_processing(self, episode_ids, progress_callback=None, timeout=600):
    # Neo4j: 동기 처리이므로 no-op
    # Supermemory: 역시 동기 처리
    pass
```

---

### 2.4 Node Operations

#### `get_all_nodes(graph_id, limit) → List[Dict]`

```python
def get_all_nodes(self, graph_id, limit=2000):
    # 구조적 노드 데이터 → Neo4j에서만 가져옴
    return self.neo4j.get_all_nodes(graph_id, limit)
```

#### `get_node(uuid) → Optional[Dict]`

```python
def get_node(self, uuid):
    node = self.neo4j.get_node(uuid)
    if node:
        # Supermemory에서 해당 노드(에이전트)의 프로필 보강
        agent_tag = node.get("name", "").replace(" ", "_").lower()
        try:
            profile = self.sm.profile(containerTag=agent_tag)
            node["sm_profile"] = {
                "static": profile.static,
                "dynamic": profile.dynamic
            }
        except Exception:
            pass
    return node
```

#### `get_node_edges(node_uuid) → List[Dict]`

```python
def get_node_edges(self, node_uuid):
    # 구조적 관계 → Neo4j
    return self.neo4j.get_node_edges(node_uuid)
```

#### `get_nodes_by_label(graph_id, label) → List[Dict]`

```python
def get_nodes_by_label(self, graph_id, label):
    return self.neo4j.get_nodes_by_label(graph_id, label)
```

---

### 2.5 Edge Operations

#### `get_all_edges(graph_id) → List[Dict]`

```python
def get_all_edges(self, graph_id):
    return self.neo4j.get_all_edges(graph_id)
```

---

### 2.6 Search (★ 핵심 통합 포인트)

#### `search(graph_id, query, limit, scope)`

```python
def search(self, graph_id, query, limit=10, scope="edges"):
    # 1. Supermemory 하이브리드 검색 (메모리 + RAG)
    sm_results = self.sm.search.memories(
        q=query,
        containerTag=graph_id,
        searchMode="hybrid"
    )
    
    # 2. Neo4j 구조적 검색 (노드/엣지 기반)
    neo4j_results = self.neo4j.search(graph_id, query, limit, scope)
    
    # 3. 결과 병합 & 중복 제거
    return self._merge_search_results(
        sm_results=sm_results,
        neo4j_results=neo4j_results,
        limit=limit,
        scope=scope
    )

def _merge_search_results(self, sm_results, neo4j_results, limit, scope):
    """
    Supermemory 결과(의미적 관련성 높음)와 
    Neo4j 결과(구조적 관련성 높음)를 병합.
    
    전략: Supermemory 결과를 우선하되, Neo4j 전용 데이터(엣지)를 보완
    """
    merged = {
        "edges": neo4j_results.get("edges", []),  # 엣지: Neo4j만 가능
        "nodes": [],
        "memories": sm_results,  # 새 필드: Supermemory 메모리
    }
    
    if scope in ("nodes", "both"):
        merged["nodes"] = neo4j_results.get("nodes", [])
    
    return merged
```

---

### 2.7 Graph Info

#### `get_graph_info(graph_id) → Dict`

```python
def get_graph_info(self, graph_id):
    info = self.neo4j.get_graph_info(graph_id)
    # Supermemory 메모리 통계 추가
    try:
        sm_stats = self.sm.search.memories(
            q="*", containerTag=graph_id, searchMode="memories"
        )
        info["supermemory_memory_count"] = len(sm_stats)
    except Exception:
        info["supermemory_memory_count"] = "N/A"
    return info
```

#### `get_graph_data(graph_id) → Dict`

```python
def get_graph_data(self, graph_id):
    return self.neo4j.get_graph_data(graph_id)
```

---

## 3. 신규 API (Supermemory 전용)

HybridStorage에 추가되는 Supermemory 전용 메서드:

| 메서드 | 설명 | Supermemory API |
|---|---|---|
| `get_agent_profile(agent_id)` | 에이전트 프로필 조회 (~50ms) | `client.profile()` |
| `get_agent_memories(agent_id, query)` | 에이전트 메모리 검색 | `client.search.memories()` |
| `forget_agent_memory(agent_id, memory_id)` | 특정 메모리 삭제 | TBD |
| `get_all_agent_profiles(graph_id)` | 전체 에이전트 프로필 배치 조회 | 반복 `client.profile()` |

---

## 4. 기존 서비스에 미치는 영향

| 서비스 파일 | 변경 필요 여부 | 상세 |
|---|---|---|
| `services/entity_reader.py` (11.7KB) | ⚠️ 최소 변경 | `storage` 파라미터 타입이 이미 `GraphStorage` → 변경 불필요 |
| `services/graph_builder.py` (8.3KB) | ❌ 변경 없음 | `storage.add_text()` 호출 → HybridStorage가 처리 |
| `services/graph_memory_updater.py` (17.4KB) | ⚠️ 수정 | Observer Agent 연동 추가 |
| `services/graph_tools.py` (56.4KB) | ❌ 변경 없음 | `storage.search()` 호출 → HybridStorage가 처리 |
| `services/report_agent.py` (102KB) | ⚠️ 확장 | 프로필 데이터 활용 로직 추가 |
| `services/simulation_runner.py` (70KB) | ⚠️ 확장 | ASMR Search Agent 연동 |
| `services/oasis_profile_generator.py` (47KB) | ❌ 변경 없음 | 초기 프로필 생성은 그대로 유지 |
| `api/graph.py` (19.5KB) | ❌ 변경 없음 | 이미 `GraphStorage` 인터페이스 사용 |
| `api/simulation.py` (97.8KB) | ❌ 변경 없음 | 이미 `GraphStorage` 인터페이스 사용 |
| `api/report.py` (18.7KB) | ❌ 변경 없음 | 이미 `GraphStorage` 인터페이스 사용 |

### 핵심: 기존 코드 수정 최소화

> 14개 서비스/API 파일 중 **3개만 수정** (graph_memory_updater, report_agent, simulation_runner)  
> 나머지 11개는 `GraphStorage` 추상화 덕분에 **코드 변경 없이** HybridStorage로 자동 전환됨
