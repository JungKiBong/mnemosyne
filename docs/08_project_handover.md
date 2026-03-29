# Mories (MiroFish × Supermemory) - Project Handover

## 1. 프로젝트 현재 상태 (Current Status)
- **목표 달성**: Mories의 통합 대시보드 포털 구축 및 백엔드(Neo4j) 연결 안정화 완료.
- **주요 구현 사항**:
  - `nginx.conf`를 통한 각 단일 페이지(Dashboard, Graph, Memory, Maturity, Audit, Workflows, Synaptic)간 전역 네비게이션 적용 및 정적 캐싱(`no-cache`) 문제 해결.
  - `mirofish-api` 컨테이너의 `mcp_server` 패키지 누락 문제를 해결하기 위해 `docker-compose.yml`에 볼륨 바인딩(`./mcp_server:/mcp_server`) 추가.
  - Neo4j 연결 시 로컬의 `.env` 파일이 도커 환경 변수를 덮어쓰는 문제(override) 해결.
  - Graph Explorer(`graph.html`) 뷰어 내 DOM 요소(`loading`) 참조 에러 및 `TypeError` 예방을 위한 방어 코드 추가.
  - 위의 트러블슈팅 이력을 `docs/07_troubleshooting_and_deployment.md`에 문서화하고, Neo4j Mories Memory DB에도 Ingestion 완료.
  - **n8n 워크플로우 실행 현황 모니터링 연동 완료**: `api/gateway.py`에 Neo4j 기반 ExecutionLog 저장 구현 및 `workflows.html` 대시보드 API 연동을 통한 실시간 로깅 시각화.

## 2. 개발 및 코딩 가이드라인 (Coding Guidelines)
다음 세션의 에이전트는 아래 규칙을 **엄격히 준수**하여 작업을 진행해야 합니다.

1. **파일 모듈화 (단일 파일 크기 제한)**:
   - 하나의 파일이 비대해지지 않도록 기능별로 코드를 분리(Refactoring)할 것.
   - 단일 클래스나 함수가 너무 많은 책임을 갖지 않도록 원칙 유지.
2. **보안 및 공용 자원 관리 지침 유지**:
   - `docker-compose.yml` 등 공토 파일 수정 시 타 서비스 설정 훼손 금지.
   - API 키, 비밀번호(Neo4j 등), 토큰 등은 코드에 하드코딩하지 않고 환경변수(`os.getenv`)를 통해 참조할 것.
3. **가상 환경(Virtual Env) 강제**:
   - Python 패키지 설치 및 스크립트 실행은 반드시 `source .venv/bin/activate` 후 수행할 것.
4. **테스트 파일 관리 격리**:
   - 일회성 테스트 스크립트 및 더미 데이터는 프로젝트 최상단이나 운영 디렉토리가 아닌 `tests/temp/` 등의 격리된 폴더에 저장하여 검증 후 쉽게 삭제(Clean-up)할 수 있게 할 것.
5. **예외 처리 및 자원 반환 (Robustness)**:
   - 데이터베이스 커넥션, 파일 쓰기, 네트워크 소켓 등 자원은 반드시 `try-finally` 블록 혹은 컨텍스트 매니저(`with`)를 통해 안전하게 반환(close)할 것.
   - 모든 에러는 묵살(`pass`)하지 않고, 원인 추적을 위해 명확한 `logger` 패키지로 에러 로그를 남길 것.
6. **트러블슈팅 및 반복 이슈 관리**:
   - 동일한 버그 반복을 피하기 위해, 개발 전 `docs/07_troubleshooting_and_deployment.md` 및 Mories Graph DB의 기억들을 먼저 검색하여 기존 이슈 해결 패턴을 참고할 것.
7. **컨텍스트 길이 모니터링 경고**:
   - AI 에이전트는 대화 트리가 지나치게 길어져 맥락이 희미해지기 전, 사용자에게 능동적으로 "새로운 대화 세션 생성"을 제안하고 그 시점까지의 핸드오버와 기억을 정리해야 함.

## 3. 남아있는 백로그 및 다음 단계 (Next Steps)
- Graph Viewer 상의 대규모 노드 군집화(Clustering) 및 시맨틱 필터기 도입.
- 만료 임박 API 키/토큰 갱신 관리자 전용 UI 패널 설계 및 연동.
