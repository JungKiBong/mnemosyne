# 데이터 소스 확장 & 스트림 연계 설계

> **문서:** 05_data_sources_design.md  
> **작성일:** 2026-03-27

---

## 1. 현황 분석

### 현재 MiroFish-Offline 데이터 파이프라인

```
파일 업로드 (PDF/MD/TXT만)
       │
       ▼
  FileParser.extract_text() → str
       │
       ▼
  split_text_into_chunks() → List[str]
       │
       ▼
  storage.add_text_batch() → NER → Neo4j
```

**한계:**
- 파일 3종(PDF, MD, TXT)만 지원
- 구조화 데이터(CSV, JSON, DB) 미지원
- 실시간 스트림 데이터 미지원
- 외부 Neo4j/그래프 DB 연계 불가
- URL/웹 크롤링 미지원

---

## 2. 목표 아키텍처: Universal Data Ingestion

```
┌─────────────────────────────────────────────────────────────────┐
│                    Data Source Layer                             │
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐    │
│  │  Files   │ │Structured│ │  Stream  │ │  Graph / DB      │    │
│  │          │ │  Data    │ │  Data    │ │  Connectors      │    │
│  │ PDF      │ │ CSV      │ │ Kafka   │ │ Neo4j (외부)      │    │
│  │ MD/TXT   │ │ JSON/L   │ │ Redis   │ │ PostgreSQL       │    │
│  │ DOCX     │ │ Parquet  │ │ WebSocket│ │ MongoDB          │    │
│  │ XLSX     │ │ YAML     │ │ SSE      │ │ REST API         │    │
│  │ HTML     │ │ XML      │ │ Webhook  │ │ GraphQL          │    │
│  │ PPTX     │ │ SQLite   │ │ MQTT     │ │ Wikidata/DBpedia │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘    │
│       │            │            │                 │              │
└───────┼────────────┼────────────┼─────────────────┼──────────────┘
        │            │            │                 │
        ▼            ▼            ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              DataIngestionService (NEW)                         │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  SourceAdapter (abstract)                               │     │
│  │                                                        │     │
│  │  adapt(raw_input) → IngestionResult                    │     │
│  │    ├── text: str             (추출된 텍스트)              │     │
│  │    ├── metadata: Dict        (출처, 타임스탬프 등)        │     │
│  │    ├── entities: List[Dict]  (사전 추출된 엔티티, 옵션)   │     │
│  │    └── relations: List[Dict] (사전 추출된 관계, 옵션)     │     │
│  └────────────────────────────────────────────────────────┘     │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────┐  ┌────────────────────┐                    │
│  │ TextPipeline    │  │ StructuredPipeline │                    │
│  │ (기존 흐름)      │  │ (구조→텍스트 변환)   │                    │
│  │ chunk → NER     │  │ schema-aware NER   │                    │
│  └────────┬────────┘  └────────┬───────────┘                    │
│           │                    │                                │
│           ▼                    ▼                                │
│  ┌─────────────────────────────────────────────┐                │
│  │         GraphStorage (HybridStorage)         │                │
│  │         Neo4j + Supermemory                  │                │
│  └─────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. SourceAdapter 추상 인터페이스

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Iterator
from enum import Enum


class SourceType(Enum):
    FILE = "file"
    STRUCTURED = "structured"
    STREAM = "stream"
    GRAPH = "graph"
    API = "api"


@dataclass
class IngestionResult:
    """어댑터가 반환하는 정규화된 데이터"""
    text: str                                    # 추출된 텍스트 (NER 입력)
    metadata: Dict[str, Any] = field(default_factory=dict)  # 출처, 시각 등
    entities: List[Dict[str, Any]] = field(default_factory=list)  # 사전 추출 엔티티 (옵션)
    relations: List[Dict[str, Any]] = field(default_factory=list) # 사전 추출 관계 (옵션)
    source_type: SourceType = SourceType.FILE
    raw_records: List[Dict] = field(default_factory=list)  # 원본 레코드 (구조화 데이터용)


class SourceAdapter(ABC):
    """모든 데이터 소스의 공통 인터페이스"""

    @abstractmethod
    def can_handle(self, source_ref: str) -> bool:
        """이 어댑터가 해당 소스를 처리할 수 있는지 판단"""

    @abstractmethod
    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        """소스에서 데이터를 읽어 정규화된 결과 반환"""

    @abstractmethod
    def ingest_stream(self, source_ref: str, **kwargs) -> Iterator[IngestionResult]:
        """스트림 소스: 데이터를 연속적으로 반환 (배치/실시간)"""
        raise NotImplementedError("This adapter does not support streaming")


class StreamSourceAdapter(SourceAdapter):
    """스트림 데이터 소스용 특화 인터페이스"""

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> None:
        """스트림 소스에 연결"""

    @abstractmethod
    def disconnect(self) -> None:
        """연결 해제"""

    @abstractmethod
    def is_connected(self) -> bool:
        """연결 상태 확인"""
```

---

## 4. 어댑터 구현 설계

### 4.1 파일 어댑터 (확장)

| 포맷 | 어댑터 클래스 | 라이브러리 | 우선순위 |
|---|---|---|---|
| PDF | `PdfAdapter` | PyMuPDF (fitz) | ✅ 기존 |
| MD/TXT | `TextAdapter` | 내장 + charset_normalizer | ✅ 기존 |
| DOCX | `DocxAdapter` | python-docx | 🔵 Phase 1 |
| XLSX/XLS | `ExcelAdapter` | openpyxl / pandas | 🔵 Phase 1 |
| PPTX | `PptxAdapter` | python-pptx | 🟡 Phase 2 |
| HTML | `HtmlAdapter` | BeautifulSoup4 | 🟡 Phase 2 |

```python
class DocxAdapter(SourceAdapter):
    def can_handle(self, source_ref):
        return source_ref.lower().endswith(('.docx', '.doc'))

    def ingest(self, source_ref, **kwargs):
        from docx import Document
        doc = Document(source_ref)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        tables_text = []
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                tables_text.append(" | ".join(cells))
        
        full_text = "\n".join(paragraphs)
        if tables_text:
            full_text += "\n\n=== Tables ===\n" + "\n".join(tables_text)
        
        return IngestionResult(
            text=full_text,
            metadata={"source": source_ref, "format": "docx"},
            source_type=SourceType.FILE
        )
```

### 4.2 구조화 데이터 어댑터

| 포맷 | 어댑터 클래스 | 텍스트 변환 전략 | 우선순위 |
|---|---|---|---|
| CSV | `CsvAdapter` | 행 → 자연어 문장 변환 | 🔵 Phase 1 |
| JSON/JSONL | `JsonAdapter` | 키-값 → 서술형 변환 | 🔵 Phase 1 |
| Parquet | `ParquetAdapter` | pandas → CSV 흐름과 동일 | 🟡 Phase 2 |
| YAML | `YamlAdapter` | 계층 구조 → 서술형 변환 | 🟡 Phase 2 |
| XML | `XmlAdapter` | 태그 → 서술형 변환 | 🟡 Phase 2 |
| SQLite | `SqliteAdapter` | 쿼리 결과 → 자연어 변환 | 🟡 Phase 2 |

**핵심 원칙:** 구조화 데이터는 NER 추출기가 이해할 수 있도록 **자연어 문장으로 변환**한다.

```python
class CsvAdapter(SourceAdapter):
    """
    CSV 데이터를 자연어 텍스트로 변환.
    
    전략:
    1. 헤더를 스키마로 인식
    2. 각 행을 자연어 문장으로 변환
    3. 선택적으로 통계 요약 추가
    """
    
    def can_handle(self, source_ref):
        return source_ref.lower().endswith('.csv')

    def ingest(self, source_ref, **kwargs):
        import pandas as pd
        
        df = pd.read_csv(source_ref)
        schema_desc = f"Dataset with {len(df)} records and columns: {', '.join(df.columns)}"
        
        # 행 → 자연어 변환
        sentences = []
        row_limit = kwargs.get("row_limit", 500)  # 최대 변환 행 수
        
        for _, row in df.head(row_limit).iterrows():
            parts = [f"{col} is {val}" for col, val in row.items() if pd.notna(val)]
            sentences.append(". ".join(parts) + ".")
        
        # 통계 요약 (수치 컬럼)
        summary_parts = [schema_desc]
        for col in df.select_dtypes(include='number').columns:
            summary_parts.append(
                f"{col}: min={df[col].min()}, max={df[col].max()}, "
                f"mean={df[col].mean():.2f}, median={df[col].median():.2f}"
            )
        
        full_text = "\n".join(summary_parts) + "\n\n" + "\n".join(sentences)
        
        return IngestionResult(
            text=full_text,
            metadata={
                "source": source_ref, "format": "csv",
                "row_count": len(df), "columns": list(df.columns)
            },
            source_type=SourceType.STRUCTURED,
            raw_records=df.head(row_limit).to_dict('records')
        )


class JsonAdapter(SourceAdapter):
    """JSON/JSONL 데이터를 자연어로 변환"""
    
    def can_handle(self, source_ref):
        return source_ref.lower().endswith(('.json', '.jsonl'))

    def ingest(self, source_ref, **kwargs):
        import json
        
        with open(source_ref, 'r') as f:
            if source_ref.endswith('.jsonl'):
                records = [json.loads(line) for line in f if line.strip()]
            else:
                data = json.load(f)
                records = data if isinstance(data, list) else [data]
        
        sentences = []
        for record in records:
            sentence = self._record_to_text(record)
            sentences.append(sentence)
        
        return IngestionResult(
            text="\n".join(sentences),
            metadata={"source": source_ref, "format": "json", "record_count": len(records)},
            source_type=SourceType.STRUCTURED,
            raw_records=records
        )
    
    def _record_to_text(self, record, prefix=""):
        """재귀적으로 JSON 객체 → 자연어 변환"""
        parts = []
        for key, value in record.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                parts.append(self._record_to_text(value, full_key))
            elif isinstance(value, list):
                items = ", ".join(str(v) for v in value)
                parts.append(f"{full_key} includes {items}")
            else:
                parts.append(f"{full_key} is {value}")
        return ". ".join(parts) + "."


class ParquetAdapter(SourceAdapter):
    """Parquet 파일 → pandas DataFrame → CsvAdapter와 동일 흐름"""

    def can_handle(self, source_ref):
        return source_ref.lower().endswith('.parquet')

    def ingest(self, source_ref, **kwargs):
        import pandas as pd
        df = pd.read_parquet(source_ref)
        
        # 임시 CSV로 변환 후 CsvAdapter 로직 재사용
        csv_adapter = CsvAdapter()
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
        df.to_csv(tmp.name, index=False)
        result = csv_adapter.ingest(tmp.name, **kwargs)
        os.unlink(tmp.name)
        
        result.metadata["source"] = source_ref
        result.metadata["format"] = "parquet"
        return result
```

### 4.3 스트림 데이터 어댑터

| 소스 | 어댑터 클래스 | 프로토콜 | 우선순위 |
|---|---|---|---|
| Kafka | `KafkaStreamAdapter` | Consumer Group | 🟡 Phase 2 |
| Redis Pub/Sub | `RedisStreamAdapter` | Subscribe | 🟡 Phase 2 |
| WebSocket | `WebSocketStreamAdapter` | WS Client | 🟡 Phase 2 |
| Webhook | `WebhookAdapter` | HTTP POST 수신 | 🔵 Phase 1 |
| SSE (Server-Sent Events) | `SseStreamAdapter` | EventSource | 🟡 Phase 2 |
| MQTT | `MqttStreamAdapter` | Subscribe | 🔴 Phase 3 |
| RSS/Atom Feed | `RssFeedAdapter` | 폴링 | 🔵 Phase 1 |

```python
class WebhookAdapter(SourceAdapter):
    """
    외부 시스템(뉴스 피드, 알림 등)에서 Webhook으로 실시간 데이터를 수신.
    Flask 엔드포인트를 노출하여 POST 요청을 받음.
    """
    
    def can_handle(self, source_ref):
        return source_ref.startswith("webhook://")
    
    def ingest(self, source_ref, **kwargs):
        # Webhook은 push 모델 → register_endpoint()로 등록
        raise NotImplementedError("Use register_endpoint() for webhooks")
    
    def ingest_stream(self, source_ref, **kwargs):
        """Webhook 큐에서 데이터를 연속적으로 가져옴"""
        while True:
            payload = self._webhook_queue.get()  # blocking
            yield IngestionResult(
                text=self._payload_to_text(payload),
                metadata={
                    "source": source_ref,
                    "format": "webhook",
                    "received_at": datetime.now().isoformat()
                },
                source_type=SourceType.STREAM
            )
    
    def register_endpoint(self, app, path="/api/webhook/ingest"):
        """Flask 앱에 webhook 엔드포인트 등록"""
        @app.route(path, methods=['POST'])
        def webhook_ingest():
            payload = request.get_json()
            self._webhook_queue.put(payload)
            return jsonify({"status": "accepted"}), 202


class KafkaStreamAdapter(StreamSourceAdapter):
    """
    Apache Kafka에서 토픽을 구독하여 실시간 데이터 수신.
    시뮬레이션 중 실시간 뉴스/이벤트 주입에 적합.
    """
    
    def connect(self, config):
        from confluent_kafka import Consumer
        self.consumer = Consumer({
            'bootstrap.servers': config['bootstrap_servers'],
            'group.id': config.get('group_id', 'mirofish-ingest'),
            'auto.offset.reset': 'latest'
        })
        self.consumer.subscribe(config['topics'])
        self._connected = True
    
    def ingest_stream(self, source_ref, **kwargs):
        while self._connected:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None or msg.error():
                continue
            
            text = msg.value().decode('utf-8')
            yield IngestionResult(
                text=text,
                metadata={
                    "source": f"kafka://{msg.topic()}/{msg.partition()}",
                    "offset": msg.offset(),
                    "timestamp": msg.timestamp()[1],
                    "format": "kafka"
                },
                source_type=SourceType.STREAM
            )
```

### 4.4 Graph/DB 커넥터 어댑터

| 소스 | 어댑터 클래스 | 용도 | 우선순위 |
|---|---|---|---|
| Neo4j (외부) | `Neo4jImportAdapter` | 기존 지식 그래프 가져오기 | 🔵 Phase 1 |
| PostgreSQL | `PostgresAdapter` | RDB 테이블 → 텍스트 변환 | 🟡 Phase 2 |
| MongoDB | `MongoAdapter` | 문서 DB → 텍스트 변환 | 🟡 Phase 2 |
| REST API | `RestApiAdapter` | 외부 API 호출 → 데이터 수집 | 🔵 Phase 1 |
| GraphQL | `GraphQLAdapter` | GraphQL 엔드포인트 쿼리 | 🟡 Phase 2 |
| Wikidata | `WikidataAdapter` | 공개 지식 그래프 임포트 | 🔴 Phase 3 |

```python
class Neo4jImportAdapter(SourceAdapter):
    """
    외부 Neo4j 인스턴스의 지식 그래프를 MiroFish 시뮬레이션에 임포트.
    
    사용 시나리오:
    - 기존 조직의 Neo4j 지식 그래프를 시뮬레이션 세계관에 주입
    - 다른 MiroFish 인스턴스의 시뮬레이션 결과를 가져와 후속 시뮬레이션 수행
    - 공개 지식 그래프(Wikidata 등)의 서브그래프를 시드로 사용
    """
    
    def can_handle(self, source_ref):
        return source_ref.startswith(("bolt://", "neo4j://", "neo4j+s://"))
    
    def ingest(self, source_ref, **kwargs):
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(
            source_ref,
            auth=(kwargs.get('user', 'neo4j'), kwargs.get('password', ''))
        )
        
        query = kwargs.get('query', 'MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 1000')
        
        entities = []
        relations = []
        text_parts = []
        
        with driver.session() as session:
            results = session.run(query)
            for record in results:
                n = record['n']
                r = record['r']
                m = record['m']
                
                # 엔티티 추출
                n_name = n.get('name', str(n.id))
                m_name = m.get('name', str(m.id))
                r_type = type(r).__name__
                
                entities.append({
                    "name": n_name, "type": list(n.labels)[0] if n.labels else "Entity",
                    "properties": dict(n)
                })
                entities.append({
                    "name": m_name, "type": list(m.labels)[0] if m.labels else "Entity",
                    "properties": dict(m)
                })
                relations.append({
                    "source": n_name, "target": m_name,
                    "type": r_type, "properties": dict(r)
                })
                
                # 자연어 변환
                text_parts.append(f"{n_name} {r_type} {m_name}.")
        
        driver.close()
        
        return IngestionResult(
            text="\n".join(text_parts),
            metadata={
                "source": source_ref, "format": "neo4j",
                "entity_count": len(entities), "relation_count": len(relations)
            },
            entities=entities,
            relations=relations,
            source_type=SourceType.GRAPH
        )


class PostgresAdapter(SourceAdapter):
    """
    PostgreSQL 테이블/뷰의 데이터를 자연어로 변환하여 시뮬레이션 시드로 사용.
    """
    
    def can_handle(self, source_ref):
        return source_ref.startswith(("postgresql://", "postgres://"))
    
    def ingest(self, source_ref, **kwargs):
        import pandas as pd
        from sqlalchemy import create_engine
        
        engine = create_engine(source_ref)
        query = kwargs.get('query', kwargs.get('table', None))
        
        if not query:
            raise ValueError("Provide 'query' (SQL) or 'table' (table name)")
        
        if not query.strip().upper().startswith('SELECT'):
            query = f"SELECT * FROM {query} LIMIT 1000"
        
        df = pd.read_sql(query, engine)
        
        # DataFrame → 자연어 변환 (CsvAdapter 로직 재사용)
        sentences = []
        for _, row in df.iterrows():
            parts = [f"{col} is {val}" for col, val in row.items() if pd.notna(val)]
            sentences.append(". ".join(parts) + ".")
        
        schema_desc = f"Database query returned {len(df)} records with columns: {', '.join(df.columns)}"
        full_text = schema_desc + "\n\n" + "\n".join(sentences)
        
        return IngestionResult(
            text=full_text,
            metadata={
                "source": source_ref, "format": "postgresql",
                "row_count": len(df), "columns": list(df.columns)
            },
            source_type=SourceType.STRUCTURED,
            raw_records=df.to_dict('records')
        )


class RestApiAdapter(SourceAdapter):
    """
    외부 REST API를 호출하여 데이터를 수집.
    뉴스 API, 소셜 미디어 API, 금융 데이터 API 등.
    """
    
    def can_handle(self, source_ref):
        return source_ref.startswith(("http://", "https://"))
    
    def ingest(self, source_ref, **kwargs):
        import requests
        
        method = kwargs.get('method', 'GET')
        headers = kwargs.get('headers', {})
        params = kwargs.get('params', {})
        
        response = requests.request(method, source_ref, headers=headers, params=params)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '')
        
        if 'json' in content_type:
            data = response.json()
            json_adapter = JsonAdapter()
            # 임시 파일로 저장 후 처리
            import tempfile, json, os
            tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
            json.dump(data, tmp)
            tmp.close()
            result = json_adapter.ingest(tmp.name, **kwargs)
            os.unlink(tmp.name)
            result.metadata["source"] = source_ref
            result.metadata["format"] = "rest_api"
            return result
        else:
            # 텍스트로 처리
            return IngestionResult(
                text=response.text,
                metadata={"source": source_ref, "format": "rest_api"},
                source_type=SourceType.API
            )
    
    def ingest_stream(self, source_ref, **kwargs):
        """폴링 기반 스트림: interval초마다 API 재호출"""
        import time
        interval = kwargs.get('poll_interval', 60)
        
        while True:
            yield self.ingest(source_ref, **kwargs)
            time.sleep(interval)
```

---

## 5. DataIngestionService (통합 서비스)

```python
class DataIngestionService:
    """
    모든 데이터 소스를 통합 관리하는 서비스.
    어댑터 자동 탐색 + 파이프라인 실행.
    """
    
    def __init__(self, storage: GraphStorage):
        self.storage = storage
        self.adapters: List[SourceAdapter] = []
        self._stream_threads: Dict[str, threading.Thread] = {}
        self._register_default_adapters()
    
    def _register_default_adapters(self):
        """기본 어댑터 등록"""
        self.adapters.extend([
            # 파일
            PdfAdapter(), TextAdapter(), DocxAdapter(),
            ExcelAdapter(), HtmlAdapter(),
            # 구조화
            CsvAdapter(), JsonAdapter(), ParquetAdapter(),
            # DB/그래프
            Neo4jImportAdapter(), PostgresAdapter(), RestApiAdapter(),
            # 스트림
            WebhookAdapter(),
        ])
    
    def register_adapter(self, adapter: SourceAdapter):
        """커스텀 어댑터 등록"""
        self.adapters.insert(0, adapter)  # 우선순위: 커스텀 > 기본
    
    def find_adapter(self, source_ref: str) -> SourceAdapter:
        """소스에 맞는 어댑터 자동 탐색"""
        for adapter in self.adapters:
            if adapter.can_handle(source_ref):
                return adapter
        raise ValueError(f"No adapter found for source: {source_ref}")
    
    def ingest(self, graph_id: str, source_ref: str, **kwargs) -> Dict[str, Any]:
        """
        데이터 수집 → 정규화 → 그래프 저장 (원샷)
        
        Args:
            graph_id: 대상 그래프 ID
            source_ref: 데이터 소스 참조
                - 파일 경로: "/path/to/file.csv"
                - DB URI: "postgresql://host/db"
                - Neo4j URI: "bolt://host:7687"
                - URL: "https://api.example.com/data"
        """
        adapter = self.find_adapter(source_ref)
        result = adapter.ingest(source_ref, **kwargs)
        
        # 사전 추출 엔티티/관계가 있으면 직접 그래프에 주입
        if result.entities or result.relations:
            self._inject_pre_extracted(graph_id, result)
        
        # 텍스트 파이프라인: 청크 → NER → 그래프 저장
        if result.text:
            chunks = split_text_into_chunks(result.text)
            episode_ids = self.storage.add_text_batch(graph_id, chunks)
        
        return {
            "source": source_ref,
            "source_type": result.source_type.value,
            "text_length": len(result.text),
            "entities_injected": len(result.entities),
            "relations_injected": len(result.relations),
            "metadata": result.metadata
        }
    
    def start_stream(self, graph_id: str, source_ref: str, **kwargs):
        """스트림 소스 연결 및 실시간 수집 시작"""
        adapter = self.find_adapter(source_ref)
        
        def stream_worker():
            for result in adapter.ingest_stream(source_ref, **kwargs):
                if result.text:
                    self.storage.add_text(graph_id, result.text)
                if result.entities or result.relations:
                    self._inject_pre_extracted(graph_id, result)
        
        thread = threading.Thread(target=stream_worker, daemon=True)
        thread.start()
        self._stream_threads[source_ref] = thread
    
    def stop_stream(self, source_ref: str):
        """스트림 수집 중지"""
        if source_ref in self._stream_threads:
            # 어댑터의 disconnect 호출
            adapter = self.find_adapter(source_ref)
            if isinstance(adapter, StreamSourceAdapter):
                adapter.disconnect()
```

---

## 6. Neo4j 연합 (Federation) 설계

외부 Neo4j 인스턴스와의 연계를 위한 상세 설계:

```
┌─────────────────────┐     ┌─────────────────────┐
│  External Neo4j     │     │  MiroFish Neo4j     │
│  (조직 지식 그래프)   │     │  (시뮬레이션 그래프)   │
│                     │     │                     │
│  ┌───────────────┐  │  ←──│──── Import ────→    │
│  │ Person        │  │     │  ┌───────────────┐  │
│  │ Organization  │  │     │  │ SimAgent      │  │
│  │ Event         │  │     │  │ SimRelation   │  │
│  └───────────────┘  │     │  └───────────────┘  │
│                     │     │                     │
│  ┌───────────────┐  │  ──→│──── Export ────→    │
│  │ 시뮬 결과 반영  │  │     │  ┌───────────────┐  │
│  │               │  │     │  │ Prediction    │  │
│  └───────────────┘  │     │  │ Sentiment     │  │
│                     │     │  └───────────────┘  │
└─────────────────────┘     └─────────────────────┘
```

### 6.1 Import 모드 (외부 → MiroFish)

```python
# 사용 예시
ingestion = DataIngestionService(storage)

# 외부 Neo4j에서 특정 서브그래프 임포트
ingestion.ingest(
    graph_id="sim_abc123",
    source_ref="bolt://external-neo4j:7687",
    user="neo4j",
    password="secret",
    query="""
        MATCH (p:Person)-[r:WORKS_AT]->(o:Organization)
        WHERE o.industry = 'Technology'
        RETURN p, r, o LIMIT 500
    """
)
```

### 6.2 Export 모드 (MiroFish → 외부)

```python
class Neo4jExportService:
    """시뮬레이션 결과를 외부 Neo4j로 내보내기"""
    
    def export_simulation_results(
        self, graph_id: str, target_uri: str,
        target_auth: tuple, export_labels: List[str] = None
    ):
        # 1. 로컬 Neo4j에서 시뮬레이션 결과 추출
        results = self.storage.get_graph_data(graph_id)
        
        # 2. 외부 Neo4j에 기록
        driver = GraphDatabase.driver(target_uri, auth=target_auth)
        with driver.session() as session:
            for node in results['nodes']:
                session.run(
                    "MERGE (n:SimResult {uuid: $uuid}) SET n += $props",
                    uuid=node['uuid'], props=node
                )
```

### 6.3 Sync 모드 (양방향 실시간)

```python
class Neo4jSyncService:
    """
    두 Neo4j 인스턴스 간 실시간 동기화.
    Change Data Capture (CDC) 또는 폴링 기반.
    """
    
    def start_sync(self, source_uri, target_uri, sync_config):
        """
        sync_config:
          - direction: "source_to_target" | "target_to_source" | "bidirectional"
          - labels: ["Person", "Event"]  # 동기화 대상 레이블
          - interval: 30  # 폴링 간격 (초)
          - conflict_strategy: "source_wins" | "target_wins" | "latest_wins"
        """
        pass
```

---

## 7. API 확장 설계

기존 `/api/graph/ontology/generate`에 파일 업로드만 있던 것을 범용 데이터 수집 API로 확장:

### 7.1 범용 수집 엔드포인트

```
POST /api/ingest
Content-Type: application/json

{
    "project_id": "proj_abc123",
    "sources": [
        // 파일 (기존 호환)
        {"type": "file", "path": "/uploads/report.pdf"},
        
        // 구조화 데이터
        {"type": "file", "path": "/uploads/data.csv", "options": {"row_limit": 1000}},
        {"type": "file", "path": "/uploads/config.json"},
        
        // 외부 DB
        {
            "type": "database",
            "uri": "postgresql://host/db",
            "query": "SELECT * FROM events WHERE year = 2026"
        },
        
        // 외부 Neo4j
        {
            "type": "neo4j",
            "uri": "bolt://external:7687",
            "auth": {"user": "neo4j", "password": "***"},
            "query": "MATCH (n:Person)-[r]->(m) RETURN n,r,m LIMIT 500"
        },
        
        // REST API
        {
            "type": "api",
            "url": "https://newsapi.org/v2/everything?q=AI",
            "headers": {"X-Api-Key": "***"}
        }
    ]
}
```

### 7.2 스트림 관리 엔드포인트

```
# 스트림 시작
POST /api/stream/start
{
    "project_id": "proj_abc123",
    "graph_id": "graph_xyz",
    "source": {
        "type": "kafka",
        "config": {
            "bootstrap_servers": "kafka:9092",
            "topics": ["news-feed", "social-events"],
            "group_id": "mirofish-sim-1"
        }
    }
}

# 스트림 상태 조회
GET /api/stream/status

# 스트림 중지
POST /api/stream/stop
{"source_ref": "kafka://kafka:9092"}
```

---

## 8. .env 확장

```env
# ===== 기존 설정 (유지) =====
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
NEO4J_URI=bolt://localhost:7687

# ===== ★ NEW: 데이터 소스 설정 =====
# 지원 파일 포맷 확장
ALLOWED_EXTENSIONS=pdf,md,txt,markdown,docx,xlsx,xls,csv,json,jsonl,parquet,yaml,yml,xml,html,pptx

# 구조화 데이터 변환
CSV_ROW_LIMIT=1000              # CSV → text 변환 시 최대 행 수
JSON_MAX_DEPTH=5                # JSON 중첩 최대 깊이
STRUCTURED_DATA_SUMMARIZE=true  # 통계 요약 자동 추가

# ===== ★ NEW: 외부 Neo4j 연계 =====
EXTERNAL_NEO4J_URI=              # 외부 Neo4j URI (비워두면 비활성)
EXTERNAL_NEO4J_USER=neo4j
EXTERNAL_NEO4J_PASSWORD=
NEO4J_SYNC_ENABLED=false
NEO4J_SYNC_DIRECTION=source_to_target
NEO4J_SYNC_INTERVAL=30

# ===== ★ NEW: 스트림 데이터 =====
STREAM_ENABLED=false
KAFKA_BOOTSTRAP_SERVERS=
KAFKA_TOPICS=
REDIS_URL=
WEBHOOK_ENABLED=false
WEBHOOK_PATH=/api/webhook/ingest
```

---

## 9. 구현 우선순위 로드맵

| Phase | 어댑터 | 기간 |
|---|---|---|
| **Phase 1** (필수) | DOCX, XLSX, CSV, JSON, REST API, Neo4j Import, Webhook | 2주 |
| **Phase 2** (확장) | Parquet, YAML, XML, HTML, PPTX, PostgreSQL, Kafka, WebSocket, SSE | 2주 |
| **Phase 3** (고급) | MongoDB, GraphQL, MQTT, Wikidata, Neo4j Sync (양방향) | 2주 |

### Phase 1 완료 시 지원 포맷

```
파일:    PDF, MD, TXT, DOCX, XLSX, CSV, JSON
DB:     Neo4j (외부 임포트)
API:    REST API (GET/POST)
스트림:  Webhook (push), RSS Feed (polling)
```

---

## 10. 데이터 흐름 전체도 (통합)

```
                    ┌──────── 실시간 ────────┐
                    │                       │
 [파일 업로드]  [DB/API 쿼리]  [Kafka/Webhook]  [외부 Neo4j]
      │              │              │              │
      ▼              ▼              ▼              ▼
 ┌──────────────────────────────────────────────────────┐
 │             DataIngestionService                     │
 │                                                      │
 │  SourceAdapter.ingest() → IngestionResult            │
 │    ├── text (자연어) ──────────────┐                  │
 │    ├── entities (사전 추출) ───────┤                  │
 │    └── relations (사전 추출) ──────┤                  │
 │                                   │                  │
 │  ┌────────────────────────────────▼───────────────┐  │
 │  │            Ingestion Pipeline                  │  │
 │  │                                                │  │
 │  │  text → chunk → NER/RE → 노드/엣지 생성        │  │
 │  │  pre-extracted → 직접 그래프 주입               │  │
 │  └────────────────────────────────┬───────────────┘  │
 └───────────────────────────────────┼──────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
       ┌────────────┐       ┌──────────────┐      ┌──────────────┐
       │  Neo4j     │       │ Supermemory  │      │ External     │
       │  (구조)    │       │ (메모리/ASMR) │      │ Neo4j (동기) │
       └────────────┘       └──────────────┘      └──────────────┘
```
