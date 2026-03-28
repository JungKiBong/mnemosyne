# 단계별 구현 계획

> **문서:** 03_integration_plan.md  
> **작성일:** 2026-03-27

---

## 전체 로드맵

```
Phase 0      Phase 1        Phase 1.5        Phase 2        Phase 3        Phase 4
환경 구축     HybridStorage   데이터소스확장     ASMR Observers  ASMR Search    프로덕션 & UX
(1주)        구현 (2주)      & Neo4j연합 (2주)  통합 (2주)      통합 (2주)      (2주)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
▓▓▓▓         ▓▓▓▓▓▓▓▓        ▓▓▓▓▓▓▓▓          ▓▓▓▓▓▓▓▓       ▓▓▓▓▓▓▓▓       ▓▓▓▓▓▓▓▓
```

---

## Phase 0: 환경 구축 (1주)

### 목표
MiroFish-Offline이 로컬에서 정상 작동하는 것을 확인하고, Supermemory SDK 연동 기반을 마련한다.

### 작업

- [ ] **0.1** MiroFish-Offline 로컬 환경 구성
  - Docker Compose 또는 수동으로 Neo4j + Ollama + Flask 실행
  - 테스트 시드 텍스트로 end-to-end 시뮬레이션 1회 실행 확인
  
- [ ] **0.2** Supermemory SDK 설치 및 API 키 발급
  - `pip install supermemory`
  - API 키 테스트: `client.add()`, `client.profile()`, `client.search.memories()` 동작 확인
  
- [ ] **0.3** Supermemory self-hosted 가능 여부 조사
  - 2026년 4월 초 오픈소스 예정 → 타이밍에 따라 로컬 호스팅 전환 가능

### 완료 조건
- MiroFish-Offline 시뮬레이션이 Neo4j와 함께 정상 동작
- Supermemory Python SDK로 CRUD + 검색이 동작

---

## Phase 1: HybridStorage 구현 (2주)

### 목표
`GraphStorage` 추상 인터페이스를 구현하는 `HybridStorage` 클래스를 작성하여, 기존 코드 변경 없이 Neo4j + Supermemory를 병렬 운용한다.

### 작업

- [ ] **1.1** `src/storage/supermemory_client.py` 작성
  - Supermemory Python SDK 래퍼
  - 환경변수 기반 설정 로딩
  - 연결 테스트 / 헬스체크 유틸리티

- [ ] **1.2** `src/storage/hybrid_storage.py` 작성
  - `GraphStorage` 14개 메서드 모두 구현
  - 그래프 구조 → Neo4j 위임
  - 메모리/검색/프로필 → Supermemory 위임
  - `add_text()`: 양쪽에 동시 기록
  - `search()`: Supermemory 결과 + Neo4j 결과 병합

- [ ] **1.3** Flask `__init__.py` 수정
  - `.env`의 `STORAGE_BACKEND` 값에 따라 Neo4j / Supermemory / Hybrid 중 선택
  - `app.extensions['neo4j_storage']` → `app.extensions['memory_storage']`로 이름 변경 (하위 호환 유지)

- [ ] **1.4** 통합 테스트
  - 동일 시드 텍스트로 Neo4j 단독 vs HybridStorage 결과 비교
  - 검색 정확도, 레이턴시 벤치마크

### 완료 조건
- `.env`에서 `STORAGE_BACKEND=hybrid` 설정만으로 Supermemory가 활성화
- 기존 시뮬레이션 워크플로우(Graph Build → Simulation → Report)가 정상 동작

---

## Phase 1.5: 데이터 소스 확장 & Neo4j 연합 (2주)

### 목표
파일 3종(PDF/MD/TXT)만 지원하던 입력을 범용 데이터 수집 시스템으로 확장하고, 외부 Neo4j 및 스트림 데이터 소스와 연계한다.

> 상세 설계: [05_data_sources_design.md](./05_data_sources_design.md)

### 작업

- [ ] **1.5.1** `SourceAdapter` 추상 인터페이스 & `DataIngestionService` 구현
  - `IngestionResult` 데이터 클래스 (text, metadata, entities, relations)
  - 어댑터 자동 탐색 (`can_handle()` 기반)
  - 기존 `FileParser`를 `PdfAdapter`, `TextAdapter`로 마이그레이션 (하위 호환 유지)

- [ ] **1.5.2** 파일 어댑터 확장
  - `DocxAdapter` (python-docx): 단락 + 표 추출
  - `ExcelAdapter` (openpyxl/pandas): 시트별 → 자연어 변환
  - `HtmlAdapter` (BeautifulSoup4): 태그 제거 + 구조 보존

- [ ] **1.5.3** 구조화 데이터 어댑터
  - `CsvAdapter`: 행 → 자연어 문장 변환, 통계 요약 자동 추가
  - `JsonAdapter` / `JsonlAdapter`: 재귀적 키-값 서술형 변환
  - `ParquetAdapter`: pandas → CsvAdapter 파이프라인 재사용

- [ ] **1.5.4** 외부 Neo4j 연계 (Import)
  - `Neo4jImportAdapter`: Cypher 쿼리 → 엔티티/관계 직접 추출
  - 사전 추출(pre-extracted) 엔티티/관계를 NER 우회하여 그래프에 직접 주입
  - `.env`의 `EXTERNAL_NEO4J_URI`로 설정

- [ ] **1.5.5** REST API & Webhook 어댑터
  - `RestApiAdapter`: GET/POST → JSON 응답 → JsonAdapter 파이프라인
  - `WebhookAdapter`: Flask 엔드포인트 `/api/webhook/ingest` 등록, 큐 기반 비동기 수집

- [ ] **1.5.6** 스트림 수집 프레임워크
  - `StreamSourceAdapter` 특화 인터페이스 (connect/disconnect/is_connected)
  - `DataIngestionService.start_stream()` / `stop_stream()` 관리
  - 스트림 데이터 → 시뮬레이션 실행 중 실시간 이벤트 주입 연동

- [ ] **1.5.7** API 확장
  - `POST /api/ingest` — 범용 데이터 수집 (다중 소스 동시 수집)
  - `POST /api/stream/start`, `GET /api/stream/status`, `POST /api/stream/stop`
  - `.env` 확장: `ALLOWED_EXTENSIONS`, `CSV_ROW_LIMIT`, `STREAM_ENABLED` 등

- [ ] **1.5.8** 통합 테스트
  - 각 어댑터별 단위 테스트 (최소 10개 포맷)
  - 외부 Neo4j 임포트 → 시뮬레이션 실행 end-to-end 테스트
  - 스트림 수집 시작 → 시뮬레이션 중 라이브 이벤트 주입 테스트

### 완료 조건
- `DataIngestionService.ingest(graph_id, "/path/to/file.csv")` 한 줄로 모든 포맷 수집 동작
- 외부 Neo4j에서 Cypher 쿼리로 서브그래프를 임포트하여 시뮬레이션 시드로 사용 가능
- Webhook으로 실시간 뉴스/이벤트를 수신하여 실행 중인 시뮬레이션에 주입 가능

---

## Phase 2: ASMR Observer Agent 통합 (2주)

### 목표
시뮬레이션 로그에서 에이전트별 기억을 인지적으로 추출하는 Observer Agent를 도입한다.

### 작업

- [ ] **2.1** `src/agents/observer_agent.py` 작성
  - 3개의 병렬 Observer:
    - **Observer A**: 개인 정보, 선호도, 습관 추출
    - **Observer B**: 이벤트, 행동 패턴 추출
    - **Observer C**: 관계, 사회적 맥락, 감정 추출
  - 추출 결과 → Supermemory `client.add()` 호출

- [ ] **2.2** `GraphMemoryUpdater` 확장
  - 기존 5개 배치 → Neo4j 전송 로직 유지
  - 동시에 Observer Agent에도 활동 로그 전달
  - Observer는 비동기(별도 스레드)로 인지적 추출 수행

- [ ] **2.3** 에이전트 프로필 주입
  - 시뮬레이션 각 라운드 시작 시, 에이전트별 `client.profile()` 조회
  - 결과를 에이전트의 LLM 시스템 프롬프트에 주입
  - 캐싱: 동일 라운드 내에서는 프로필 재조회 안 함

- [ ] **2.4** 자동 망각 검증
  - 시뮬레이션 30라운드(30시간 시뮬) 후 Supermemory에 저장된 메모리 품질 점검
  - 만료된 정보(예: "내일 시험")가 자동 삭제되었는지 확인
  - 모순 정보(예: 입장 변경)가 자동 해결되었는지 확인

### 완료 조건
- 에이전트가 시뮬레이션 중 자신의 과거 행동/관계를 정확히 기억
- Observer 에이전트가 시뮬레이션 로그에서 구조화 지식을 자동 추출

---

## Phase 3: ASMR Search Agent 통합 (2주)

### 목표
에이전트가 행동을 결정할 때, ASMR Search Agent가 맥락·사실·시간을 전문적으로 검색하여 제공한다.

### 작업

- [ ] **3.1** `src/agents/search_agent.py` 작성
  - 3개의 병렬 Search Agent:
    - **Search 1**: 직접적 사실 & 명시적 진술 검색
    - **Search 2**: 관련 맥락, 사회적 단서, 함의 검색
    - **Search 3**: 시간 타임라인 재구성 & 관계 맵
  - 결과 통합 Orchestrator

- [ ] **3.2** 시뮬레이션 러너 연동
  - `simulation_runner.py`의 에이전트 결정 루프에 ASMR 검색 삽입
  - 성능 최적화: 병렬 검색 → 결과 합류 → 프롬프트 주입

- [ ] **3.3** ReportAgent 강화
  - 보고서 생성 시 Supermemory 프로필 데이터 활용
  - 에이전트 포커스 그룹 인터뷰 시 시간적 맥락 제공

- [ ] **3.4** 벤치마크 & 비교
  - 동일 시나리오에서 ASMR 미적용 vs 적용 시뮬레이션 결과 비교
  - 에이전트 행동의 일관성, 현실성, 시간 인식 정확도 측정

### 완료 조건
- 에이전트가 "3라운드 전에 A와 싸웠으니, 지금 A와 대화 시 적대적 어조를 유지한다" 등의 시간 인지적 행동을 보임
- ASMR 미사용 대비 시뮬레이션 현실성이 명확히 향상

---

## Phase 4: 프로덕션 & UX (2주)

### 작업

- [ ] **4.1** Docker Compose 확장
  - Supermemory 서비스 (self-hosted) 추가
  - 또는 외부 API 연결 모드 지원

- [ ] **4.2** 프론트엔드 대시보드 확장
  - 에이전트 프로필 카드 (Supermemory 프로필 시각화)
  - 메모리 타임라인 뷰 (시간별 기억 변화 추적)
  - 자동 망각 로그 뷰

- [ ] **4.3** 설정 UI
  - 스토리지 백엔드 전환 (Neo4j / Hybrid / Supermemory)
  - ASMR 에이전트 활성화/비활성화 토글

- [ ] **4.4** 문서화 & 릴리즈
  - README, API 문서
  - 데모 시나리오 2~3개 준비

---

## Phase 5: MCP Server & 외부 AI 연동 (2주)

### 목표
Mories 메모리 시스템을 MCP (Model Context Protocol) Server로 래핑하여,
외부 AI 에이전트 (Claude, Gemini, 커스텀 에이전트 등)가 도구(Tool)로써
지식 그래프 검색·에이전트 프로필 조회·데이터 주입 등을 수행할 수 있도록 한다.

### 작업

- [ ] **5.1** MCP Server 기본 스캐폴딩
  - `mcp_server/` 디렉토리 생성
  - MCP Python SDK 기반 서버 구현 (`mcp[cli]`)
  - stdio / SSE 양방향 전송 지원

- [ ] **5.2** MCP Tool 정의 (핵심 5종)
  - `mories_search`: 지식 그래프 + SM 통합 검색
  - `mories_ingest`: 외부 데이터 소스 수집 (파일/URL/DB)
  - `mories_agent_profile`: 에이전트 프로필 조회
  - `mories_graph_query`: Cypher 쿼리 실행 (읽기 전용)
  - `mories_stream_control`: 스트림 수집 시작/중지

- [ ] **5.3** n8n 연동
  - n8n HTTP Request 노드 기반 워크플로우 템플릿 3~5개 작성
    - 자동 뉴스 수집 → 시뮬레이션 주입
    - 시뮬레이션 결과 요약 → Slack/이메일 전송
    - 주기적 에이전트 프로필 스냅샷 → Google Sheets
  - n8n MCP 노드 연동 가이드

- [ ] **5.4** 보안 & 인증
  - MCP Server API 키 인증
  - Neo4j 읽기 전용 모드 강제 (외부 접근 시)
  - Rate limiting (분당 요청 수 제한)

- [ ] **5.5** 멀티 에이전트 메모리 공유 프로토콜
  - containerTag 기반 네임스페이스 격리
  - 에이전트 간 공유 메모리 영역 (shared_context) 설계
  - 외부 AI → MCP Tool → Mories → 응답 흐름 E2E 테스트

### 완료 조건
- Claude/Gemini에서 MCP Tool로 `mories_search("Alice의 최근 행동은?")`을 호출하면 SearchResult가 반환됨
- n8n 워크플로우가 주기적으로 데이터를 수집하여 시뮬레이션에 자동 주입됨
- 외부 접근 시 읽기 전용 + API 키 인증이 강제됨

---

## 핵심 마일스톤 요약

| 마일스톤 | 예상 완료 | 핵심 산출물 |
|---|---|---|
| Phase 0 완료 | ✅ 완료 | 로컬 환경 정상 동작, SDK 연동 확인 |
| Phase 1 완료 | ✅ 완료 | HybridStorage 클래스, `.env` 기반 백엔드 전환 |
| Phase 1.5 완료 | ✅ 완료 | 11종 어댑터, 외부 Neo4j 임포트, 스트림 수집 |
| Phase 2 완료 | ✅ 완료 | Observer Agent 3개, Orchestrator, 에이전트 프로필 주입 |
| Phase 3 완료 | ✅ 완료 | Search Agent 3개, 시간 인식 검색, 프로필 캐싱 |
| Phase 4 완료 | ✅ 완료 | Docker Compose, 대시보드, README |
| Phase 5 완료 | ✅ 완료 | MCP Server 5종 Tool, n8n 워크플로우 3개, SSE/stdio 듀얼 전송 |

