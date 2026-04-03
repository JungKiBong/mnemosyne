# Mories — 다음 세션 프롬프트
# 문서 경로: docs/handover/NEXT_SESSION_PROMPT_v2.md
# 버전: v2.1 | 갱신일: 2026-04-03

---

아래 프롬프트를 **새 대화창**에 그대로 붙여넣기하세요:

---

```
Mories 프로젝트 작업을 이어갑니다.

## 프로젝트 위치
/Users/jungkibong/Projects/tmp/mirofish-supermemory

## 핸드오버 문서 (반드시 먼저 읽어주세요)
다음 4개 파일을 순서대로 읽고 현재 상황을 파악해주세요:
1. docs/handover/HANDOVER_v2.0_part1_session_summary.md — 이전 세션 작업 요약
2. docs/handover/HANDOVER_v2.0_part2_status.md — 작업 현황 & 우선순위
3. docs/handover/HANDOVER_v2.0_part3_troubleshooting.md — 트러블슈팅 기록 (반복 이슈 방지, 꼭 참고할 것)
4. docs/handover/HANDOVER_v2.0_part4_technical.md — 기술 상세 & 아키텍처

## 이전 핸드오버 (v1.0, 레거시 참조용)
docs/handover/HANDOVER_v1.0_part1_overview.md — 프로젝트 원칙 & 코드 품질 표준

## 세션 시작 체크리스트
1. source .venv/bin/activate (파이썬은 반드시 가상환경 활성화 확인 후 실행)
2. git status && git log --oneline -5 (git 상태 확인)
3. docker ps --format '{{.Names}} {{.Status}}' | grep mirofish (서비스 확인)
4. python3 -m pytest tests/ -q --tb=no 2>/dev/null | tail -3 (테스트 현황)

## 작업할 내용
1. **GitHub Commit:** 이전 세션의 인지 기억(Cognitive) API 추가 및 MCP 연동 코드를 커밋합니다.
2. **테스트카드 Fix:** P0 버그 수정 내용은 반영되었으나 Pytest Fixture 스코핑 이슈(`test_reconciliation.py`) 때문에 테스트가 실패하고 있습니다. 이 테스트 바인딩 오류를 조치하여 통합 테스트를 100% Passed 상태로 만드세요.
3. **UI 고도화(Harness 시각화):** 
   - 하네스 프로세스 추출 결과, Harness 오케스트레이션 기억, 그리고 조건부 인지 지식(Conditional)들을 Mories 대시보드 UI를 통해 시각적으로 렌더링하고 편집할 수 있도록 화면 작업을 진행하세요.

## 필수 규칙 (항상 준수)

### 공용 자원 보호
- data/gitlab/ — 공용 GitLab 데이터, 절대 변경/삭제 금지
- docker-compose.yml — 다른 서비스와 공유, 신중히 수정
- .env 파일 — 실 비밀번호 포함, Git 커밋 절대 금지, 노출 금지
- 다른 프로젝트 컨테이너 (presenton, jupyterhub, livedvr 등) — 변경/중지 금지

### 코드 품질 & 안정성
- 예외처리: try/except 블록에 구체적인 예외 타입을 지정하고, 추적을 위한 로깅(`logger.error(exc_info=True)`)을 절대 빼먹지 마세요.
- 자원 관리: DB 세션 및 파일 등 자원 점유나 미반환으로 인한 오류(릭)를 철저히 예방하세요. (반드시 `with` 구문 사용)
- 로깅: `logger = logging.getLogger('mirofish.<모듈명>')` 사용 철저.
- 개발자 친화적: 개발자가 유지 관리가 쉽도록 주석은 한글로 최대한 쉽고 상세히 작성하세요. WHY(왜 이렇게 작성했나) 중심으로.
- 문서화: 필요하다면 별도의 설명문서를 작성하고, 해당 코드 주석에 `# 설명문서: docs/<경로>/<파일명> v<버전> 참조` 형태로 기입하세요.

### 파일 구조 및 컨텍스트
- 파일 크기: 하나의 파일이 너무 길어지지 않도록 주의하세요 (300줄 초과 시 분리 검토).
- 테스트 파일: 임시 테스트 코드는 `tests/temp/` 같은 곳에 별도로 저장해서 나중에 쉽게 지울 수 있도록 작성하세요.
- 트러블슈팅: 동일한 이슈가 반복 발생되지 않도록 트러블슈팅 문서(part3)를 꼭 관리하고 참고하세요.
- **컨텍스트 한계:** 작업 중 대화 컨텍스트가 길어지거나 너무 많은 코드를 작성해 품질 유실의 위험이 느껴질 경우, 지체 없이 "새로운 대화가 필요하다"고 저에게 알리고 새 세션을 요청하세요.
- 핸드오버 문서 갱신 시 반드시 버전 번호를 올려주세요 (v2.0 → v2.1 등)
```
