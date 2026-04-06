# 📖 Mories 운영 가이드

> 시스템 운영, 관리, 트러블슈팅을 위한 실무 가이드

## 1. 시스템 요구사항

| 구성 요소 | 최소 사양 | 권장 사양 |
| --- | --- | --- |
| Python | 3.12+ | 3.13+ |
| Neo4j | 5.x | 5.x (Docker) |
| RAM | 4GB | 8GB+ |
| Disk | 2GB | 10GB+ |
| Ollama (선택) | — | llama3.1, nomic-embed-text |

---

## 2. 설치 및 실행

### 2.1 기본 설치
```bash
# 1. 프로젝트 클론
git clone https://github.com/JungKiBong/mories.git
cd mories

# 2. 환경 변수 설정
cp .env.example .env
nano .env  # NEO4J_PASSWORD 등 수정

# 3. Neo4j 시작
docker-compose -f docker-compose.mac.yml up -d neo4j

# 4. Python 환경 구성
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt

# 5. 서버 실행
cd src
FLASK_APP=app FLASK_DEBUG=0 flask run --host=0.0.0.0 --port=5050
```

### 2.2 Docker 전체 스택
```bash
docker-compose up -d --build
# API: localhost:5050, Neo4j: localhost:7474, Dashboard: localhost:5050/dashboard
```

### 2.3 백업 및 복원 (Backup & Restore)
Docker 환경에서 Neo4j 데이터를 안전하게 백업 및 복원하는 절차입니다.
```bash
# 백업 (Dump)
docker exec -it mirofish-neo4j neo4j-admin database dump system --to-path=/backups
docker exec -it mirofish-neo4j neo4j-admin database dump neo4j --to-path=/backups

# 호스트 서버로 백업 파일 복사
docker cp mirofish-neo4j:/backups/neo4j.dump ./neo4j_backup.dump

# 복원 시 (컨테이너 정지 상태에서 마운트된 볼륨에 로드하거나 빈 DB에 로드)
docker exec -it mirofish-neo4j neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
```

---

## 3. 인지 메모리 엔진 이해

### 3.1 시작부터 활용까지의 전체 흐름 (End-to-End Scenario)
데이터가 수집되고 에이전트가 이를 활용하기까지의 사이클입니다:
1. **수집 (Ingestion):** 외부 도구(n8n, 웹훅)에서 수집된 정보가 Gateway API (`POST /api/gateway/webhook`)를 통해 들어옵니다.
2. **단기 기억 (STM):** 데이터는 먼저 STM(단기 기억 버퍼)에 24시간(`stm_ttl`) 동안 머무릅니다.
3. **평가 (Evaluation):** 감정 분석기나 리뷰어가 해당 단기 기억에 `salience`(중요도, 0~1.0)를 부여합니다.
4. **장기 기억 (LTM):** 만약 `salience`가 0.3 이상이라면 LTM으로 영구 보관(Promote)됩니다.
5. **활용 (Retrieval):** AI 에이전트가 `memory_search` MCP 도구로 질문(예: "아키텍처 결정 사항이 뭐야?")을 던지면, 관련된 LTM 지식을 반환하며 해당 기억의 접근수(access count)와 salience가 일시적으로 스파이크(Boost)됩니다.
6. **감쇠 (Decay):** 시간이 지남에 따라 쓰이지 않는 기억의 salience는 매일 5%씩 서서히 낮아집니다.

### 3.2 핵심 개념

| 개념 | 설명 | 파라미터 |
| --- | --- | --- |
| **Salience** | 기억의 중요도 (0.0 ~ 1.0) | 초기값은 평가에 의해 결정 |
| **Decay Rate** | 일일 감쇠율 | 기본: 0.95 (매일 5% 감소) |
| **Boost Amount** | 검색 시 강화량 | 기본: +0.15 |
| **STM TTL** | 단기기억 유효시간 | 기본: 86,400초 (24시간) |
| **Promote Threshold** | LTM 승격 기준 | salience ≥ 0.3 |

### 3.3 기억 범위 (Scope) 및 성숙도 (Maturity)
* **Scope:** `Personal(개인) → Tribal(팀) → Social(조직) → Universal(전체)` (승격은 단방향, salience > 0.7 조건)
* **Maturity:** `Draft → Reviewed → Validated → Certified → Archived`

---

## 4. 대시보드 사용법

| 페이지 | URL | 설명 |
| --- | --- | --- |
| 시스템 개요 | `/dashboard` | 전체 시스템 상태 |
| 메모리 관리 | `/memory` | STM/LTM, Decay, Boost, Scope, 설정 |
| 감사 이력 | `/memory_history` | 전체 변경 이력 + 롤백 |
| 시냅틱 네트워크 | `/synaptic` | 에이전트 간 연결 시각화 |

*대시보드 소스코드는 `/dashboard/` 폴더 내에 있으며, Nginx를 통해 정적 파일 배포로 제공됩니다. 수정 사항은 브라우저 캐시 무효화를 위해 스크립트의 `?v=` 태그를 올려 반영할 수 있습니다.*

---

## 5. MCP 서버 연동 및 에이전트 명세

Mories는 AI 에이전트를 위한 MCP(Model Context Protocol) 서버를 내장하고 있습니다. 에이전트 개발자는 아래 도구 명세(JSON-RPC 형태)를 참고하여 통합할 수 있습니다.

### 5.1 `memory_search` (기억 검색)
의미 기반(또는 키워드)으로 장기 기억(LTM)을 검색합니다.
* **입력 파라미터**: `query` (string, 필수) - 검색할 내용, `limit` (int, 선택, 기본 5) - 결과 반환 개수
* **사용 예시**: `{"method": "memory_search", "params": {"query": "사용자 인증 로직의 문제점"}}`

### 5.2 `memory_store` (기억 저장)
에이전트가 새로운 지식을 단기 기억(STM)에 저장합니다.
* **입력 파라미터**: `content` (string, 필수) - 보관할 지식, `metadata` (object, 선택) - 기타 태그 정보
* **사용 예시**: `{"method": "memory_store", "params": {"content": "오류 코드는 ERR_102입니다."}}`

### 5.3 `memory_boost` (강화)
특정 기억의 salience(중요도 점수)를 즉시 증가시킵니다.
* **입력 파라미터**: `memory_id` (string, 필수) - 기억 UUID, `reason` (string, 선택) - 강화 사유

### 5.4 REST MCP Proxy
직접 웹훅으로 호출하는 경우:
```bash
curl -X POST http://localhost:5050/api/mcp \
  -H "Content-Type: application/json" \
  -d '{"method": "memory_search", "params": {"query": "architecture"}}'
```

---

## 6. 보안 설정

### 6.1 RBAC (역할 기반 접근 제어)
```bash
# 접근 권한 검사
curl -X POST http://localhost:5050/api/security/check \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "agent-1", "resource": "memory-uuid", "action": "read"}'
```

### 6.2 필드 암호화 (AES-256)
```bash
# 특정 기억의 필드 암호화
curl -X POST http://localhost:5050/api/security/encrypt \
  -H "Content-Type: application/json" \
  -d '{"uuid": "<memory-uuid>", "fields": ["content"]}'
```

---

## 7. 정합성 관리 & 트러블슈팅

### 7.1 데이터 정합성 (Reconciliation)
데이터 스키마 불일치 또는 30일 이상 미갱신 등을 검출합니다.
```bash
# 검사 및 자동수정
curl -X POST http://localhost:5050/api/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{"auto_fix": true}'
```

### 7.2 트러블슈팅 (Neo4j 및 감쇠)
* **Neo4j 연결 실패**: `docker logs mirofish-neo4j`를 통해 컨테이너 시동 확인 및 `.env` 파일의 `NEO4J_URI` 점검.
* **감쇠(Decay) 스케줄러 미작동**: `curl http://localhost:5050/api/health` 호출 시 `"scheduler": "running"` 확인. 작동 중지 상태라면 수동 트리거로 복구 가능: `curl -X POST http://localhost:5050/api/v1/memory/decay -d '{"dry_run": false}'`.

---
*Last updated: 2026-04-01*
