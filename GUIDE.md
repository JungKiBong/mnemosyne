# 📖 Mnemosyne 운영 가이드

> 시스템 운영, 관리, 트러블슈팅을 위한 실무 가이드

---

## 목차

1. [시스템 요구사항](#1-시스템-요구사항)
2. [설치 및 실행](#2-설치-및-실행)
3. [인지 메모리 엔진 이해](#3-인지-메모리-엔진-이해)
4. [대시보드 사용법](#4-대시보드-사용법)
5. [API 활용 가이드](#5-api-활용-가이드)
6. [MCP 서버 연동](#6-mcp-서버-연동)
7. [n8n / 외부 시스템 연동](#7-n8n--외부-시스템-연동)
8. [보안 설정](#8-보안-설정)
9. [데이터 정합성 관리](#9-데이터-정합성-관리)
10. [트러블슈팅](#10-트러블슈팅)

---

## 1. 시스템 요구사항

| 구성 요소 | 최소 사양 | 권장 사양 |
|-----------|----------|----------|
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
git clone https://github.com/JungKiBong/mnemosyne.git
cd mnemosyne

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
docker-compose up -d
# API: localhost:5050, Neo4j: localhost:7474, Dashboard: localhost:5050/dashboard
```

### 2.3 테스트 실행

```bash
# 프로젝트 루트에서
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_resilience.py tests/integration/ tests/e2e/ -v
# 결과: 58 passed ✅
```

---

## 3. 인지 메모리 엔진 이해

### 3.1 기억의 생명주기

```
[데이터 수집]  →  [STM 버퍼]  →  [평가]  →  [LTM 저장]  →  [감쇠/강화]  →  [아카이브/소멸]
                    ↑                           ↓
              salience < 0.3 → 폐기    salience × 0.95/day (Ebbinghaus)
                                        검색 시 +0.15 강화 (Retrieval Boost)
```

### 3.2 핵심 개념

| 개념 | 설명 | 파라미터 |
|------|------|---------|
| **Salience** | 기억의 중요도 (0.0 ~ 1.0) | 초기값은 평가에 의해 결정 |
| **Decay Rate** | 일일 감쇠율 | 기본: 0.95 (매일 5% 감소) |
| **Boost Amount** | 검색 시 강화량 | 기본: +0.15 |
| **STM TTL** | 단기기억 유효시간 | 기본: 86,400초 (24시간) |
| **Promote Threshold** | LTM 승격 기준 | salience ≥ 0.3 |

### 3.3 기억 범위 (Scope)

```
Personal (개인) → Tribal (팀) → Social (조직) → Universal (전체)
```

- 승격 조건: `salience > 0.7` AND `access_count >= 5`
- 승격은 단방향 (강등 불가)
- 각 범위에 따라 접근 가능 에이전트가 달라짐

### 3.4 지식 성숙도 (Maturity)

```
Draft → Reviewed → Validated → Certified → Archived
```

- 자동 승격 규칙 기반 (access_count, salience, 기간)
- API: `/api/maturity/check-promotions`

---

## 4. 대시보드 사용법

### 4.1 접속 URL

| 페이지 | URL | 설명 |
|--------|-----|------|
| 시스템 개요 | `/dashboard` | 전체 시스템 상태 |
| 메모리 관리 | `/memory` | STM/LTM, Decay, Boost, Scope, 설정 |
| 감사 이력 | `/memory/history` | 전체 변경 이력 + 롤백 |
| 시냅틱 네트워크 | `/memory/synaptic` | 에이전트 간 연결 시각화 |

### 4.2 주요 기능

- **Overview 탭**: 총 기억 수, 활성 STM, 평균 salience, health score
- **STM 탭**: 현재 STM 버퍼 내용, 평가/승격/폐기 액션
- **LTM 탭**: 장기기억 목록, salience 그래프, 검색
- **Settings 탭**: decay_rate, boost_amount, stm_ttl 실시간 조정

---

## 5. API 활용 가이드

### 5.1 기억 저장 (STM → LTM)

```bash
# 1. STM에 추가
curl -X POST http://localhost:5050/api/memory/stm/add \
  -H "Content-Type: application/json" \
  -d '{"content": "프로젝트 X의 아키텍처 결정", "source": "meeting"}'

# 2. 평가 (salience 부여)
curl -X POST http://localhost:5050/api/memory/stm/evaluate \
  -H "Content-Type: application/json" \
  -d '{"id": "<stm-uuid>", "salience": 0.8}'

# 3. LTM으로 승격
curl -X POST http://localhost:5050/api/memory/stm/promote \
  -H "Content-Type: application/json" \
  -d '{"id": "<stm-uuid>"}'
```

### 5.2 기억 검색

```bash
curl -X POST http://localhost:5050/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "아키텍처 결정", "limit": 10}'
# 검색 시 자동으로 Retrieval Boost 적용
```

### 5.3 감쇠 수동 트리거

```bash
# Dry-run (실제 변경 없이 영향 확인)
curl -X POST http://localhost:5050/api/memory/decay \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# 실제 실행
curl -X POST http://localhost:5050/api/memory/decay \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

### 5.4 감사 및 롤백

```bash
# 특정 기억의 변경 이력
curl http://localhost:5050/api/memory/audit/history/<memory-uuid>

# 이전 버전으로 롤백
curl -X POST http://localhost:5050/api/memory/audit/rollback \
  -H "Content-Type: application/json" \
  -d '{"revision_id": "<revision-uuid>"}'
```

---

## 6. MCP 서버 연동

Mnemosyne는 MCP(Model Context Protocol) 서버를 내장하고 있어 AI 에이전트가 직접 도구로 호출 가능합니다.

### 지원 도구 (5개)

| Tool | Description |
|------|-------------|
| `memory_store` | 기억 저장 (STM/LTM) |
| `memory_search` | 의미 기반 기억 검색 |
| `memory_boost` | 기억 중요도 강화 |
| `memory_scope` | 범위 조회/승격 |
| `memory_audit` | 감사 이력 조회 |

### REST MCP Proxy

```bash
# JSON-RPC 형식으로 MCP 도구 호출
curl -X POST http://localhost:5050/api/mcp \
  -H "Content-Type: application/json" \
  -d '{"method": "memory_search", "params": {"query": "architecture"}}'
```

---

## 7. n8n / 외부 시스템 연동

### Gateway 엔드포인트

```bash
# n8n 웹훅 수신
POST /api/gateway/n8n

# NiFi 데이터 수신
POST /api/gateway/nifi

# Spark 배치 데이터
POST /api/gateway/spark

# 범용 웹훅
POST /api/gateway/webhook
```

### n8n 워크플로우 예시

`n8n_workflows/` 폴더에 사전 구성된 템플릿이 있습니다.

---

## 8. 보안 설정

### 8.1 RBAC (역할 기반 접근 제어)

```bash
# 역할 목록 조회
curl http://localhost:5050/api/security/roles

# 접근 권한 검사
curl -X POST http://localhost:5050/api/security/check \
  -H "Content-Type: application/json" \
  -d '{"principal_id": "agent-1", "resource": "memory-uuid", "action": "read"}'
```

### 8.2 필드 암호화 (AES-256)

```bash
# 특정 기억의 필드 암호화
curl -X POST http://localhost:5050/api/security/encrypt \
  -H "Content-Type: application/json" \
  -d '{"uuid": "<memory-uuid>", "fields": ["content"]}'
```

---

## 9. 데이터 정합성 관리

### 9.1 Quick Check

```bash
curl http://localhost:5050/api/reconciliation/check
# 반환: total_memories, without_scope, stale_30d, health_score
```

### 9.2 Full Reconciliation

```bash
# 자동 수정 포함
curl -X POST http://localhost:5050/api/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{"auto_fix": true}'
```

### 9.3 검사 항목

| 검사 | 설명 | 자동 수정 |
|------|------|----------|
| Schema Completeness | 필수 속성 누락 | ✅ |
| Scope Assignment | 유효하지 않은 scope | ✅ |
| Audit Coverage | 감사 기록 없는 엔티티 | ❌ (경고만) |
| Salience Staleness | 30일 이상 미갱신 | ❌ (경고만) |
| Dead Letter Queue | Outbox 실패 건수 | ❌ (경고만) |
| Orphaned Revisions | 고아 리비전 노드 | ✅ |

---

## 10. 트러블슈팅

### Neo4j 연결 실패

```bash
# Neo4j 컨테이너 상태 확인
docker ps | grep neo4j

# Neo4j 로그 확인
docker logs mirofish-neo4j

# 환경 변수 확인
grep NEO4J .env
```

### 메모리 감쇠가 안 될 때

```bash
# 스케줄러 상태 확인
curl http://localhost:5050/api/health
# → "scheduler": "running" 확인

# 수동 감쇠 실행
curl -X POST http://localhost:5050/api/memory/decay -d '{"dry_run": false}'
```

### 테스트 실패 시

```bash
# 개별 테스트 실행 (디버그)
PYTHONPATH=src .venv/bin/python -m pytest tests/integration/test_memory_lifecycle.py -v --tb=long -s

# Neo4j 연결 확인
PYTHONPATH=src .venv/bin/python -c "
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'mirofish'))
with d.session() as s: print(s.run('RETURN 1').single()[0])
d.close()
"
```

### 포트 충돌

```bash
# 사용 중인 포트 확인
lsof -i :5050
lsof -i :7687
lsof -i :7474
```

---

## 📋 주요 환경 변수 정리

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j 연결 |
| `NEO4J_USER` | `neo4j` | Neo4j 사용자 |
| `NEO4J_PASSWORD` | — | Neo4j 비밀번호 |
| `SUPERMEMORY_API_KEY` | — | Supermemory API 키 (선택) |
| `LLM_PROVIDER` | `ollama` | LLM 제공자 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 서버 |
| `LLM_MODEL` | `llama3.1` | LLM 모델명 |
| `FLASK_SECRET_KEY` | — | Flask 세션 키 |
| `WEBHOOK_SECRET` | — | 웹훅 HMAC 시크릿 |

---

*Last updated: 2026-03-28*
