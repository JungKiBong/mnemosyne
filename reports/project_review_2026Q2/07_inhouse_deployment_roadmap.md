# Mories 사내 에이전틱 워크플로우 적용 로드맵
> **Date**: 2026-04-06 | **Version**: v1.0  
> **목표**: 사내 멀티 에이전트 시스템의 공유 메모리 인프라로 Mories 안정화·실전 도입  
> **기존 계획과의 관계**: `06_product_transition_plan.md`의 Phase 0~1을 사내 맥락으로 재구성. Phase 2~3(SaaS/클라우드)은 전략적으로 동결.

---

## 목차

1. [전략 전환 근거](#1-전략-전환-근거)
2. [현재 자산 재평가](#2-현재-자산-재평가-코드-기반-팩트-체크)
3. [Step 1: 코어 안정화 & 보안 (Week 1-2)](#3-step-1-코어-안정화--보안-week-1-2)
4. [Step 2: 사내 인프라 밀착 통합 (Week 3-6)](#4-step-2-사내-인프라-밀착-통합-week-3-6)
5. [Step 3: 사내 보급형 패키지 & 온보딩 (Week 7-8)](#5-step-3-사내-보급형-패키지--온보딩-week-7-8)
6. [기존 글로벌 계획 대비 변경 사항](#6-기존-글로벌-계획-대비-변경-사항)
7. [사내 적용 아키텍처](#7-사내-적용-아키텍처)
8. [리스크 및 Go/No-Go](#8-리스크-및-gono-go)
9. [KPI 및 성공 기준](#9-kpi-및-성공-기준)

---

## 1. 전략 전환 근거

### 기존 계획 (글로벌 SaaS)의 문제점

| 기존 계획 요소 | 사내 도입 시 비효율인 이유 |
|--------------|------------------------|
| PyPI/npm 퍼블릭 배포 | 사내 코드를 외부에 노출할 필요 없음 |
| OAuth2 + Google/GitHub 소셜 로그인 | 사내는 Keycloak/LDAP/SSO가 표준 |
| Stripe 과금 시스템 | 사내 사용료는 부서 청구되므로 불필요 |
| 멀티테넌트 완전 격리 | 사내에서는 Team/Project 스코프로 충분 |
| 영문화 (코드 주석/UI) | 사내 개발팀은 한국어 사용 — 나중에 해도 됨 |
| GDPR/SOC2 규정 준수 | 사내 보안 정책은 별도 체계 |

### 사내 도입 최적 전략: 3-Step 집중형

```
기존 계획:  Phase 0 (4주) → Phase 1 (8주) → Phase 2 (12주) → Phase 3 (24주)
                                                                    ↑ SaaS 목표
사내 전환:  Step 1 (2주)  → Step 2 (4주)  → Step 3 (2주)
            코어 안정화      인프라 통합       사내 배포
                                               ↑ 사내 일상 운용 목표
```

**총 8주 만에 사내 에이전트를 위한 인지 메모리 인프라를 실전 투입합니다.**

---

## 2. 현재 자산 재평가 (코드 기반 팩트 체크)

> [!IMPORTANT]
> 이전 보고서(03_competitive_analysis.md)에서 "벡터 검색 미지원"이라고 평가했으나, 코드 검토 결과 **이미 완전히 구현되어 있었습니다.** 아래는 코드 기반의 정확한 현황입니다.

### ✅ 이미 구현된 핵심 기능 (즉시 사용 가능)

| 기능 | 파일 | 상태 | 비고 |
|------|------|------|------|
| **하이브리드 검색 (Vector + BM25)** | `storage/search_service.py` (312 LOC) | ✅ 완전 구현 | 0.75*vector + 0.25*keyword 가중 + salience 리랭킹 |
| **멀티 프로바이더 임베딩** | `storage/embedding_service.py` (258 LOC) | ✅ 완전 구현 | Ollama, OpenAI, vLLM, 커스텀 엔드포인트 지원 |
| **Neo4j 벡터 인덱스** | `storage/neo4j_schema.py` | ✅ 스키마 정의 완료 | entity_embedding (768d), fact_embedding (768d) cosine |
| **인출 시 자동 salience 강화** | `search_service.py:277` | ✅ 구현됨 | 비동기 fire-and-forget 부스트 |
| **임베딩 캐시 (2000항)** | `embedding_service.py:237` | ✅ 구현됨 | 스레드 안전 + LRU 방식 |
| **임베딩 health check API** | `admin.py:427` | ✅ 구현됨 | `/api/admin/settings/test/embedding` |
| **STM/LTM/PM 인지 기억** | `storage/memory_manager.py` (810 LOC) | ✅ 완전 구현 | Ebbinghaus 감쇠 + 스코프 계층 |
| **27개 MCP 도구** | `mcp_server/mories_mcp.py` | ✅ 실전 사용 중 | Claude/Cursor/n8n 연동 검증 완료 |
| **하네스 오케스트레이션** | `harness/` 전체 | ⚠️ 80% | DSL + 7종 Executor + Auto-Healing |
| **Docker Compose 3-서비스** | `docker-compose.yml` | ✅ 완전 구현 | Neo4j + API + Dashboard (Nginx) |
| **Prometheus 메트릭** | `__init__.py` | ✅ 수집 중 | QPS, Latency, Cache Hit/Miss |

### ⚠️ 사내 도입 전 반드시 해결해야 할 이슈

| 이슈 | 파일 | 심각도 | 설명 |
|------|------|--------|------|
| **`exec()` 동적 코드 실행** | `ray_executor.py:109` | 🔴 Critical | 에이전트가 생성한 코드를 검증 없이 실행 — 사내 망 탈취 가능 |
| **API Key 하드코딩 위험** | `config.py:24` | 🟡 Medium | `SECRET_KEY` 기본값이 고정 문자열 |
| **CORS `*` 전체 허용** | `config.py:28` | 🟡 Medium | 사내 도메인 화이트리스트 필요 |
| **하드코딩 IP** | MCP 서버 | 🟡 Medium | `192.168.x.x` 로컬 IP 잔존 |
| **STM in-memory만** | `memory_manager.py` | 🟡 Medium | 서버 재시작 시 단기기억 전부 소실 |
| **레거시 코드 24%** | simulation/report | 🟢 Low | 시뮬레이션 4,446 LOC + 보고서 2,579 LOC 불필요 동재 |

---

## 3. Step 1: 코어 안정화 & 보안 (Week 1-2)

> **목표**: 사내 에이전트가 연결해도 보안 사고가 발생하지 않을 수준으로 코어를 경화한다.

### Task 1.1: `exec()` 보안 취약점 제거 (🔴 최우선)

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 1.1.1 | `ray_executor.py:109`의 `exec(script_code)` → AST 화이트리스트 검증 도입 | 4h | `ast.parse()` → 허용된 노드만 통과 |
| 1.1.2 | 허용 AST 노드 정의: `FunctionDef`, `Return`, `Assign`, `Call` 등 안전한 노드만 | 2h | `import os`, `import subprocess`, `__builtins__` 차단 |
| 1.1.3 | 불허 패턴 차단 테스트 작성 | 2h | `exec("import os; os.system('rm -rf /')")` → `SecurityError` |
| 1.1.4 | 대안: Wasm(wasmer-python) 샌드박스 실행 경로 추가 (선택) | 8h | Ray 사용 불가 환경용 fallback |

**구현 방향**:
```python
# ray_executor.py — 수정 전
exec(script_code, {}, local_ns)

# ray_executor.py — 수정 후
import ast

BLOCKED_NODES = {ast.Import, ast.ImportFrom, ast.Global, ast.Exec}
BLOCKED_NAMES = {"__import__", "eval", "exec", "compile", "open", 
                 "os", "subprocess", "sys", "shutil"}

def _validate_script(code: str) -> None:
    """AST-level security validation before execution."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if type(node) in BLOCKED_NODES:
            raise SecurityError(f"Blocked AST node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise SecurityError(f"Blocked identifier: {node.id}")

_validate_script(script_code)  # 검증 통과 시에만 실행
exec(script_code, {"__builtins__": {}}, local_ns)  # builtins 차단
```

---

### Task 1.2: 인증 및 네트워크 보안 기초

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 1.2.1 | `SECRET_KEY` → 환경변수 필수화 (기본값 제거, 시작 시 검증) | 1h | 기본값 없으면 `ValueError` 발생 |
| 1.2.2 | CORS → 사내 도메인만 허용: `*.company.internal`, `localhost:*` | 1h | `.env` CORS_ORIGINS에서 설정 |
| 1.2.3 | 하드코딩 IP → 환경변수 전환 | 2h | `grep -rn "192.168"` 결과 0건 |
| 1.2.4 | API Key 인증 미들웨어 강화: 헤더 검증 + Rate Limit 적용 | 4h | 인증 없는 요청 400 반환 |
| 1.2.5 | Docker Compose 네트워크를 `internal: true`로 설정 (외부 직접 접근 차단) | 1h | Nginx 리버스 프록시만 노출 |

---

### Task 1.3: 레거시 코드 분리 (경량화)

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 1.3.1 | `src/app/plugins/` 디렉토리 생성, 시뮬레이션 4파일 이동 | 3h | `simulation_runner.py`, `simulation_manager.py`, `simulation_config_generator.py`, `oasis_profile_generator.py` |
| 1.3.2 | `api/simulation.py` → 조건부 블루프린트 등록 (`ENABLE_SIMULATION=false` 기본) | 2h | 사내 배포 시 시뮬레이션 비활성 |
| 1.3.3 | `report_agent.py` → `plugins/reports/` 이동 | 1h | |
| 1.3.4 | `pyproject.toml` 의존성 분리: camel-oasis/camel-ai → `[simulation]` extras | 2h | `pip install -e "."` 60초 이내 |
| 1.3.5 | Config에서 OASIS 관련 설정 조건부 로딩 (`config.py:62-74`) | 1h | |

**효과**: 코어 설치 크기 ~3GB → ~200MB, 설치 시간 10분+ → 60초

---

### Task 1.4: STM 영속화 (Redis 전환)

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 1.4.1 | `storage/stm_backend.py` ABC 인터페이스 정의 | 2h | `add()`, `get()`, `list_all()`, `pop()`, `clear()` |
| 1.4.2 | `InMemorySTMBackend` (기존 Dict 래핑, 하위호환 기본값) | 1h | |
| 1.4.3 | `RedisSTMBackend` 구현 (Sorted Set + TTL) | 6h | TTL=24h, 직렬화=JSON |
| 1.4.4 | `MemoryManager` → STM Backend DI 전환 | 2h | `.env`에서 `STM_BACKEND=redis` 전환 |
| 1.4.5 | Docker Compose에 Redis 서비스 추가 | 1h | `redis:7-alpine` |
| 1.4.6 | 재시작 후 STM 유지 통합 테스트 | 2h | API로 STM 저장 → 컨테이너 재시작 → STM 조회 성공 |

---

### Step 1 완료 체크리스트

- [ ] `exec()` 직접 호출 0건 (AST 검증 게이트 통과 시에만 실행)
- [ ] `grep -rn "192.168" src/` → 0건
- [ ] CORS가 사내 도메인만 허용
- [ ] `pip install -e "."` camel-oasis 없이 60초 이내
- [ ] STM Redis 영속화: 서버 재시작 후 STM 유지
- [ ] 코어 설치 크기 ≤ 300MB

---

## 4. Step 2: 사내 인프라 밀착 통합 (Week 3-6)

> **목표**: 사내의 기존 인프라(Keycloak, Ollama, 사내 LLM)와 Mories를 완전히 연결한다.

### Task 2.1: 사내 SSO/Keycloak 인증 연동

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 2.1.1 | `src/app/auth/` 패키지 생성, `keycloak_auth.py` 모듈 | 4h | |
| 2.1.2 | Keycloak OIDC 토큰 검증 미들웨어 (`@require_auth`) | 8h | Bearer token → Keycloak introspect → 사용자 정보 |
| 2.1.3 | 기존 API Key 인증과 병행 모드 (마이그레이션 기간) | 4h | `AUTH_MODE=keycloak\|apikey\|both` |
| 2.1.4 | Keycloak 그룹/역할 → Mories Scope 매핑 | 4h | `team-backend` → Tribal scope, `admin` → Global |
| 2.1.5 | 대시보드 로그인 페이지 Keycloak redirect 연동 | 4h | |
| 2.1.6 | 통합 테스트: Keycloak 토큰으로 API 호출 검증 | 4h | |

**구현 방향**:
```python
# auth/keycloak_auth.py
from functools import wraps
from flask import request, g, jsonify
import requests

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Missing token"}), 401
        
        # Keycloak token introspection
        resp = requests.post(
            f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token/introspect",
            data={"token": token, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
        )
        token_info = resp.json()
        
        if not token_info.get("active"):
            return jsonify({"error": "Invalid token"}), 401
        
        g.user = token_info.get("preferred_username")
        g.roles = token_info.get("realm_access", {}).get("roles", [])
        g.scope = _map_roles_to_scope(g.roles)
        return f(*args, **kwargs)
    return decorated
```

---

### Task 2.2: 임베딩/LLM 사내 인프라 연결 검증

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 2.2.1 | 사내 Ollama 서버와 `EmbeddingService` 연결 검증 | 2h | `nomic-embed-text` 768d 벡터 생성 확인 |
| 2.2.2 | 사내 vLLM 서버 연동 (있을 경우) | 2h | `EMBEDDING_PROVIDER=openai` + 사내 URL |
| 2.2.3 | 기존 기억 데이터 일괄 임베딩 마이그레이션 스크립트 | 4h | `scripts/migrate_embeddings.py` |
| 2.2.4 | 하이브리드 검색(vector+BM25) E2E 검증 | 4h | 사내 도메인 용어로 검색 품질 테스트 |
| 2.2.5 | 임베딩 캐시 효율 모니터링 (hit rate ≥ 60%) | 2h | Prometheus `memory_cache_hits_total` 확인 |

---

### Task 2.3: API 버전닝 + 응답 표준화

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 2.3.1 | URL prefix `/api/` → `/api/v1/` 일괄 변경 | 6h | 10개 블루프린트 업데이트 |
| 2.3.2 | 기존 `/api/` 경로에 301 Redirect + deprecation header | 2h | 하위호환 유지 |
| 2.3.3 | MCP 서버 엔드포인트 경로 동기화 | 2h | `mories_mcp.py` 매핑 업데이트 |
| 2.3.4 | 통일된 에러 응답 형식 도입 | 4h | `{"status": "error", "code": "...", "message": "..."}` |
| 2.3.5 | 대시보드 HTML 내 fetch URL 업데이트 | 4h | 15개 HTML 파일 |

---

### Task 2.4: 사내 에이전트 파이프라인 연결

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 2.4.1 | Cursor IDE MCP 연결 가이드 + .env 템플릿 | 2h | 사내 개발자가 5분 내 연결 |
| 2.4.2 | Claude Desktop MCP 연결 가이드 | 2h | |
| 2.4.3 | n8n 워크플로우에서 Mories HTTP Request 노드 템플릿 | 4h | ingest → recall → harness 3종 |
| 2.4.4 | Dify 앱에서 Mories Tool Node 연동 예제 | 4h | |
| 2.4.5 | 사내 에이전트 간 Synaptic Bridge 멀티에이전트 검증 | 8h | Agent A 학습 → Agent B recall 성공 |

---

### Task 2.5: 모니터링 실전 구축

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 2.5.1 | Docker Compose에 Prometheus + Grafana 추가 | 4h | `docker-compose.monitoring.yml` |
| 2.5.2 | Grafana 대시보드 4패널: QPS, Latency, Error Rate, Memory Health | 4h | |
| 2.5.3 | 감쇠 실행(run_decay) 주기 + 결과 메트릭 노출 | 2h | |
| 2.5.4 | 슬랙/Teams 알림 연동 (에러율 5% 초과 시) | 2h | AlertManager → Webhook |

---

### Step 2 완료 체크리스트

- [ ] Keycloak SSO 토큰으로 API 호출 성공
- [ ] 사내 Ollama/vLLM으로 하이브리드 검색 작동
- [ ] API v1 prefix 적용 + MCP 동기화
- [ ] Cursor/Claude/n8n에서 Mories 연결 완료
- [ ] Grafana 대시보드로 실시간 모니터링
- [ ] Agent A→B Synaptic Bridge 검증 통과

---

## 5. Step 3: 사내 보급형 패키지 & 온보딩 (Week 7-8)

> **목표**: 사내 개발팀이 자기 에이전트에 Mories를 1~2줄 코드로 붙일 수 있도록 한다.

### Task 3.1: 사내 Python SDK (Private Registry)

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 3.1.1 | `sdk/python/` 디렉토리 생성, `pyproject.toml` 설정 | 2h | `mories-sdk` 패키지 |
| 3.1.2 | `MoriesClient` 핵심 인터페이스: `remember()`, `recall()`, `imprint()`, `health()` | 12h | |
| 3.1.3 | 하네스 하위 클라이언트: `client.harness.record()`, `.execute()`, `.evolve()` | 4h | |
| 3.1.4 | Keycloak 토큰 자동 갱신 통합 | 4h | `MoriesClient(auth="keycloak")` |
| 3.1.5 | 타입 힌트 + Pydantic 모델: `Memory`, `SearchResult`, `HarnessPattern` | 4h | |
| 3.1.6 | 사내 프라이빗 PyPI(Nexus/Artifactory) 배포 | 2h | `pip install mories-sdk` (사내망) |

**목표 사용 예**:
```python
from mories import MoriesClient

# 사내 SSO 토큰 기반 인증
client = MoriesClient(
    url="https://mories.company.internal",
    auth="keycloak"  # 자동으로 Keycloak 토큰 흭득/갱신
)

# 기억 저장
client.remember(
    content="FastAPI의 Depends는 Flask Blueprint와 달리 함수 시그니처 기반 DI를 사용",
    salience=0.8,
    scope="tribal",
    tags=["fastapi", "architecture"]
)

# 시맨틱 검색
results = client.recall("FastAPI dependency injection 패턴", limit=5)

# 팀 필수 규칙 각인
client.imprint(
    content="PR 머지 전 반드시 2인 이상 코드 리뷰 필수",
    category="policy",
    priority=10
)
```

---

### Task 3.2: LangChain 사내 표준 플러그인

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 3.2.1 | `langchain-mories` 패키지 생성 | 2h | |
| 3.2.2 | `MoriesMemory(BaseChatMemory)` 구현 | 8h | LangChain 인터페이스 준수 |
| 3.2.3 | 사내 LangGraph StateGraph 통합 예제 | 4h | |
| 3.2.4 | 사내 프라이빗 PyPI 배포 | 1h | |

---

### Task 3.3: 사내 개발자 온보딩 문서

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 3.3.1 | 사내 위키(Confluence/Notion) 5분 퀵스타트 작성 | 4h | 설치 → 기억 저장 → 검색 |
| 3.3.2 | Swagger UI 활성화: `/api/v1/docs` | 4h | `flasgger` 또는 `flask-smorest` |
| 3.3.3 | 사내 에이전트 연동 레시피북 (Cursor/Claude/n8n/Dify) | 4h | 스크린샷 포함 |
| 3.3.4 | FAQ: "메모리 감쇠란?", "스코프 언제 쓰나?", "하네스가 뭔가?" | 2h | |
| 3.3.5 | 사내 발표용 슬라이드 (30분 기술 소개) | 4h | |

---

### Task 3.4: 파일럿 팀 실전 적용

| # | 세부 작업 | 공수 | 완료 기준 |
|---|----------|------|----------|
| 3.4.1 | 파일럿 팀 선정 (3-5명 개발자) | 1일 | |
| 3.4.2 | 1주간 일상 업무에 Mories 에이전트 적용 | 1주 | |
| 3.4.3 | 파일럿 피드백 수집 + 이슈 해결 | 3일 | |
| 3.4.4 | 파일럿 결과 보고서 작성 (사내 확산 판단 근거) | 1일 | |

---

### Step 3 완료 체크리스트

- [ ] `pip install mories-sdk` → 사내 프라이빗 레지스트리에서 설치
- [ ] `from mories import MoriesClient` → 3줄 코드로 기억 저장/검색
- [ ] LangChain Memory 플러그인 사내 배포
- [ ] Swagger UI `/api/v1/docs` 활성화
- [ ] 파일럿 팀 1주 실전 운용 + 피드백 수집 완료

---

## 6. 기존 글로벌 계획 대비 변경 사항

### 유지 (✅), 앞당김 (⏫), 축소 (📉), 동결 (⏸️)

| 기존 Task | 변경 | 사내 로드맵 위치 | 근거 |
|-----------|------|----------------|------|
| 0.1 레거시 분리 | ✅ 유지 | Step 1 — Task 1.3 | 설치 경량화 필수 |
| 0.2 의존성 재구조화 | ✅ 유지 | Step 1 — Task 1.3.4 | camel-oasis 제거 |
| 0.3 코드 영문화 | ⏸️ **동결** | — | 사내 한국어 팀이므로 급하지 않음 |
| 0.4 API 버전닝 | ✅ 유지 | Step 2 — Task 2.3 | |
| 0.5 보안 하드닝 | ⏫ **최우선** | Step 1 — Task 1.1, 1.2 | exec() 취약점 |
| 0.6 거대 파일 리팩터링 | 📉 축소 | 추후 | 기능에 영향 없으므로 운용 후 진행 |
| 1.1 Python SDK | ✅ 유지 | Step 3 — Task 3.1 | 사내 레지스트리 배포 |
| 1.2 JS SDK | ⏸️ **동결** | — | 사내 에이전트는 Python 중심 |
| 1.3 OpenAPI 문서 | 📉 축소 | Step 3 — Task 3.3.2 | Swagger UI만 우선 |
| 1.4 개발자 포털(docs.mories.dev) | ⏸️ **동결** | — | 사내 위키로 대체 |
| 1.5 LangChain 플러그인 | ✅ 유지 | Step 3 — Task 3.2 | 사내 에이전트 표준 |
| 2.1 OAuth2 (Google/GitHub) | 🔄 **변경** | Step 2 — Task 2.1 | → Keycloak SSO로 대체 |
| 2.2 STM Redis | ⏫ **앞당김** | Step 1 — Task 1.4 | 운용 안정성 최우선 |
| 2.3 Storage ABC | ⏸️ 동결 | — | 사내는 Neo4j 고정 운용 |
| 2.4 CI/CD | 📉 축소 | 추후 | 사내 Jenkins/GitLab 연동은 별도 |
| 2.5 벡터 검색 | ✅ **이미 완료** | Step 2 — Task 2.2에서 검증만 | 코드 구현 완료 상태 |
| 2.6 K8s Helm | ⏸️ 동결 | — | Docker Compose로 충분 |
| 2.7 부하 테스트 | ⏸️ 동결 | — | 사내 30명 이하 규모에서 불필요 |
| **Phase 3 전체** | ⏸️ **전면 동결** | — | Stripe, 멀티테넌트, GDPR 불필요 |

### 새로 추가된 Task (사내 전용)

| 신규 Task | 위치 | 근거 |
|-----------|------|------|
| Keycloak SSO 연동 | Step 2 — Task 2.1 | 사내 인증 표준 |
| 사내 에이전트 파이프 연결 (Cursor/n8n/Dify) | Step 2 — Task 2.4 | 실전 사용 가능해야 함 |
| Grafana 모니터링 실전 구축 | Step 2 — Task 2.5 | 운영 가시성 확보 |
| 파일럿 팀 실전 적용 | Step 3 — Task 3.4 | 내부 검증 없이 확산 불가 |

---

## 7. 사내 적용 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                        사내 네트워크                                  │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │ Cursor   │   │ Claude   │   │ n8n      │   │ Dify     │        │
│  │ (개발팀) │   │ Desktop  │   │ (자동화) │   │ (AI앱)  │        │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘        │
│       │              │              │              │               │
│       └──────────────┴──────┬───────┴──────────────┘               │
│                             │ MCP Protocol / REST API               │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │                  Mories Core Server                       │      │
│  │  ┌──────────┐  ┌────────────┐  ┌──────────────────────┐ │      │
│  │  │ Keycloak │  │ Cognitive  │  │ Harness              │ │      │
│  │  │ Auth     │  │ Memory     │  │ Orchestration        │ │      │
│  │  │ Gateway  │  │ Engine     │  │ (DSL+7 Executors)    │ │      │
│  │  └──────────┘  └──────┬─────┘  └──────────────────────┘ │      │
│  │                       │                                   │      │
│  │  ┌──────────┐  ┌─────┴──────┐  ┌──────────────────────┐ │      │
│  │  │ Redis    │  │ Hybrid     │  │ Prometheus           │ │      │
│  │  │ (STM)    │  │ Search     │  │ Metrics              │ │      │
│  │  │          │  │ Vec + BM25 │  │                      │ │      │
│  │  └──────────┘  └──────┬─────┘  └──────────────────────┘ │      │
│  └───────────────────────┼──────────────────────────────────┘      │
│                          │                                          │
│  ┌───────────────────────┼──────────────────────────────────┐      │
│  │              Infrastructure Layer                          │      │
│  │  ┌──────────┐  ┌─────┴──────┐  ┌──────────┐             │      │
│  │  │ Neo4j    │  │ Ollama /   │  │ Grafana  │             │      │
│  │  │ 5.18     │  │ vLLM       │  │          │             │      │
│  │  │ (Graph)  │  │ (Embedding)│  │ (Monitor)│             │      │
│  │  └──────────┘  └────────────┘  └──────────┘             │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
│  ┌──────────────────────────────┐                                  │
│  │  Keycloak (사내 SSO)          │                                  │
│  │  LDAP/AD 연동                 │                                  │
│  └──────────────────────────────┘                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 8. 리스크 및 Go/No-Go

### Go/No-Go 게이트

| 시점 | 조건 | No-Go 시 행동 |
|------|------|---------------|
| **Step 1 완료 (2주)** | exec() 0건, Redis STM 작동, 코어 60초 설치 | 보안 이슈 미해결 시 도입 불가 |
| **Step 2 완료 (6주)** | Keycloak 인증 통과, 검색 품질 OK, Cursor 연결 성공 | 인프라 불일치 → 사내 환경 추가 커스텀 |
| **Step 3 완료 (8주)** | SDK 설치 가능, 파일럿 팀 1주 운용 성공 | 파일럿 실패 → 피드백 기반 2차 반복 |

### 사내 도입 고유 리스크

| 리스크 | 확률 | 영향 | 완화 전략 |
|--------|------|------|---------|
| Ollama 사내 서버 성능 부족 | 중 | 임베딩 지연 | 임베딩 캐시(2000항) 활용 + 사내 vLLM 대안 |
| Neo4j 사내 운영 부담 | 중 | 장애 시 에이전트 전체 중단 | Docker healthcheck + 자동 재시작 + 일일 백업 |
| Keycloak 연동 인증 복잡 | 낮 | SSO 지연 | API Key 병행 모드(Both)로 점진 전환 |
| 개발자 도입 저항 | 중 | 사용률 저조 | 파일럿 팀 성공 사례 + 5분 온보딩 + 슬랙 채널 |

---

## 9. KPI 및 성공 기준

### Step별 핵심 KPI

| 지표 | Step 1 (2주) | Step 2 (6주) | Step 3 (8주) | 운용 3개월 |
|------|-------------|-------------|-------------|-----------|
| **보안 취약점 수** | 0건 | 0건 | 0건 | 0건 |
| **코어 설치 시간** | ≤ 60초 | 유지 | 유지 | 유지 |
| **검색 품질 (Top-5 적중률)** | — | ≥ 70% | ≥ 75% | ≥ 80% |
| **API 평균 응답 시간** | — | ≤ 300ms | ≤ 200ms | ≤ 200ms |
| **연결된 에이전트 수** | 0 | ≥ 3 (Cursor/Claude/n8n) | ≥ 5 | ≥ 10 |
| **일일 활성 기억 조작수** | 0 | — | ≥ 50 | ≥ 200 |
| **파일럿 팀 만족도** | — | — | NPS ≥ 20 | NPS ≥ 30 |

### 성공 정의

> **8주 후, 사내 개발자가 `pip install mories-sdk` 하고 3줄 코드로 자기 에이전트에 장기 기억을 붙여서, 어제 실패한 빌드 경험을 오늘 에이전트가 자동으로 회피하는 것을 체험한다.**

---

## 부록: 글로벌 확장 경로 (사내 성공 이후)

사내 도입이 검증된 후, 기존 `06_product_transition_plan.md`의 다음 단계를 순차 재개합니다:

```
사내 8주 완료
    ↓
사내 3개월 운용 + 안정화
    ↓
Phase 1 재개: 영문화 + PyPI 공개 배포 + 개발자 포털
    ↓
Phase 2 재개: CI/CD + K8s + 벡터 검색 고도화
    ↓
Phase 3: Cloud SaaS (시장 검증 후 결정)
```

**사내 성공이 글로벌 진출의 가장 강력한 PMF 증거가 됩니다.**

---

*이 문서는 기존 `06_product_transition_plan.md` (글로벌 SaaS)를 사내 도입 목적으로 재구성한 실행 계획입니다.*
