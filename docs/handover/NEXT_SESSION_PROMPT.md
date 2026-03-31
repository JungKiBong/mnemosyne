# 새 세션 시작 프롬프트
# 문서 경로: docs/handover/NEXT_SESSION_PROMPT.md
# 버전: v1.0 | 작성일: 2026-03-31
# 용도: 새 대화창을 열 때 첫 번째로 붙여넣을 프롬프트

---

아래 내용을 새 대화 창에 복사해서 붙여넣기 하세요.

==========================================================================
COPY FROM HERE
==========================================================================

# Mories 프로젝트 작업 인계 (컨텍스트 복원)

## 현재 세션 정보
- **이전 대화 ID:** 2e4d554d-bcf8-4c5a-8a1a-d22313c5ddfd
- **저장소:** `/Users/jungkibong/Projects/tmp/mirofish-supermemory`
- **핸드오버 문서:** `docs/handover/` 디렉터리 (파트별로 분리됨)

## 작업 재개 요청

이전 세션에서 Mories 프로젝트의 Phase A~G까지 완료하였습니다.
핸드오버 문서를 먼저 읽고 컨텍스트를 복원한 뒤, 이어서 작업을 진행해 주세요.

### 핸드오버 문서 위치
```
/Users/jungkibong/Projects/tmp/mirofish-supermemory/docs/handover/
├── HANDOVER_v1.0_part1_overview.md      # 프로젝트 개요, 원칙, 코딩 표준
├── HANDOVER_v1.0_part2_phase_status.md  # 완료/미완료 Phase 현황
├── HANDOVER_v1.0_part3_troubleshooting.md  # 트러블슈팅 기록
└── NEXT_SESSION_PROMPT.md               # 이 파일
```

### 세션 시작 시 반드시 위 문서들을 읽어, 다음을 확인해 주세요
1. `HANDOVER_v1.0_part1_overview.md` — 원칙 및 표준 확인
2. `HANDOVER_v1.0_part2_phase_status.md` — 어디까지 완료됐는지 확인
3. `HANDOVER_v1.0_part3_troubleshooting.md` — 이미 발생한 이슈 파악

---

## 작업 우선순위

**P0 (즉시 수정):**
- [BUG-1] `src/app/api/memory.py`의 `_get_audit()` 함수에서 `current_app` 미임포트
  → `from flask import current_app` 추가
- [BUG-2] `src/app/storage/reconciliation_service.py` 233, 356번째 줄
  → Neo4j `datetime()` 함수에 ISO 문자열 정규식 검증 추가

**P1 (이후 작업):**
- git push origin main (4개 커밋 미push 상태)
- n8n 워크플로우 실용화 (`webhook.py` 연동)
- MCP 서버 패키징 고도화
- 배치 인제스천 API (`POST /api/ingest/batch`)

---

## 필수 준수 사항(공용 자원 보호)

> 아래 항목은 이전 세션에서도 강조된 내용이며, 절대 위반 금지

1. `data/gitlab/` 디렉터리 — 공용 GitLab 데이터, 절대 수정/커밋 금지
2. 루트 `docker-compose.yml` — 다른 서비스와 공유, 수정 전 반드시 확인
3. `.env` 파일 — 실 비밀번호 포함, Git 커밋 금지 (`.env.example` 사용)
4. Neo4j 비밀번호(`mirofish`), API 키 — 코드에 하드코딩 절대 금지

---

## 환경 설정 규칙

- **Python:** 반드시 `.venv` 가상환경에서 실행
  ```bash
  source .venv/bin/activate
  python3 --version  # 3.13.x 확인
  ```
- **테스트:** 임시 테스트는 `tests/temp/`에 저장 (나중에 안전하게 삭제 가능)
- **LLM:** 에어갭 내 Ollama 또는 vLLM 서버 사용 (외부 API 직접 호출 금지)

---

## 코딩 표준

1. **예외처리:** 구체적 예외 타입으로 잡고, `exc_info=True`로 로깅 후 처리
2. **자원 반환:** DB 드라이버/세션은 `with` 블록 필수 (자동 반환)
3. **주석:** 한글로 WHY를 설명 (WHAT은 코드 자체가 설명)
4. **로깅:** `logging.getLogger('mirofish.<모듈명>')` 네임스페이스 통일
5. **파일 길이:** 하나의 파일이 너무 길어지면 기능별로 분리

---

## 세션 관리 안내

- 작업 중 컨텍스트가 너무 길어지면, 새 대화창이 필요하다고 알려 주세요.
- 새 대화창을 시작할 때는 이 문서(`NEXT_SESSION_PROMPT.md`)를 업데이트한 뒤 새 세션에서 사용하세요.
- 트러블슈팅이 발생하면 `HANDOVER_v1.0_part3_troubleshooting.md`에 기록해 주세요.

==========================================================================
COPY UNTIL HERE
==========================================================================
