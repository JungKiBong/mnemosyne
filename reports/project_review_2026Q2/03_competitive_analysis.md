# 03. 경쟁 분석 — AI 에이전트 메모리 & 오케스트레이션
> **Date**: 2026-04-06 | **관점**: Mories의 시장 포지셔닝과 차별화 전략

---

## 1. 시장 구도 (2026 Q2)

AI 에이전트 인프라는 두 축으로 분화하고 있습니다:

```
                    오케스트레이션 (Workflow)
                           ▲
                           │
    Temporal ──────────────┼──────────── LangGraph
    (Durable Execution)    │            (Agent Logic)
                           │
                           │   ★ Mories
                           │   (Memory + Orchestration)
                           │
    Argo/Dagger ───────────┼──────────── n8n/Dify
    (Infra Pipeline)       │            (Low-Code AI)
                           │
    ◄──────────────────────┼──────────────────────►
    인프라/Reliability                    Intelligence/AI
                           │
    Redis ─────────────────┼──────────── Mem0
    (KV Cache)             │            (AI Memory)
                           │
    Zep ───────────────────┼──────────── Letta (MemGPT)
    (Session Memory)       │            (Cognitive Memory)
                           │
                           ▼
                    메모리 (Persistence)
```

---

## 2. 핵심 경쟁자 비교

### 2.1 메모리 계층 경쟁자

| 기준 | **Mories** | **Mem0** | **Zep** | **Letta (MemGPT)** |
|------|-----------|---------|---------|-------------------|
| **핵심 철학** | 인지 심리학 기반 기억 모델 | 개인화 AI 메모리 | 세션 메모리 + 팩트 추출 | Self-editing 메모리 에이전트 |
| **메모리 모델** | STM → LTM → PM + Ebbinghaus 감쇠 | Flat key-value + Graph | Temporal windowed + Facts | Archival + Working Memory + Persona |
| **망각 메커니즘** | ✅ Ebbinghaus 곡선 | ❌ 없음 | ❌ 없음 | 🟡 Context 윈도우 관리 |
| **다중 에이전트** | ✅ Synaptic Bridge | 🟡 User-level 분리만 | 🟡 Session 수준 | ❌ 단일 에이전트 |
| **MCP 지원** | ✅ 27개 도구 | ✅ 5개 도구 | ❌ | ❌ |
| **오케스트레이션** | ✅ Harness v4 | ❌ | ❌ | ❌ |
| **스토리지** | Neo4j (Graph) | PostgreSQL + Vector | PostgreSQL + Vector | ChromaDB / PostgreSQL |
| **GitHub Stars** | ~0 (Private) | ~25K | ~3K | ~15K |
| **팀 규모** | 1인 | 15+ | 10+ | YC 스타트업 |
| **SaaS 제공** | ❌ | ✅ Cloud API | ✅ Cloud API | ✅ Cloud API |
| **가격** | OSS (무료) | Free/Pro ($49+) | Free/Pro | Free/Pro |
| **SDK** | Python REST + MCP | Python/JS/Go SDK | Python/JS SDK | Python SDK |

### 2.2 Mories만의 고유 강점

| 차별 요소 | 설명 | 경쟁사 대비 |
|-----------|------|------------|
| **Ebbinghaus 감쇠** | 인지 심리학 망각곡선으로 자동 정리 | 유일 |
| **Scope Ladder** | Personal→Tribal→Social→Global 계층 | 유일 |
| **Permanent Memory** | Imprint/Frozen 영구 각인 | 유일 |
| **Harness 자기 진화** | 실행 → 학습 → 진화 자체 루프 | 유일 |
| **Audit Trail + Rollback** | 모든 기억 변경의 불변 이력 | Letta만 유사 |
| **27 MCP 도구** | 가장 풍부한 MCP 도구셋 | 업계 최다 수준 |

### 2.3 Mories의 약점 (경쟁사 대비)

| 약점 | 영향 | 경쟁사 비교 |
|------|------|------------|
| **벡터 검색 미지원** | RAG 기반 시맨틱 검색 불가 | Mem0/Zep의 핵심 기능 |
| **SDK 미제공** | Python/JS 클라이언트 라이브러리 없음 | 전 경쟁사 SDK 보유 |
| **Cloud SaaS 없음** | 셀프 호스트만 가능 | 전 경쟁사 Cloud 제공 |
| **커뮤니티 없음** | GitHub Stars 0, 문서 부족 | Mem0: 25K stars |
| **영어 문서 미비** | 글로벌 접근 불가 | 전 경쟁사 영어 first |

---

## 3. 오케스트레이션 계층 경쟁자

### 3.1 비교 매트릭스

| 기준 | **Mories Harness** | **LangGraph** | **Temporal** | **n8n** |
|------|-------------------|---------------|-------------|---------|
| **핵심 기능** | 메모리 통합 워크플로우 | 에이전트 상태 머신 | Durable Execution | 노코드 워크플로우 |
| **DSL 형식** | JSON Schema v4 | Python DAG | Go/Python Activity | Visual Canvas |
| **분산 실행** | Ray, Nomad, Wasm | 없음 | Worker 기반 | 단일 서버 |
| **메모리 통합** | ✅ 네이티브 | ❌ 없음 | ❌ 없음 | ❌ 없음 |
| **자기 복구** | ✅ LLM Healer | ❌ | ✅ (Retry) | 🟡 (실패 재시도) |
| **성숙도** | 🟡 프로토타입 | 🟢 프로덕션 | 🟢 프로덕션 | 🟢 프로덕션 |
| **학습 곡선** | 🟡 중간 | 🔴 높음 | 🔴 매우 높음 | 🟢 낮음 |
| **실행 보장** | 체크포인트 재개 | 체크포인트 | At-Least-Once | 실패 시 재시도 |
| **HITL** | ✅ 네이티브 게이트 | ✅ | ❌ (커스텀 구현) | 🟡 (수동 트리거) |

### 3.2 Mories Harness의 고유 포지션

> **"메모리 통합 오케스트레이터"** — 실행 경험이 자동으로 지식 그래프에 누적되어, 다음 실행에서 더 나은 의사결정을 하는 자율 진화형 엔진

이것은 LangGraph나 Temporal이 제공하지 못하는 **고유한 가치**입니다. 워크플로우 실행이 단순히 "작업 완료"에 그치지 않고, 시스템의 **인지적 성장**으로 이어진다는 점이 핵심 차별화입니다.

---

## 4. 시장 진입 전략 분석

### 4.1 진입 가능한 세그먼트

| 세그먼트 | TAM | Mories 적합도 | 진입 난이도 |
|----------|-----|--------------|------------|
| **1. MCP 도구 생태계** | 성장 중 | ⭐⭐⭐⭐⭐ | 🟢 낮음 |
| **2. AI 에이전트 메모리** | $500M+ | ⭐⭐⭐⭐ | 🟡 중간 |
| **3. 워크플로우 오케스트레이션** | $2B+ | ⭐⭐ | 🔴 매우 높음 |
| **4. 엔터프라이즈 지식 관리** | $10B+ | ⭐⭐⭐ | 🔴 높음 |

### 4.2 최적 진입 순서

```
Phase 1 (0-3개월): MCP Memory Tool → PyPI 패키지 배포
                   "pip install mories-mcp" 한 줄로 시작
                   
Phase 2 (3-6개월): Python SDK → JS SDK → Go SDK
                   LangChain/LangGraph/CrewAI 통합 플러그인
                   
Phase 3 (6-12개월): Cloud SaaS → Managed Instance
                   Free tier → Pro tier 전환
                   
Phase 4 (12-18개월): Enterprise → On-premise License
                   SOC2 인증, GDPR 준수
```

---

## 5. SWOT 분석

| | 긍정적 | 부정적 |
|---|---|---|
| **내부** | **Strengths**: 인지 심리학 기반 독창성, MCP 27도구, 풍부한 기능셋, 1인 개발 효율성 | **Weaknesses**: 0 커뮤니티, SDK 미제공, 영어 문서 부족, SaaS 미제공, 벡터 검색 없음 |
| **외부** | **Opportunities**: MCP 생태계 급성장, 멀티 에이전트 수요 폭발, Mem0/Zep의 오케스트레이션 부재 | **Threats**: Mem0의 자금력($12M+), LangChain의 생태계 장악, 대형 클라우드(OpenAI Memory, Google Gemini Memory) 직접 진입 |

---

## 6. 핵심 결론

### Mories의 시장 위치: "차별화된 기술, 미성숙한 Go-To-Market"

**기술적으로** Mories는 경쟁사 대비 명확한 차별화 포인트를 보유합니다:
1. 유일한 인지 심리학 기반 메모리 모델
2. 유일한 메모리+오케스트레이션 통합 시스템
3. 가장 풍부한 MCP 도구셋

**상업적으로** 다음이 부족합니다:
1. 개발자 온보딩 경험 (SDK, 문서, 예제)
2. 클라우드 서비스 (SaaS 호스팅)
3. 커뮤니티 + 브랜드 인지도
4. Go-To-Market 전략 + 가격 모델

> **판단**: 기술 자체는 글로벌 경쟁력이 있으나, 프로덕트로의 전환에 12~18개월의 체계적 투자가 필요합니다. 가장 빠른 PMF (Product-Market Fit) 경로는 **MCP 도구 생태계 진입 → PyPI 패키지 → LangChain 플러그인** 순서입니다.
