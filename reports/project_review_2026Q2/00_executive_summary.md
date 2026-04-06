# Mories Project — Executive Summary Report
> **Date**: 2026-04-06 | **Version**: v4 (Harness) | **Author**: Antigravity Project Review

---

## 1. 프로젝트 한눈에 보기

| 항목 | 현황 |
|------|------|
| **프로젝트명** | Mories (구 MiroFish-Supermemory) |
| **핵심 비전** | 인간의 인지 기억 모델을 모방한 AI 에이전트 메모리 시스템 + 자율 오케스트레이션 엔진 |
| **소스코드 규모** | Python 39,973 LOC (앱 코어) + Dashboard 9,261 LOC + MCP Server 1,776 LOC |
| **테스트** | 128 테스트 (120 PASSED / 1 FAILED / 7 ERRORS) — 93.8% Pass Rate |
| **Git 커밋** | 75 commits |
| **핵심 의존성** | Flask 3.x, Neo4j 5.x, Python 3.12+, Prometheus |
| **배포** | Docker Compose (dev/prod/monitoring 분리) |
| **MCP 도구** | 27개 도구 제공 (메모리 14 + 하네스 11 + 인프라 2) |

---

## 2. 원래 목적 vs 현재 상태

### 원래 목적
> "인간의 기억 구조를 모방하여, AI 에이전트가 세션을 넘어 맥락을 유지하고, 여러 에이전트 간 지식을 공유하며, 경험에서 자율적으로 학습하는 인지 메모리 시스템."

### 현재 달성 상태

| 목표 | 상태 | 평가 |
|------|------|------|
| STM → LTM → PM 인지 기억 라이프사이클 | ✅ 완성 | Ebbinghaus 곡선 기반 감쇠, 인출 강화, 영구 각인까지 구현 |
| 다중 에이전트 메모리 공유 (Synaptic Bridge) | ✅ 완성 | MCP 27개 도구로 Claude/Cursor/n8n 에이전트가 실제로 사용 중 |
| RBAC + 암호화 보안 계층 | ✅ 완성 | 역할 기반 접근 + AES-256 필드 암호화 |
| 워크플로우 오케스트레이션 (Harness v4) | ⚠️ 80% | DSL 스키마, 런타임, 7종 Executor, Auto-Healing 구현. 프로덕션 부하 테스트 미완 |
| 분산 실행 (Ray/Nomad/Wasm) | ⚠️ 60% | 코드 완성, Lazy-import 독립 아키텍처. 실 클러스터 E2E 검증 미완 |
| 글로벌 범용 프로덕트 | ❌ 30% | 아래 상세 분석 참조 |

---

## 3. 핵심 강점

### 3.1 독창적 인지 메모리 아키텍처
- **Ebbinghaus 망각곡선 기반 감쇠** — 학술적 근거를 가진 유일한 오픈소스 메모리 시스템
- **계층적 Scope 시스템** (Personal → Tribal → Social → Global) — 컨텍스트 격리와 지식 상속이 동시 가능
- **Procedural/Observational 카테고리** — 도구 사용 경험과 행동 관찰을 분리 기록

### 3.2 실전 검증된 MCP 통합
- 27개 MCP 도구가 **실제 일상 개발 세션**에서 사용되고 있음 (대화 이력 20+ 세션 증빙)
- Claude Desktop, Cursor, n8n에서의 크로스-플랫폼 호환성 검증 완료

### 3.3 잘 설계된 모듈 아키텍처
- Flask 블루프린트 기반 API 모듈화 (10개 블루프린트)
- Lazy-import 패턴으로 인프라 계층 완전 분리
- Dependency Injection (DI)으로 테스트 용이성 확보

---

## 4. 핵심 약점 (글로벌 프로덕트 관점)

### 🔴 Critical
1. **영어 문서/코드 혼재** — 한국어·중국어·영어가 무작위로 혼재 (requirements.txt에 중문 주석, README에 한국어)
2. **테스트 커버리지 불균형** — E2E/Integration 테스트 다수가 Neo4j 실행 의존 (CI/CD 병목)
3. **API 인증 부재** — JWT/OAuth 없이 API Key 수준. 멀티테넌트 SaaS로 부적합
4. **모니터링 미성숙** — Prometheus 메트릭 정의됨, 실제 Grafana 대시보드/알림 설정 없음

### 🟡 Warning
5. **거대 파일 문제** — `report_agent.py` (2,579 LOC), `simulation.py` (2,715 LOC), `memory_categories.py` (2,410 LOC) 단일 파일에 과도한 로직 집중
6. **exec() 보안 리스크** — `ray_executor.py`에서 동적 코드 실행 (`exec(script_code)`)
7. **하드코딩된 IP/URL** — MCP 서버에 `192.168.35.86` 등 로컬 IP 하드코딩

---

## 5. 글로벌 프로덕트 가능성 평가

| 영역 | 점수 | 논거 |
|------|------|------|
| **기술적 독창성** | ⭐⭐⭐⭐ (4/5) | 인지 심리학 기반 메모리 → 학술적·기능적 차별화 확실 |
| **시장 포지셔닝** | ⭐⭐⭐ (3/5) | Mem0, Zep, Letta 대비 오케스트레이션 통합이 차별점이나, 이들의 성숙도/생태계에 아직 미달 |
| **코드 프로덕션 준비도** | ⭐⭐ (2/5) | 보안, 인증, i18n, 에러 핸들링, 로깅이 프로덕션 수준 미달 |
| **확장성** | ⭐⭐⭐ (3/5) | Neo4j 수직 확장 한계, Ray/Nomad 수평 확장 프레임 있으나 미검증 |
| **개발 속도/팀 역량** | ⭐⭐⭐⭐⭐ (5/5) | 1인 개발로 40K LOC, 15 phase 완성. 매우 빠른 진행 |

### 종합 판정

> **현재 상태**: 강력한 R&D 프로토타입 + 실전 검증된 개인 도구
> **글로벌 프로덕트까지**: 12~18개월의 체계적 엔지니어링 필요
> **최적 전략**: 인지 메모리 엔진을 핵심 라이브러리로 분리 → PyPI 패키지 배포 → SDK 중심 생태계 구축

---

## 6. 상세 보고서 목록

| # | 파일 | 내용 |
|---|------|------|
| 1 | [01_codebase_analysis.md](./01_codebase_analysis.md) | 코드베이스 상세 분석 (모듈별 LOC, 복잡도, 기술 부채) |
| 2 | [02_architecture_review.md](./02_architecture_review.md) | 아키텍처 리뷰 (강점, 약점, 개선 권고) |
| 3 | [03_competitive_analysis.md](./03_competitive_analysis.md) | 경쟁 분석 (Mem0, Zep, Letta, LangGraph 대비 포지셔닝) |
| 4 | [04_harness_orchestration.md](./04_harness_orchestration.md) | 하네스 오케스트레이션 엔진 깊이 분석 |
| 5 | [05_product_readiness.md](./05_product_readiness.md) | 프로덕트 준비도 평가 + 글로벌 출시 로드맵 |

---

*이 보고서는 2026년 4월 6일 기준 코드베이스 분석을 바탕으로 작성되었습니다.*
