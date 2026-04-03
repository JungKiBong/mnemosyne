# Mories 핸드오버 — Part 2: Phase 완료 현황 & 미완료 작업
# 문서 경로: docs/handover/HANDOVER_v1.0_part2_phase_status.md
# 버전: v1.0 | 작성일: 2026-03-31

---

## 1. 완료된 Phase 현황

| Phase | 이름 | 핵심 커밋 | 상태 |
|-------|------|-----------|------|
| A | 아키텍처 정리 (싱글톤, 레거시 제거) | 초기 커밋들 | ✅ 완료 |
| B | 시뮬레이션 기반 인지 기억 엔진 통합 | 초기 커밋들 | ✅ 완료 |
| C | Supermemory 선택적 가속/동기화 | 초기 커밋들 | ✅ 완료 |
| D | 에어갭 호환 + E2E 테스트 21건 | 초기 커밋들 | ✅ 완료 |
| E | 용어집(Terminology) 서비스 + UI | `e5828f9` | ✅ 완료 |
| F | Air-gap LLM/Embedding 전환 | `371171b`, `b53b2fd` | ✅ 완료 |
| G-A | Tech Debt Sprint (6개 버그 수정) | `54e01b7` | ✅ 완료 |
| G-B | Harness (Webhook, /health, Docker prod) | `dd61998` | ✅ 완료 |
| G-C | Data Pipeline 경량화 (pandas 제거) | `8767f18` | ✅ 완료 |

> **현재 로컬은 origin/main보다 4커밋 앞서 있음. Push 전:**
> ```bash
> git push origin main
> ```

### Phase G-B에서 새로 추가된 파일들
- `src/app/utils/webhook.py` — Harness WebhookPublisher (신규)
- `docker-compose.prod.yml` — 프로덕션 Docker Compose 오버라이드 (신규)

---

## 2. 현재 테스트 현황 (2026-03-31 기준)

- **전체:** 98 passed / 13 failed (111 total)
- **핵심 파이프라인 E2E:** 21/21 통과 ✅
- **실패 원인:** 아래 P0 버그들 참조

---

## 3. 미완료 작업 (P0 — 즉시 수정 필요)

### [BUG-1] `memory.py` current_app 미임포트
- **파일:** `src/app/api/memory.py`, `_get_audit()` 함수
- **오류:** `NameError: name 'current_app' is not defined`
- **수정:** 파일 상단에 `from flask import current_app` 추가
- **영향:** TestAuditAPI 2건 실패

### [BUG-2] reconciliation_service.py Neo4j datetime() 호환성
- **파일:** `src/app/storage/reconciliation_service.py`, Line 233, 356
- **오류:** `Neo4jError: Invalid call signature for DateTimeFunction: Provided input was [Long(xxx)]`
- **원인:** `n.last_accessed` 값이 ISO 문자열이 아닌 경우 datetime() 파싱 실패
- **수정:** Cypher 쿼리에 정규식 검증 추가:
  ```cypher
  -- 기존 (오류 유발)
  AND datetime(n.last_accessed) < datetime() - duration('P30D')

  -- 수정 후
  AND n.last_accessed IS NOT NULL
  AND n.last_accessed =~ '\\d{4}-\\d{2}-\\d{2}.*'
  AND datetime(n.last_accessed) < datetime() - duration('P30D')
  ```
- **영향:** TestReconciliationAPI 3건, test_reconciliation.py 1건 실패

---

## 4. 미완료 작업 (P1 — 다음 세션 주요 작업)

### [TASK-1] Git Push (5분)
```bash
cd /Users/jungkibong/Projects/tmp/mirofish-supermemory
git push origin main
```

### [TASK-2] n8n 워크플로우 실용화 (1.5h) - ✅ 완료
- Webhook Publisher(`src/app/utils/webhook.py`)가 발행하는 이벤트를 n8n이 실제 소비
- 대상 이벤트:
  - `memory.promoted` → n8n → Slack/알림
  - `memory.decayed` → n8n → 주간 리포트
  - `health.degraded` → n8n → 장애 알림
- `docs/n8n/` 에 워크플로우 템플릿과 문서 추가 완료

### [TASK-3] MCP 서버 패키징 고도화 (2h)
- `mcp_server/` 디렉터리에 서버 코드 이미 존재
- 공개 배포를 위한 패키징 및 문서화 필요
- 기존 파일: `mcp_server/setup.sh`, `mcp_server/claude_desktop_config.json`

### [TASK-4] 멀티테넌트 지원 (4h+)
- 여러 사용자의 기억 공간 격리
- 현재 `scope` 필드(`personal`, `tribal`, `social`, `global`)만 있음
- `tenant_id` 포함 Neo4j 쿼리 레이어 추가 필요

### [TASK-5] 배치 인제스천 API (2h) - ✅ 완료
- `POST /api/ingest/batch/async` — 비동기 멀티스레드 기반 배치 처리 구현
- Background Worker (ThreadPoolExecutor) 및 n8n Webhook 연동 완료

### [TASK-6] 보안 강화 (2h) - ✅ 완전 완료
- Rate Limiting (Flask-Limiter) 도입 완료 (`/api/ingest` 계열에 리미트 적용)
- CORS 프로덕션 설정 완료 (`CORS_ORIGINS` 환경변수 연동)
- API Key 자동 회전 - `memory_encryption.py`를 통한 암호화 키 전체 회전/갱신 로직 및 API(`/api/admin/security/rotate`) 구현 완료

---

## 5. 중기 로드맵 (Phase H~)

| Phase | 이름 | 설명 |
|-------|------|------|
| H | Multi-Agent 완성 | ADK/LangGraph 에이전트와 MCP 완전 연동 |
| I | Vector Search 고도화 | Neo4j Vector Index + HNSW |
| J | Federation | 다수 Mories 인스턴스 간 기억 연합 |
