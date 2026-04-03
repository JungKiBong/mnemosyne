# Mories 핸드오버 — Part 3: 트러블슈팅 기록 (v2.0)
# 문서 경로: docs/handover/HANDOVER_v2.0_part3_troubleshooting.md
# 버전: v2.0 | 갱신일: 2026-04-02
# 용도: 반복 이슈 방지를 위한 발생 원인/해결책 누적 기록

---

## TS-001: Neo4j datetime() 호환성 오류 [미해결]

- **상태:** ⚠️ 미해결 (테스트 실패 유발)
- **증상:** `Neo4j ClientError: Invalid call signature for DateTimeFunction`
- **원인:** `n.last_accessed` 필드에 ISO 문자열 대신 Unix Long/null 존재 시 `datetime()` 함수 실패
- **해결 방법:**
  ```cypher
  AND n.last_accessed IS NOT NULL
  AND n.last_accessed =~ '\\d{4}-\\d{2}-\\d{2}.*'
  AND datetime(n.last_accessed) < datetime() - duration('P30D')
  ```
- **관련 파일:** `src/app/storage/reconciliation_service.py` (233, 356행)
- **관련 테스트:** TestReconciliationAPI 3건, TestReconciliationService 1건

---

## TS-002: LLMClient.create() silent failure [해결됨]

- **상태:** ✅ 해결 (커밋 54e01b7)
- **원인:** 클래스 메서드가 아닌 인스턴스 메서드를 클래스 호출
- **해결:** `LLMClient()` 인스턴스 생성 후 `.chat()` 호출
- **관련 파일:** `src/app/services/simulation_runner.py` 391행

---

## TS-003: current_app 미임포트 [미해결]

- **상태:** ⚠️ 미해결 (TestAuditAPI 2건 실패)
- **증상:** `NameError: name 'current_app' is not defined`
- **해결 방법:** `from flask import current_app` 추가
- **관련 파일:** `src/app/api/memory.py`, `_get_audit()` 함수

---

## TS-004: EmbeddingService 스레드 안전성 [해결됨]

- **상태:** ✅ 해결 (커밋 54e01b7)
- **해결:** `threading.Lock()` 추가, `with self._lock:` 보호
- **관련 파일:** `src/app/storage/embedding_service.py`

---

## TS-005: pandas 의존성 테스트 실패 [해결됨]

- **상태:** ✅ 해결 (커밋 8767f18)
- **해결:** CsvAdapter를 표준 라이브러리로 재작성
- **관련 파일:** `src/app/adapters/structured_adapters.py`

---

## TS-006: Admin 라우트 중복 등록 [해결됨]

- **상태:** ✅ 해결 (커밋 54e01b7)
- **해결:** 이중 데코레이터 제거
- **관련 파일:** `src/app/api/admin.py`

---

## TS-007: _is_ollama() 포트 의존 오탐 [해결됨]

- **상태:** ✅ 해결 (커밋 54e01b7)
- **해결:** `LLM_PROVIDER` 환경변수 우선, 포트 휴리스틱 폴백
- **관련 파일:** `src/app/utils/llm_client.py`

---

## TS-008: 파일 크기 과다로 인한 write_to_file 실패 [해결됨]

- **상태:** ✅ 해결
- **해결:** 파일 기능별 분리 (300줄 초과 시 분리 권장)

---

## TS-009: Nginx JS 캐시로 인한 변경 미반영 [해결됨]

- **상태:** ✅ 해결 (2026-04-01 세션)
- **증상:** `i18n.js`, `nav-component.js` 수정 후 브라우저에서 구 버전 로드
- **원인:** `.js` 파일에 `expires 7d; Cache-Control: public, immutable` 적용됨
- **해결:** `nginx.conf`에서 `.js` 파일 별도 no-cache 룰 추가
  ```nginx
  location ~* \.js$ {
      add_header Cache-Control "no-cache, no-store, must-revalidate";
      add_header Pragma "no-cache";
  }
  ```
- **관련 파일:** `dashboard/nginx.conf`
- **주의:** 프로덕션 전환 시 파일 버저닝(예: `i18n.js?v=2`) 도입 후 캐시 복원 필요

---

## TS-010: i18n 키 누락으로 "undefined" 표시 [해결됨]

- **상태:** ✅ 해결 (2026-04-01 세션)
- **증상:** 영어 전환 시 일부 UI 텍스트가 "undefined"로 표시
- **원인:** `i18n.js` 사전에 해당 키 미등록
- **해결:** 새 UI 요소 추가 시 반드시 `i18n.js`에 ko/en 키 쌍으로 등록
- **원칙:** 새 HTML 요소에는 반드시 `data-i18n` 속성 부여, 동적 JS에는 `window.t('키')` 사용

---

## TS-011: 사이드바 메뉴 리다이렉트 오류 [해결됨]

- **상태:** ✅ 해결 (2026-04-01 세션)
- **증상:** API Explorer, Guide 클릭 시 대시보드(/)로 리다이렉트
- **원인:** `nav-component.js`의 href와 `nginx.conf`의 `try_files` 분기 불일치
- **해결:** nginx에서 `.html` 확장자 매핑 적용 (`$uri.html` 추가)
- **관련 파일:** `dashboard/nginx.conf` (25행), `dashboard/nav-component.js` (NAV_GROUPS)

---

## 앞으로 이슈 발생 시 기록 양식

```markdown
## TS-NNN: 이슈 제목 [상태]

- **상태:** ⚠️ 미해결 / ✅ 해결됨 / 🔄 진행 중
- **증상:** (어떤 오류/현상이 나타났나)
- **원인:** (왜 발생했나)
- **해결 방법:** (어떻게 고쳤나)
- **관련 파일:** (파일명 및 라인 번호)
- **관련 테스트:** (실패/통과 테스트 이름)
```
