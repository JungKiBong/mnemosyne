# 🔧 트러블슈팅 이력 (Troubleshooting Log)
**프로젝트:** mirofish-supermemory  
**최종 업데이트:** 2026-04-04

> 동일한 이슈 재발 방지를 위해 에러 수정 과정 및 원인을 누적 기록합니다.

---

## TS-001: Neo4j 연결 인증 실패
- **날짜:** 2026-03-28
- **증상:** `AuthError: The client is unauthorized due to authentication failure`
- **원인:** `.env` 파일의 `NEO4J_PASSWORD`가 실제 Neo4j 컨테이너와 불일치 
- **해결:** `.env`에 `NEO4J_PASSWORD=mirofish` 설정 → 컨테이너 재시작
- **예방:** Neo4j credentials는 `.env`에서만 관리, 코드에 하드코딩 금지

## TS-002: Pytest Fixture 바인딩 에러
- **날짜:** 2026-04-02~03
- **증상:** `fixture 'neo4j_session' not found` 에러로 통합 테스트 전부 실패
- **원인:** `conftest.py`에 테스트용 Neo4j fixture가 누락되어 있었음
- **해결:** `tests/conftest.py`에 `neo4j_session`, `neo4j_driver` fixture 추가 + skip 데코레이터 적용
- **예방:** 통합 테스트에는 반드시 `@pytest.mark.skipif(not _available)` 패턴 적용

## TS-003: Neo4j datetime 호환성 문제
- **날짜:** 2026-03-30
- **증상:** `datetime.datetime` 객체를 Neo4j에 직접 전달 시 타입 에러
- **원인:** Neo4j Python driver는 `neo4j.time.DateTime`만 직접 지원
- **해결:** `.isoformat()` 문자열로 변환하여 저장 → 조회 시 파싱
- **예방:** Neo4j에 시간 저장 시 항상 ISO-8601 문자열 사용

## TS-004: LLM Healer JSON 파싱 실패
- **날짜:** 2026-04-04
- **증상:** Ollama 응답에 마크다운 코드블록이 포함되어 JSON 파싱 실패
- **원인:** LLM이 `\`\`\`json ... \`\`\`` 래핑을 붙여서 응답
- **해결:** 3단계 파서 구현 (직접 파싱 → 코드블록 추출 → brace 매칭)
- **예방:** LLM 응답 파싱 시 항상 multi-fallback 패턴 적용

## TS-005: 테스트 데이터 오염
- **날짜:** 2026-04-04
- **증상:** E2E 테스트 데이터가 프로덕션 그래프에 잔존
- **원인:** teardown에서 테스트 네임스페이스 정리 로직 누락
- **해결:** `TEST_DOMAIN = f"test_e2e_{uuid}"` + `teardown_class`에서 `DETACH DELETE`
- **예방:** E2E 테스트는 반드시 고유 네임스페이스 + teardown 정리

## TS-006: 가상환경 미사용으로 패키지 충돌
- **날짜:** 2026-03-28
- **증상:** 시스템 Python에서 실행 시 `neo4j` 패키지 버전 불일치
- **원인:** 시스템 글로벌 Python 사용
- **해결:** `.venv/bin/python3` 명시적 사용
- **예방:** 모든 명령은 `.venv` 경로 확인 후 실행

---

## 주의 패턴 (발생 가능성 높은 이슈)

| 패턴 | 예방 조치 |
|------|-----------|
| Docker 컨테이너 미시작 | 테스트 전 `docker ps` 확인 |
| 포트 충돌 (7687, 11434) | `lsof -i :PORT` 사전 체크 |
| LLM 타임아웃 | `timeout` 파라미터 충분히 설정 (기본 60s) |
| 대용량 응답 OOM | LLM 응답 `max_tokens` 제한 (4096) |
| SQLite 동시 접근 | `check_same_thread=False` + WAL 모드 |
