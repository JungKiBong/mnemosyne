# Mories 핸드오버 — Part 1: 프로젝트 개요 & 원칙
# 문서 경로: docs/handover/HANDOVER_v1.0_part1_overview.md
# 버전: v1.0 | 작성일: 2026-03-31

---

## 1. 프로젝트 개요

- **프로젝트명:** Mories — Multi-Agent Cognitive Memory Engine (Air-gap 특화)
- **저장소:** `/Users/jungkibong/Projects/tmp/mirofish-supermemory`
- **주 언어:** Python 3.13 (Flask), JavaScript, HTML/CSS
- **가상환경:** `.venv` (항상 활성화 필요)

### 가상환경 실행
```bash
cd /Users/jungkibong/Projects/tmp/mirofish-supermemory
source .venv/bin/activate
python3 --version  # 3.13.x 확인
```

### 서비스 실행
```bash
# 개발 서버
source .venv/bin/activate
python3 -m flask --app "src/app:create_app()" run --port 5000

# Docker (개발)
docker compose up -d

# Docker (프로덕션, 에어갭)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 2. 에어갭(Air-gap) 원칙 (변경 금지)

- 외부 클라우드 API(OpenAI, Anthropic 등) 직접 호출 **절대 금지**
- LLM/Embedding은 에어갭 내 **별도 추론 서버(Ollama/vLLM)** 를 통해서만 접근
- 환경변수로 교체 가능: `LLM_PROVIDER=ollama|openai|vllm`

---

## 3. 공용 자원 보호 (절대 수정 금지)

| 자원 | 경로 | 비고 |
|------|------|------|
| GitLab 데이터 | `data/gitlab/` | 공용 서비스, 절대 변경 금지 |
| 공용 docker-compose | 루트 `docker-compose.yml` | 다른 서비스와 공유됨 |
| `.env` 파일 | 프로젝트 루트 | 실 비밀번호 포함, Git 커밋 금지 |
| Neo4j 암호 | `NEO4J_PASSWORD=mirofish` | 하드코딩 금지, `.env.example` 참조 |
| API 키 | `MCP_API_KEY`, `SUPERMEMORY_API_KEY` | 환경변수로만 관리 |

> `data/` 디렉터리는 `.gitignore` 등록됨. 절대 커밋 금지.

---

## 4. 코드 품질 표준

### 예외처리 패턴
```python
try:
    result = some_operation()
except Neo4jError as e:
    # Neo4j 오류: 503으로 변환하여 반환
    logger.error(f"Neo4j 조회 실패 — 원인: {e}", exc_info=True)
    return {"error": "데이터베이스 오류", "detail": str(e)}, 503
except Exception as e:
    # 예상 밖 오류: 스택 추적 포함 상위 전파
    logger.critical(f"예상치 못한 오류: {e}", exc_info=True)
    raise
```

### 자원 반환 (DB 세션 반드시 with 블록)
```python
with driver.session() as session:   # 예외 시에도 자동 해제
    result = session.run(query)
```

### 주석 작성
- 한글로 작성 (유지보수 개발자 기준)
- WHY(왜 필요한가)를 설명
- 별도 문서 참조 시: `# 설명: docs/architecture/WEBHOOK.md v1.0 참조`

### 로깅 표준
```python
logger = logging.getLogger('mirofish.<모듈명>')
logger.info(f"작업 시작: {param}")      # 정상 흐름
logger.warning(f"예상 외 상황: {msg}")  # 조사 필요
logger.error(f"오류", exc_info=True)    # 스택 추적 포함
```

### 테스트 파일 위치
- 단위: `tests/unit/test_*.py`
- E2E: `tests/e2e/test_*.py`
- 통합: `tests/integration/test_*.py`
- **임시(나중에 삭제 가능):** `tests/temp/`
- 공유 데이터: `tests/fixtures/`

---

## 5. 주요 파일 맵

```
mirofish-supermemory/
├── src/app/
│   ├── api/          # Flask 라우트 (memory.py, core.py, admin.py...)
│   ├── storage/      # Neo4j 스토리지 (memory_manager.py, reconciliation_service.py...)
│   ├── services/     # 비즈니스 로직 (simulation_runner.py, ontology_generator.py...)
│   ├── adapters/     # 파일 인제스천 어댑터 (pandas 의존성 제거 완료)
│   ├── utils/        # 공통 유틸 (webhook.py 신규, llm_client.py, retry.py...)
│   ├── security/     # 암호화 (memory_encryption.py)
│   └── config.py     # 환경변수 중앙 관리
├── mcp_server/       # MCP 프로토콜 서버 (server.py, tools.py, config.py...)
├── dashboard/        # 프론트엔드 HTML/JS/CSS
├── tests/
│   ├── e2e/
│   ├── unit/
│   ├── integration/
│   └── temp/         # 임시 테스트 (안전하게 삭제 가능)
├── docs/handover/    # 핸드오버 문서 (이 파일 위치)
├── .env.example      # 환경변수 템플릿
├── docker-compose.yml
└── docker-compose.prod.yml  # 프로덕션 오버라이드 (신규)
```

---

## 6. 환경변수 요약

```bash
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=mirofish          # 하드코딩 금지

LLM_PROVIDER=ollama              # ollama | openai | vllm
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL_NAME=qwen2.5:32b
LLM_API_KEY=ollama               # Ollama는 더미값

EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://host.docker.internal:11434
EMBEDDING_MODEL=nomic-embed-text

WEBHOOK_ENABLED=false
WEBHOOK_URL=                     # 쉼표 구분 다중 URL
WEBHOOK_SECRET=                  # HMAC-SHA256 서명 키
MCP_API_KEY=
```

---

## 7. 새 세션 시작 체크리스트

```
[ ] source .venv/bin/activate
[ ] python3 -m pytest tests/ -q --tb=no  (테스트 현황 확인)
[ ] git status && git log --oneline -5   (git 상태 확인)
[ ] data/gitlab/ 건드리지 않았는지 확인
[ ] .env 파일 존재 확인 (없으면 .env.example 복사)
```
