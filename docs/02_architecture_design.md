# 통합 아키텍처 설계

> **문서:** 02_architecture_design.md  
> **작성일:** 2026-03-27

---

## 1. 현재 MiroFish-Offline 아키텍처

```
┌─────────────────────────────────────────┐
│              Flask API                  │
│   graph.py  simulation.py  report.py    │
└──────────────┬──────────────────────────┘
               │ app.extensions['neo4j_storage']
┌──────────────▼──────────────────────────┐
│            Service Layer                │
│  EntityReader     GraphToolsService     │
│  GraphMemoryUpdater  ReportAgent        │
└──────────────┬──────────────────────────┘
               │ storage: GraphStorage
┌──────────────▼──────────────────────────┐
│     GraphStorage (abstract)             │
│         ┌─────────────────┐             │
│         │  Neo4jStorage   │             │
│         │  ┌────────────┐ │             │
│         │  │EmbedService│ ← Ollama      │
│         │  │NERExtractor│ ← Ollama LLM  │
│         │  │SearchSvc   │ ← Hybrid      │
│         │  └────────────┘ │             │
│         └─────────────────┘             │
└──────────────┬──────────────────────────┘
           [Neo4j CE 5.15]
```

### 핵심 파일 분석 결과

| 파일 | 크기 | 역할 |
|---|---|---|
| `storage/graph_storage.py` | 3.7KB (127줄) | **추상 인터페이스** — 14개 abstract method 정의 |
| `storage/neo4j_storage.py` | 25KB | Neo4j 구현체 — NER/임베딩/하이브리드검색 포함 |
| `storage/search_service.py` | 8.1KB | 하이브리드 검색 (벡터 0.7 + BM25 0.3) |
| `storage/embedding_service.py` | 6.6KB | Ollama 임베딩 서비스 |
| `storage/ner_extractor.py` | 9.2KB | LLM 기반 NER/RE 추출 |
| `services/graph_memory_updater.py` | 17.4KB (455줄) | 시뮬레이션 활동 → 그래프 실시간 업데이트 |
| `services/simulation_runner.py` | 70KB | OASIS 시뮬레이션 실행 엔진 |
| `services/report_agent.py` | 102KB | 시뮬레이션 후 분석 보고서 생성 |

---

## 2. 통합 후 목표 아키텍처

```
┌──────────────────────────────────────────────────────┐
│                    Flask API                         │
│       graph.py  simulation.py  report.py             │
└──────────────────┬───────────────────────────────────┘
                   │ app.extensions['memory_storage']
┌──────────────────▼───────────────────────────────────┐
│                 Service Layer                        │
│   EntityReader       GraphToolsService               │
│   GraphMemoryUpdater ReportAgent                     │
│   ┌─────────────────────────────────┐                │
│   │  ★ NEW: ASMR Observer Agent     │ ← 시뮬 로그에서 │
│   │  (3개 병렬: 개인/프로젝트/관계)     │   인지적 추출    │
│   └─────────────────────────────────┘                │
└──────────────────┬───────────────────────────────────┘
                   │ storage: GraphStorage
┌──────────────────▼───────────────────────────────────┐
│          GraphStorage (abstract)                     │
│                                                      │
│   ┌─────────────────┐   ┌─────────────────────┐      │
│   │  Neo4jStorage    │   │★ SupermemoryStorage │      │
│   │  (기존, 폴백)     │   │  (NEW 구현체)        │      │
│   └────────┬────────┘   └──────────┬──────────┘      │
│            │                       │                  │
│   ┌────────▼────────┐   ┌──────────▼──────────┐      │
│   │  Neo4j CE       │   │  Supermemory API    │      │
│   │  (로컬 그래프DB)  │   │  (메모리+프로필+검색) │      │
│   └─────────────────┘   └─────────────────────┘      │
│                                                      │
│   ┌─────────────────────────────────────────┐        │
│   │★ HybridStorage (옵션)                    │        │
│   │  Neo4j(그래프 구조) + Supermemory(메모리)  │        │
│   └─────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────┘
```

---

## 3. GraphStorage 인터페이스 ↔ Supermemory API 매핑

### 3.1 GraphStorage 추상 메서드 (14개)

MiroFish-Offline의 `GraphStorage`가 요구하는 인터페이스와 Supermemory API의 대응 관계:

| # | GraphStorage 메서드 | 설명 | Supermemory 매핑 | 매핑 난이도 |
|---|---|---|---|---|
| 1 | `create_graph(name, desc)` | 그래프 생성 | 새 `containerTag` 생성 | ✅ 쉬움 |
| 2 | `delete_graph(graph_id)` | 그래프 삭제 | containerTag 아래 모든 메모리 삭제 | ✅ 쉬움 |
| 3 | `set_ontology(graph_id, ontology)` | 온톨로지 저장 | `client.add()` (메타데이터로 저장) | ⚠️ 중간 |
| 4 | `get_ontology(graph_id)` | 온톨로지 조회 | `client.search.documents()` | ⚠️ 중간 |
| 5 | `add_text(graph_id, text)` | 텍스트→NER→그래프 | `client.add({content, containerTag})` | ✅ 쉬움 |
| 6 | `add_text_batch(...)` | 배치 텍스트 추가 | 반복 `client.add()` | ✅ 쉬움 |
| 7 | `wait_for_processing(...)` | 처리 대기 | Supermemory는 동기 처리 → no-op | ✅ 쉬움 |
| 8 | `get_all_nodes(graph_id)` | 전체 노드 조회 | `client.search.memories()` (전체 스캔) | ⚠️ 중간 |
| 9 | `get_node(uuid)` | 단일 노드 조회 | `client.search.memories({q: uuid})` | ⚠️ 중간 |
| 10 | `get_node_edges(node_uuid)` | 노드 연결 엣지 | `client.profile()` + 관계 추출 | 🔴 복잡 |
| 11 | `get_nodes_by_label(...)` | 레이블별 노드 | `client.search.memories({q: label})` | ⚠️ 중간 |
| 12 | `get_all_edges(graph_id)` | 전체 엣지 조회 | 직접 매핑 불가 → **HybridStorage 필요** | 🔴 복잡 |
| 13 | `search(graph_id, query)` | 하이브리드 검색 | `client.search.memories({searchMode:"hybrid"})` | ✅ 쉬움 |
| 14 | `get_graph_info/data(...)` | 그래프 메타/데이터 | `client.profile()` + 집계 | ⚠️ 중간 |

### 3.2 매핑 전략 판단

위 분석 결과, **순수 Supermemory만으로는 그래프 구조(노드-엣지) 관련 메서드(#10, #12)를 완벽히 대체하기 어렵습니다.** 

따라서 **3가지 구현 전략**을 제안합니다:

---

## 4. 구현 전략 비교

### Option A: HybridStorage (추천 ⭐)

```
HybridStorage
├── Neo4j      → 그래프 구조 (노드, 엣지, 온톨로지)
└── Supermemory → 에이전트 메모리/프로필, 하이브리드 검색, 자동 망각
```

- Neo4j는 **구조적 지식**(엔티티 관계, 온톨로지)을 담당
- Supermemory는 **에이전트의 경험적 기억**(행동 로그, 선호도, 시간 추론)을 담당
- 각자의 강점에 맞게 역할 분담 → **가장 현실적이고 강력한 조합**

### Option B: SupermemoryStorage (순수 교체)

```
SupermemoryStorage → Supermemory API만 사용
```

- 그래프 구조 관련 메서드를 Supermemory의 검색/프로필 API로 근사
- Neo4j 의존성 완전 제거 가능하지만 그래프 시각화 등 기능 손실
- 작업량 ↓, 그러나 기능 ↓

### Option C: ASMR-Enhanced Neo4j (기존 유지 + ASMR 추가)

```
Neo4jStorage (기존 그대로)
  + ASMR Observer/Search 에이전트를 별도 미들웨어로 추가
```

- 기존 코드 변경 최소화
- ASMR 에이전트가 Neo4j에 쌓인 데이터를 읽고 추론하는 별도 레이어
- 작업량 ↓, Supermemory 연동 불필요하지만 자동 망각/프로필 기능 미활용

### 전략 비교표

| | Option A: Hybrid | Option B: Pure SM | Option C: ASMR 미들웨어 |
|---|---|---|---|
| **그래프 구조 유지** | ✅ Neo4j | ⚠️ 근사 | ✅ Neo4j |
| **ASMR 메모리** | ✅ Supermemory | ✅ Supermemory | ⚠️ 부분 구현 |
| **자동 망각** | ✅ | ✅ | ❌ |
| **에이전트 프로필** | ✅ ~50ms | ✅ ~50ms | ❌ |
| **시간 추론** | ✅ Search Agent | ✅ Search Agent | ⚠️ 직접 구현 필요 |
| **기존 코드 변경량** | 중간 | 큼 | 작음 |
| **Neo4j 의존** | 유지 | 제거 | 유지 |
| **프로덕션 적합성** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 5. Option A (HybridStorage) 상세 설계

### 5.1 데이터 흐름

```
[시드 텍스트 업로드]
       │
       ▼
┌──────────────────────┐
│   EntityReader       │ ─── NER/RE 추출
│   (기존 로직 유지)     │
└──────────┬───────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
[Neo4j]      [Supermemory]
 노드/엣지     초기 세계관 맥락
 온톨로지      "이 시나리오에서 A와 B는 동맹이다"

       [시뮬레이션 시작]
           │
           ▼
┌──────────────────────────────────┐
│    GraphMemoryUpdater            │
│    (에이전트 활동 로그 수집)        │
└──────────┬───────────────────────┘
           │
     ┌─────┴─────────────────┐
     ▼                       ▼
[Neo4j]                 [Supermemory]
 구조적 관계 업데이트       에이전트별 메모리
 "A가 B를 팔로우함"        containerTag="agent_42"
                          profile: {static: ["보수적 성향"],
                                    dynamic: ["A에게 분노 중"]}

       [에이전트 행동 결정 시]
           │
           ▼
┌──────────────────────────────────┐
│    Supermemory Search (ASMR)     │
│    Agent 1: 직접 사실 검색         │
│    Agent 2: 사회적 맥락 추론       │
│    Agent 3: 시간 타임라인 재구성    │
└──────────┬───────────────────────┘
           │
           ▼
     에이전트가 맥락을 이해하고 행동 결정

       [보고서 생성]
           │
           ▼
┌──────────────────────────────────┐
│    ReportAgent                   │
│    Neo4j: 구조적 증거 수집          │
│    Supermemory: 에이전트 프로필 조회  │
│              (~50ms per agent)    │
└──────────────────────────────────┘
```

### 5.2 HybridStorage 클래스 설계 (초안)

```python
class HybridStorage(GraphStorage):
    """
    Neo4j(그래프 구조) + Supermemory(에이전트 메모리)를 결합한 하이브리드 스토리지.
    
    - 그래프 구조 관련 (노드, 엣지, 온톨로지) → Neo4j에 위임
    - 메모리/검색/프로필 관련 → Supermemory에 위임
    """
    
    def __init__(self, neo4j_storage: Neo4jStorage, supermemory_client):
        self.neo4j = neo4j_storage
        self.sm = supermemory_client  # Supermemory SDK
    
    # --- 그래프 구조 → Neo4j ---
    def create_graph(self, name, desc=""):
        graph_id = self.neo4j.create_graph(name, desc)
        # Supermemory에도 동일 containerTag 생성
        return graph_id
    
    def set_ontology(self, graph_id, ontology):
        self.neo4j.set_ontology(graph_id, ontology)
    
    def get_all_nodes(self, graph_id, limit=2000):
        return self.neo4j.get_all_nodes(graph_id, limit)
    
    def get_node_edges(self, node_uuid):
        return self.neo4j.get_node_edges(node_uuid)
    
    def get_all_edges(self, graph_id):
        return self.neo4j.get_all_edges(graph_id)
    
    # --- 텍스트 추가 → 양쪽 모두 ---
    def add_text(self, graph_id, text):
        # 1. Neo4j: NER/RE → 노드/엣지 생성
        episode_id = self.neo4j.add_text(graph_id, text)
        # 2. Supermemory: 에이전트 메모리에 추가
        self.sm.add(content=text, containerTag=graph_id)
        return episode_id
    
    # --- 검색 → Supermemory 우선 (ASMR) ---
    def search(self, graph_id, query, limit=10, scope="edges"):
        sm_results = self.sm.search.memories(
            q=query, containerTag=graph_id, searchMode="hybrid"
        )
        # Neo4j에서 구조적 보완 검색
        neo4j_results = self.neo4j.search(graph_id, query, limit, scope)
        return self._merge_results(sm_results, neo4j_results)
    
    # --- 에이전트 프로필 → Supermemory 전용 ---
    def get_agent_profile(self, agent_id):
        """★ 새로 추가: Supermemory 프로필 조회 (~50ms)"""
        return self.sm.profile(containerTag=f"agent_{agent_id}")
```

### 5.3 에이전트별 Supermemory 활용

```
에이전트 500명 시뮬레이션 시:

containerTag 매핑:
  agent_0   → "sim_abc123_agent_0"
  agent_1   → "sim_abc123_agent_1"
  ...
  agent_499 → "sim_abc123_agent_499"

에이전트 행동 전:
  profile = sm.profile(containerTag="sim_abc123_agent_42")
  # → static:  ["보수적 성향", "기술 산업 종사", "독신"]
  # → dynamic: ["최근 A와 논쟁함", "정책 X에 반대 표명"]
  # → 이 정보를 에이전트의 LLM 프롬프트에 주입
```

---

## 6. .env 확장 설계

```env
# ===== 기존 MiroFish-Offline 설정 =====
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen2.5:32b
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=mirofish
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_BASE_URL=http://localhost:11434

# ===== ★ NEW: Supermemory 설정 =====
STORAGE_BACKEND=hybrid           # neo4j | supermemory | hybrid
SUPERMEMORY_API_KEY=sm_your_api_key_here
SUPERMEMORY_BASE_URL=https://api.supermemory.ai/v3
# Self-hosted의 경우:
# SUPERMEMORY_BASE_URL=http://localhost:8787/v3

# ===== ★ NEW: ASMR 에이전트 설정 =====
ASMR_ENABLED=true
ASMR_OBSERVER_AGENTS=3           # Observer 에이전트 수
ASMR_SEARCH_AGENTS=3             # Search 에이전트 수
ASMR_AUTO_FORGET=true            # 자동 망각 활성화
```

---

## 7. 기술적 위험 요소 & 완화 전략

| 위험 | 영향도 | 완화 전략 |
|---|---|---|
| Supermemory API 레이턴시 (원격) | 높음 | Self-hosted Supermemory 또는 로컬 캐시 도입 |
| ASMR 에이전트 LLM 호출 비용 | 중간 | 로컬 Ollama로 ASMR 에이전트 실행 |
| 500+ 에이전트의 동시 프로필 조회 | 중간 | 배치 조회 + 라운드별 캐싱 (1라운드 = 1시간 시뮬) |
| Supermemory 오픈소스 미완성 (4월 예정) | 높음 | Phase 1에서 Neo4j 폴백 유지, Phase 2에서 SM 통합 |
| 그래프 구조 ↔ 메모리의 정합성 | 중간 | HybridStorage 내 양쪽 동기화(add_text 시 양방향 기록) |
