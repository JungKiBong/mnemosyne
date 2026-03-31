# Mories 핸드오버 — Part 3: 트러블슈팅 기록
# 문서 경로: docs/handover/HANDOVER_v1.0_part3_troubleshooting.md
# 버전: v1.0 | 작성일: 2026-03-31
# 용도: 반복 이슈 방지를 위한 발생 원인/해결책 누적 기록

---

## TS-001: Neo4j datetime() 호환성 오류 [미해결]

- **상태:** ⚠️ 미해결 (테스트 실패 유발)
- **증상:** `Neo4j ClientError: Invalid call signature for DateTimeFunction: Provided input was [Long(xxx)]`
- **원인:** `n.last_accessed` 등의 필드에 ISO 문자열 대신 Unix Long 또는 null이 들어있을 때 `datetime()` 함수 적용 시 실패
- **해결 방법:**
  ```cypher
  -- Cypher 쿼리에 정규식 체크 선행
  AND n.last_accessed IS NOT NULL
  AND n.last_accessed =~ '\\d{4}-\\d{2}-\\d{2}.*'
  AND datetime(n.last_accessed) < datetime() - duration('P30D')
  ```
- **관련 파일:** `src/app/storage/reconciliation_service.py` 233, 356번째 줄
- **관련 테스트:** `TestReconciliationAPI` 3건, `TestReconciliationService` 1건

---

## TS-002: LLMClient.create() silent failure [해결됨]

- **상태:** ✅ 해결됨 (커밋 54e01b7)
- **증상:** 시뮬레이션이 오류 없이 빈 결과 반환
- **원인:** `LLMClient.create()` 메서드 미존재 (클래스 메서드가 아닌 인스턴스 메서드)
- **해결:** `LLMClient()` 인스턴스 생성 후 `instance.chat()` 호출로 변경
- **관련 파일:** `src/app/services/simulation_runner.py` 391번째 줄

---

## TS-003: current_app 미임포트 [미해결]

- **상태:** ⚠️ 미해결 (TestAuditAPI 2건 실패)
- **증상:** `NameError: name 'current_app' is not defined`
- **원인:** Flask `current_app`을 임포트하지 않고 사용
- **해결 방법:** 해당 파일 상단에 `from flask import current_app` 추가
- **관련 파일:** `src/app/api/memory.py`, `_get_audit()` 함수

---

## TS-004: EmbeddingService 스레드 안전성 [해결됨]

- **상태:** ✅ 해결됨 (커밋 54e01b7)
- **증상:** 다중 요청 시 캐시 경쟁 조건(Race Condition) 가능성
- **원인:** 딕셔너리 캐시에 `threading.Lock` 없이 다중 스레드 접근
- **해결:** `threading.Lock()` 추가, `with self._lock:` 으로 캐시 접근 보호
- **관련 파일:** `src/app/storage/embedding_service.py`

---

## TS-005: pandas 의존성으로 테스트 실패 [해결됨]

- **상태:** ✅ 해결됨 (커밋 8767f18)
- **증상:** `test_structured_adapters.py` 3건 실패 (에어갭 환경에서 pandas 미설치)
- **해결:** `CsvAdapter`를 표준 라이브러리(`csv`, `statistics`)로 재작성
- **관련 파일:** `src/app/adapters/structured_adapters.py`

---

## TS-006: Admin 라우트 중복 등록 [해결됨]

- **상태:** ✅ 해결됨 (커밋 54e01b7)
- **증상:** Flask 시작 시 `/settings` 라우트 충돌 경고 출력
- **원인:** `admin.py`에서 `@bp.route('/settings')` 데코레이터가 GET/PUT 양쪽 모두에 중복 적용
- **해결:** 이중 데코레이터 제거 (GET에는 GET만, PUT에는 PUT만)
- **관련 파일:** `src/app/api/admin.py` 306-309, 336-339번째 줄

---

## TS-007: _is_ollama() 포트 의존 오탐 [해결됨]

- **상태:** ✅ 해결됨 (커밋 54e01b7)
- **증상:** vLLM을 올라마로 오인식하거나 그 반대 발생
- **원인:** `LLM_BASE_URL`의 포트 번호(11434)만으로 프로바이더를 판단하는 경직된 로직
- **해결:** `LLM_PROVIDER` 환경변수를 우선 확인, 없으면 포트 휴리스틱으로 폴백
- **관련 파일:** `src/app/utils/llm_client.py` 52-54번째 줄

---

## TS-008: 파일 크기 과다로 인한 write_to_file 실패

- **상태:** ✅ 해결됨 (이 문서 분리 방식으로)
- **증상:** `write_to_file` 도구 호출 시 대용량 파일 직렬화 실패
- **해결:** 파일을 기능별로 분리 작성 (`part1_overview.md`, `part2_phase_status.md`, `part3_troubleshooting.md`)
- **원칙:** 하나의 파일이 300줄 초과 시 분리 권장

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
