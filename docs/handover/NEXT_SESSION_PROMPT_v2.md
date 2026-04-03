# Mories — 다음 세션 프롬프트
# 문서 경로: docs/handover/NEXT_SESSION_PROMPT_v2.md
# 버전: v2.0 | 갱신일: 2026-04-02

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
3. docs/handover/HANDOVER_v2.0_part3_troubleshooting.md — 트러블슈팅 기록 (반복 이슈 방지)
4. docs/handover/HANDOVER_v2.0_part4_technical.md — 기술 상세 & 아키텍처

## 이전 핸드오버 (v1.0, 레거시 참조용)
docs/handover/HANDOVER_v1.0_part1_overview.md — 프로젝트 원칙 & 코드 품질 표준

## 세션 시작 체크리스트
1. source .venv/bin/activate (파이썬은 반드시 가상환경에서 실행)
2. git status && git log --oneline -5 (git 상태 확인)
3. docker ps --format '{{.Names}} {{.Status}}' | grep mirofish (서비스 확인)
4. python3 -m pytest tests/ -q --tb=no 2>/dev/null | tail -3 (테스트 현황)

## 작업할 내용
[여기에 구체적인 작업 내용을 입력하세요]

## 필수 규칙 (항상 준수)

### 공용 자원 보호
- data/gitlab/ — 공용 GitLab 데이터, 절대 변경/삭제 금지
- docker-compose.yml — 다른 서비스와 공유, 신중히 수정
- .env 파일 — 실 비밀번호 포함, Git 커밋 절대 금지
- 다른 프로젝트 컨테이너 (presenton, jupyterhub, livedvr 등) — 변경/중지 금지

### 코드 품질
- 예외처리: try/except 블록에 구체적 예외 타입 사용, logger.error(exc_info=True) 필수
- 자원 반환: DB 세션은 반드시 `with` 블록으로 감싸서 자동 해제
- 로깅: `logger = logging.getLogger('mirofish.<모듈명>')`, 한글 메시지 권장
- 주석: 한글로 최대한 쉽고 상세히 작성, WHY(왜 필요한가) 중심
- 별도 설명 문서 필요 시: 문서 작성 후 코드 주석에 `# 설명: docs/<경로>/<파일명> v<버전> 참조` 기입

### 테스트 파일 관리
- 임시 테스트는 tests/temp/ 디렉터리에 저장 (나중에 쉽게 일괄 삭제 가능)
- 정식 테스트는 tests/unit/, tests/e2e/, tests/integration/ 에 배치

### 파일 크기
- 하나의 파일이 300줄을 초과하면 분리 검토
- 핸드오버 문서도 part 단위로 분리 유지

### 트러블슈팅 관리
- 새 이슈 발생 시 docs/handover/HANDOVER_v2.0_part3_troubleshooting.md에 TS-NNN 양식으로 추가
- 해결된 이슈도 삭제하지 말고 상태만 [해결됨]으로 변경 (히스토리 보존)

### 컨텍스트 관리
- 작업 중 대화 컨텍스트가 길어져서 품질 저하가 느껴지면, 즉시 알려주세요.
  핸드오버 문서를 갱신한 후 새로운 대화창에서 작업을 이어가겠습니다.
- 핸드오버 문서 갱신 시 반드시 버전 번호를 올려주세요 (v2.0 → v2.1 등)
```
