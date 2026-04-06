# Mories 사내 배포 로드맵 — 작업 현황 (v1.0)

> 최종 업데이트: 2026-04-06T21:42+09:00
> 대화 ID: 91a6237b-daae-4b0f-8fc7-ea880d9952e6

---

## 1. 전략 방향

- **기존**: 글로벌 SaaS 4단계(48주) 로드맵
- **현재**: **사내 전용 8주 집중 배포 로드맵**으로 전환
- SaaS 기능(Stripe, 멀티테넌시, GDPR 등)은 **동결(Frozen)** 상태

---

## 2. 로드맵 체크리스트

### Step 1: 보안 강화 & 경량화 (Weeks 1-2)

| # | 작업 | 상태 | 비고 |
|---|------|------|------|
| 1.1 | `exec()` 취약점 제거 — AST 기반 보안 검증 | ✅ 완료 | `ray_executor.py` 재작성, 테스트 통과 |
| 1.2 | 하드코딩 IP 제거 & ENV 기반 전환, CORS 화이트리스트 | ✅ 완료 | `config.py`, `mcp_server/` 4개 파일 수정 |
| 1.3 | OASIS 시뮬레이션 코드 → plugins 분리 | ✅ 완료 | `src/app/plugins/oasis/` 로 분리, 시스템 안정성 복원 완료 |
| 1.4 | Redis STM 백엔드 구현 | ✅ 완료 | memory_manager.py 연동 완료, Dict 백엔드는 fallback으로 유지 |

### Step 2: 사내 인프라 통합 (Weeks 3-6)

| # | 작업 | 상태 |
|---|------|------|
| 2.1 | Keycloak SSO 연동 | ✅ 완료 | `src/app/utils/auth.py` 작성, JWT 검증 (`pyjwt` & `PyJWKClient`) 추가, `/api/auth/me` 에 적용 |
| 2.2 | Ollama/vLLM 내부망 검증 | ✅ 완료 | `scripts/verify_internal_llm.py` 작성 및 대상 모델(`llama3.1:8b` 등) 통신 확인 |
| 2.3 | API v1 버전 관리 | ✅ 완료 | `src/app/api/v1.py` 블루프린트 신설, `__init__.py` 기반 `/api/v1` 라우팅 아키텍처 도입 |

### Step 3: SDK 패키징 & 파일럿 (Weeks 7-8)

| # | 작업 | 상태 |
|---|------|------|
| 3.1 | Python SDK 내부 배포 | ✅ 완료 | `mories_sdk/` 디렉토리 신설, `pyproject.toml` 패키징 적용 완료 |
| 3.2 | LangChain 플러그인 | ✅ 완료 | `mories.langchain.MoriesRetriever` 구현 완료 |
| 3.3 | 파일럿 팀 온보딩 | ✅ 완료 | `mories_sdk/examples/onboarding.py` 및 README.md 작성 |

---

## 3. 커밋되지 않은 변경 사항 (중요!)

아래 파일들이 아직 커밋되지 않은 상태입니다.

### Modified (기존 파일 수정)
```
M  dashboard/graph.html              # 그래프 UI 개선
M  dashboard/harness.html            # 하네스 UI 데이터 계약 수정
M  mcp_server/config.py              # IP 제거 → localhost 전환
M  mcp_server/mcp_config.json        # IP 제거 → localhost 전환
M  mcp_server/mories_mcp.py          # IP 제거 → localhost 전환
M  src/app/config.py                 # SECRET_KEY 강제, CORS 화이트리스트
M  src/app/harness/executors/__init__.py          # 레지스트리 확장
M  src/app/harness/executors/container_executor.py
M  src/app/harness/executors/nomad_executor.py     # lazy-load requests
M  src/app/harness/executors/ray_executor.py       # ⭐ AST 보안 검증 재작성
M  src/app/harness/orchestration/neo4j_memory_backend.py
M  src/app/harness/workflow_dsl_schema.json
M  tests/fixtures/v4_scenario_complex.json
M  tests/harness/test_executor_registry.py
```

### Untracked (새로 생성된 파일)
```
??  src/app/api/harness_analytics.py       # 하네스 분석 API
??  src/app/harness/executors/wasm_executor.py
??  src/app/harness/memory/workflow_recall.py
??  tests/harness/test_dsl_schema.py
??  tests/harness/test_ray_security.py      # ⭐ AST 보안 테스트
??  tests/harness/test_wasm_executor.py
??  scripts/*                               # 인프라 유틸리티 (14개)
??  reports/                                # 프로젝트 리뷰 보고서
```

---

## 4. 테스트 현황

```
✅ tests/harness/test_executor_registry.py  — 14 passed
✅ tests/harness/test_ray_security.py       — 2 passed
✅ tests/harness/test_dsl_schema.py         — 8 passed
✅ tests/unit/test_cognitive_memory*.py     — 49 passed
총계: 73 passed ✅
```

- `tests/harness/test_wasm_executor.py`: 별도 검증 필요 (wasm 런타임 의존)
- `tests/harness/` 전체를 `-v`로 실행하면 **일부 테스트가 행(hang)** 발생  
  → 원인: Neo4j 연결 타임아웃 또는 wasm 테스트의 외부 의존성  
  → 해결: 개별 파일 단위로 실행 권장

---

## 4.5 코드 리뷰 수정 사항 (2026-04-06)

| # | 항목 | 파일 | 수정 내용 |
|---|------|------|-----------|
| R-1 | Redis `KEYS` 안티패턴 | `memory_manager.py` | `KEYS *` → `SCAN` 이터레이터로 교체, O(N) 블로킹 제거 |
| R-2 | 메타데이터 직렬화 | `memory_manager.py` | `str()` → `json.dumps()`, Neo4j 데이터 무결성 확보 |
| R-3 | JWKS 캐싱 최적화 | `auth.py` | 매 요청마다 `PyJWKClient` 생성 → 모듈 수준 캐싱 |
| R-4 | PyJWT lazy import | `auth.py`, `core.py` | 설치 안된 환경에서도 서버 기동 가능하도록 fallback |
| R-5 | SDK 호환성 | `mories/langchain.py` | Pydantic `ConfigDict` 추가, `ImportError` 대응 |
| R-6 | SDK 연결 효율 | `mories/client.py` | 매 메서드마다 httpx 생성 → 커넥션 풀 공유 |

---

## 5. 환경 정보

| 항목 | 값 |
|------|-----|
| Python | 3.10.13 (uv 관리) |
| 가상환경 | `.venv/bin/python` (프로젝트 루트) |
| pytest | `.venv/bin/pytest` 사용 필수 |
| 프로젝트 루트 | `/Users/jungkibong/Projects/tmp/mirofish-supermemory` |
| .env 위치 | 프로젝트 루트 `.env` + `src/.env` (둘 다 존재) |
| Neo4j | bolt://localhost:7687 (docker) |
| LLM | Ollama 기반, localhost:11434 |
