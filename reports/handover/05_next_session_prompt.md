# 다음 세션 프롬프트 (v2.0)

> 아래 전체를 새 대화창에 붙여넣기하세요.

---

```
## 프로젝트: Mories (사내 에이전틱 메모리 엔진)

프로젝트 경로: /Users/jungkibong/Projects/tmp/mirofish-supermemory
핸드오버 문서: reports/handover/ (5개 파일)

### 이전 세션에서 완료된 작업 (Step 1~3 전체 완료)

**Step 1: 보안 강화 & 경량화**
- 1.1: exec() 보안 취약점 → AST 기반 검증으로 교체 완료
- 1.2: 하드코딩 IP 제거, CORS 화이트리스트, SECRET_KEY 강제 설정 완료
- 1.3: OASIS 시뮬레이션 코드 → plugins/ 디렉토리 분리 완료
- 1.4: Redis STM 백엔드 구현 (InMemory fallback 포함)

**Step 2: 사내 인프라 통합**
- 2.1: Keycloak SSO 연동 (auth.py + /api/auth/me)
- 2.2: Ollama/vLLM 내부망 검증 (verify_internal_llm.py)
- 2.3: API v1 블루프린트 도입 (/api/v1/info)

**Step 3: SDK 패키징 & 파일럿**
- 3.1: Python SDK (mories_sdk/) 패키징 완료
- 3.2: LangChain MoriesRetriever 구현 완료
- 3.3: 온보딩 예제 (onboarding.py) 작성 완료

**코드 리뷰 수정사항 (GAP 분석 결과)**
- Redis KEYS 안티패턴 → SCAN 이터레이터로 교체
- 메타데이터 직렬화 str() → json.dumps() 수정
- PyJWT/langchain-core lazy import + fallback stub 적용
- .env.example에 KEYCLOAK/REDIS/CORS 변수 추가
- GUIDE.md에 Keycloak SSO + Redis STM + SDK 섹션 추가
- API Explorer에 /api/auth/me, /api/v1/info 등록

핵심 테스트 73개 통과 확인:
  - test_executor_registry: 14 passed
  - test_ray_security: 2 passed
  - test_dsl_schema: 8 passed
  - test_cognitive_memory: 49 passed

### 지금 해야 할 작업 (P1~P2 잔존 기술 부채)

1. **P1: API v1 마이그레이션** — 기존 /api/search, /api/memory/* 엔드포인트를 /api/v1 블루프린트로 이전
2. **P1: Keycloak 인증 범위 확대** — 현재 /api/auth/me에만 적용된 @require_auth를 주요 API로 확대
3. **P1: MemoryManager 리팩토링** — Redis/Neo4j 백엔드 분기를 ABC 기반 전략 패턴으로 변환
4. **P2: SDK 단위 테스트** — mories_sdk/tests/ 디렉토리에 MoriesClient, MoriesRetriever 테스트 추가
5. **P2: API 에러 응답 표준화** — 일관된 에러 포맷 (error_code, message, details)

### 필수 규칙 (모든 작업에 적용)

1. **가상환경 필수**: `.venv/bin/python`, `.venv/bin/pytest` 사용. bare `python` 금지
2. **테스트 기준선**: 작업 전후 반드시 아래 커맨드로 핵심 테스트 통과 확인
   ```
   .venv/bin/pytest tests/harness/test_executor_registry.py tests/harness/test_ray_security.py tests/harness/test_dsl_schema.py -v
   ```
3. **건드리면 안 되는 것들**:
   - `.env`, `src/.env` 파일 내용 출력/노출 금지 (비밀번호 포함)
   - `docker-compose.yml` 무단 수정 금지 (다른 프로젝트 공용 자원)
   - Neo4j 전체 삭제 쿼리 금지
   - 시스템 글로벌 패키지 설치 금지
4. **테스트 파일 관리**: `tests/harness/` 또는 `tests/tmp/`에 배치하여 나중에 한번에 정리 가능하도록
5. **코드 작성 시**:
   - 예외처리와 추적을 위한 로깅(logging) 반드시 포함
   - 자원(DB 커넥션, 파일 핸들) 점유 후 반드시 반환 (with문 사용)
   - 주석은 한글로 최대한 쉽고 상세하게 작성
   - 복잡한 로직은 docs/ 폴더에 별도 설명문서를 만들고, 소스 주석에 문서 경로/이름/버전 기입
   - 단일 파일 300줄 이하 목표
6. **트러블슈팅 참고**: reports/handover/02_troubleshooting.md — 특히 TS-001(pytest 행 현상), TS-003(가상환경 혼동) 주의
7. **컨텍스트 관리**: 작업 중 컨텍스트가 길어져서 품질이 저하된다고 판단되면, 즉시 알려주세요. 핸드오버 문서를 업데이트하고 새 대화에서 이어갑니다
8. **코딩 컨벤션**: reports/handover/03_coding_conventions.md 참조

### 프로젝트 아키텍처 요약
- Flask 앱 팩토리: src/app/__init__.py
- 핵심 설정: src/app/config.py
- 메모리 엔진: src/app/storage/ (memory_manager, search_service, embedding_service)
- 하네스 실행기: src/app/harness/executors/ (ray, nomad, wasm, container, hitl)
- 인증: src/app/utils/auth.py (Keycloak JWT 검증)
- SDK: mories_sdk/ (MoriesClient + LangChain MoriesRetriever)
- API v1: src/app/api/v1.py
- MCP 서버: mcp_server/
- 대시보드: dashboard/
- 인프라 스크립트: scripts/ (플래닛 Nomad/Ray 관련)

### 커밋 상태
많은 변경사항이 커밋되지 않았습니다. 작업 진행 전 커밋 여부를 검토해주세요.
git diff --stat HEAD 으로 확인 가능합니다.
```

---

> 참고: 이 프롬프트는 reports/handover/05_next_session_prompt.md에도 저장되어 있습니다.
