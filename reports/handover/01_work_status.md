# Mories 사내 배포 로드맵 — 작업 현황 (v1.1)

> 최종 업데이트: 2026-04-07
> 대화 ID: 현재 세션 종료

---

## 1. 전략 방향

- **기존**: 글로벌 SaaS 4단계(48주) 로드맵
- **현재**: **사내 전용 8주 집중 배포 로드맵**으로 전환
- SaaS 기능(Stripe, 멀티테넌시, GDPR 등)은 **동결(Frozen)** 상태

---

## 2. 로드맵 체크리스트

### Step 1: 보안 강화 & 경량화 (완료)
- `exec()` 취약점 제거 — AST 기반 보안 검증
- 하드코딩 IP 제거 & ENV 기반 전환, CORS 화이트리스트
- Redis STM 백엔드 구현

### Step 2: 사내 인프라 통합 (완료)
- Keycloak SSO 연동 (`/api/auth/me`)
- Ollama/vLLM 내부망 검증
- API v1 버전 관리 블루프린트 도입

### Step 3: SDK 패키징 & 파일럿 (완료)
- Python SDK 내부 배포 (`mories_sdk/`)
- LangChain 플러그인 (`MoriesRetriever`)

### Step 4: 대시보드 API 최적화 및 안정화 (완료)
| 작업 | 상태 | 구체적 내용 |
|------|------|-------------|
| 4.1 대시보드 API 통일성 확보 | ✅ 완료 | 6개의 프론트엔드 모듈(`memory.html`, `synaptic.html`, `harnessUI.js`, `workflows.html`, `maturity.html`, `terminology.html`)에서 raw `fetch()`를 모두 `/assets/js/apiClient.js` (`window.moriesApi`)로 치환 |
| 4.2 Auth Token 자동화 | ✅ 완료 | Bearer 토큰이 `apiClient.js`의 공통 헤더를 통해 모든 요청에 자동 삽입됨 |
| 4.3 하드코딩 제거 | ✅ 완료 | `BASE`, `API_BASE` 변수를 제거하고 상대 경로 엔드포인트(`.get('/api/v1/...')`) 적용 |
| 4.4 CSS 린트 수정 | ✅ 완료 | `background-clip: text` 누락으로 인한 CSS 경고 수정 완료 |

### Step 5: P4 분산 인프라 연결 점검 (완료)
| 작업 | 상태 | 구체적 내용 |
|------|------|-------------|
| 5.1 Dashboard UX 경량화 | ✅ 완료 | 불필요한 Data Products 탭 제거 및 에러핸들링 독립 try-catch 처리 추가 |
| 5.2 분산 Executor Unit Test | ✅ 완료 | Nomad, Ray, Container 분산 파이프라인 개별 검증(`test_nomad_executor.py`, `test_ray_executor.py` 등) 모의 연동 및 타임아웃 예비 테스트 통과 |

---

## 3. 커밋되지 않은 변경 사항 (중요!)

아래 파일들이 아직 커밋되지 않은 상태입니다.

### Modified (기존 파일 수정 - 프론트엔드 포함)
```
M  dashboard/api-docs.html           # UI 개선
M  dashboard/assets/js/apiDocs.js    # API Playground 분리
M  dashboard/assets/js/harnessUI.js  # 14개의 raw fetch 제거 & moriesApi 연동
M  dashboard/harness.html            # UI 개선
M  dashboard/index.html              
M  dashboard/maturity.html           # moriesApi 연동 및 CSS 수정
M  dashboard/memory.html             # moriesApi 연동 및 CSS 수정
M  dashboard/memory_history.html     # moriesApi 연동
M  dashboard/synaptic.html           # moriesApi 연동
M  dashboard/terminology.html        # moriesApi 연동 및 CSS 수정
M  dashboard/workflows.html          # moriesApi 연동
M  tests/fixtures/v4_scenario_complex.json
M  tests/harness/test_executor_registry.py
# (이하 백엔드 스크립트 수정사항...)
```

### Untracked (새로 생성된 파일)
```
??  src/app/api/harness_analytics.py
??  src/app/harness/executors/wasm_executor.py
??  src/app/harness/memory/workflow_recall.py
??  dashboard/assets/js/apiClient.js # 싱글톤 API 클라이언트 
??  tests/harness/test_dsl_schema.py
??  tests/harness/test_ray_security.py
??  tests/harness/test_wasm_executor.py
??  scripts/*                               
??  reports/                                
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
- **알림**: `tests/harness/` 전체를 `-v`로 실행 시 행(hang) 현상이 여전할 수 있으므로 개별 테스트 파일 실행 권장.
