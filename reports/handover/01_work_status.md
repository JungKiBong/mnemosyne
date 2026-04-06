# Mories 사내 배포 로드맵 — 작업 현황 (v1.0)

> 최종 업데이트: 2026-04-06T15:20+09:00
> 대화 ID: 0950ca8c-c9d3-4b58-bc29-2061f2ea9d29

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
| 1.3 | OASIS 시뮬레이션 코드 → plugins 분리 | ❌ 미착수 | **다음 세션 최우선 작업** |
| 1.4 | Redis STM 백엔드 구현 | ❌ 미착수 | 현재 InMemory만 동작 |

### Step 2: 사내 인프라 통합 (Weeks 3-6)

| # | 작업 | 상태 |
|---|------|------|
| 2.1 | Keycloak SSO 연동 | ❌ 미착수 |
| 2.2 | Ollama/vLLM 내부망 검증 | ❌ 미착수 |
| 2.3 | API v1 버전 관리 | ❌ 미착수 |

### Step 3: SDK 패키징 & 파일럿 (Weeks 7-8)

| # | 작업 | 상태 |
|---|------|------|
| 3.1 | Python SDK 내부 배포 | ❌ 미착수 |
| 3.2 | LangChain 플러그인 | ❌ 미착수 |
| 3.3 | 파일럿 팀 온보딩 | ❌ 미착수 |

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
✅ tests/harness/test_executor_registry.py  — 14 passed (2.34s)
✅ tests/harness/test_ray_security.py       — 2 passed  (2.34s)
✅ tests/harness/test_dsl_schema.py         — 8 passed  (2.34s)
```

- `tests/harness/test_wasm_executor.py`: 별도 검증 필요 (wasm 런타임 의존)
- `tests/harness/` 전체를 `-v`로 실행하면 **일부 테스트가 행(hang)** 발생  
  → 원인: Neo4j 연결 타임아웃 또는 wasm 테스트의 외부 의존성  
  → 해결: 개별 파일 단위로 실행 권장

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
