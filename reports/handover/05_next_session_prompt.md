# 다음 세션 프롬프트 (v1.0)

> 아래 전체를 새 대화창에 붙여넣기하세요.

---

```
## 프로젝트: Mories (사내 에이전틱 메모리 엔진)

프로젝트 경로: /Users/jungkibong/Projects/tmp/mirofish-supermemory
핸드오버 문서: reports/handover/ (4개 파일)

### 이전 세션에서 완료된 작업
- Step 1.1: exec() 보안 취약점 → AST 기반 검증으로 교체 완료
- Step 1.2: 하드코딩 IP 제거, CORS 화이트리스트, SECRET_KEY 강제 설정 완료
- 핵심 테스트 24개 통과 확인 (test_executor_registry 14 + test_ray_security 2 + test_dsl_schema 8)

### 지금 해야 할 작업
- **Step 1.3: OASIS 시뮬레이션 코드를 plugins/ 디렉토리로 분리**
  → 상세 가이드: reports/handover/04_step1_3_guide.md 참조
- Step 1.4: Redis STM 백엔드 구현 (Step 1.3 이후)

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
- MCP 서버: mcp_server/
- 대시보드: dashboard/
- 인프라 스크립트: scripts/ (플래닛 Nomad/Ray 관련)

### 커밋 상태
아직 변경사항이 커밋되지 않았습니다. 작업 진행 전 커밋 여부를 검토해주세요.
git diff --stat HEAD 으로 확인 가능합니다.
```

---

> 참고: 이 프롬프트는 reports/handover/05_next_session_prompt.md에도 저장되어 있습니다.
