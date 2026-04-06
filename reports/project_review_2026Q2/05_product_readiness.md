# 05. 프로덕트 준비도 평가 + 글로벌 출시 로드맵
> **Date**: 2026-04-06 | **관점**: 글로벌 범용 프로덕트로의 전환 가능성과 로드맵

---

## 1. 프로덕트 준비도 매트릭스 (PRG: Product Readiness Grid)

### 1.1 기능 완성도

| 영역 | 점수 | 근거 |
|------|------|------|
| **인지 메모리 엔진** | 90% | STM/LTM/PM 라이프사이클, Ebbinghaus, Scope, Categories 모두 구현 |
| **API 완성도** | 85% | 166 엔드포인트, 모든 CRUD 작동. 버전닝/인증/스키마검증 미흡 |
| **MCP 도구** | 95% | 27개 도구 실전 사용 중. 가장 성숙한 모듈 |
| **대시보드** | 75% | 15개 HTML 페이지, 차트/그래프. 반응형/접근성 미흡 |
| **하네스 오케스트레이션** | 70% | DSL + 런타임 + 7종 Executor. 보안/E2E 검증 미완 |
| **보안** | 50% | RBAC + AES-256. JWT/OAuth/TLS 없음 |
| **배포** | 60% | Docker Compose 있으나, K8s/Helm/CI-CD 없음 |
| **문서** | 40% | README 양호, API 문서 부분적. 개발자 가이드/튜토리얼 없음 |
| **SDK/라이브러리** | 5% | MCP 서버만 존재. Python/JS SDK 없음 |

### 1.2 비기능 요구사항

| 요구사항 | 현재 수준 | 프로덕션 요구 | 갭 |
|----------|----------|-------------|---|
| **가용성 (Availability)** | 단일 인스턴스 | 99.9% SLA | 🔴 크리티컬 |
| **확장성 (Scalability)** | 수직 확장만 | 수평 확장 + 자동 스케일링 | 🔴 |
| **성능 (Performance)** | 미측정 | P95 < 200ms, TPS > 1000 | 🔴 |
| **보안 (Security)** | API Key | OAuth2 + JWT + TLS | 🔴 |
| **관측성 (Observability)** | Prometheus 정의 | Grafana + OTel + 알림 | 🟡 |
| **국제화 (i18n)** | 한국어/영어 혼재 | 영어 기본 + i18n 프레임워크 | 🟡 |
| **접근성 (a11y)** | 미적용 | WCAG 2.1 AA | 🟡 |
| **데이터 백업** | 없음 | 자동화된 일일 백업 | 🟡 |
| **규정 준수** | 없음 | GDPR, SOC2, HIPAA | 🔴 (SaaS 시) |

---

## 2. 글로벌 프로덕트 전환 시 필수 작업

### Phase 0: 기반 정리 (0-1개월) — "Clean Foundation"

| # | 작업 | 예상 공수 | 우선순위 |
|---|------|---------|---------|
| 0.1 | 레거시 코드 분리 (시뮬레이션, 보고서) | 1주 | P0 |
| 0.2 | `requirements.txt` → `extras` 분리 | 2일 | P0 |
| 0.3 | 전체 코드 영어 통일 (주석, 변수명, 문서) | 1주 | P0 |
| 0.4 | API 버전닝 `/api/v1/` 도입 | 3일 | P0 |
| 0.5 | 하드코딩 IP/URL → 환경변수 전환 | 1일 | P0 |
| 0.6 | `exec()` → Wasm 샌드박스 기본값 | 3일 | P0 |

### Phase 1: SDK & 개발자 경험 (1-3개월) — "Developer Adoption"

| # | 작업 | 예상 공수 | 비고 |
|---|------|---------|------|
| 1.1 | Python SDK (`pip install mories`) | 3주 | 핵심 — PyPI 배포 |
| 1.2 | JavaScript/TypeScript SDK | 2주 | npm 패키지 |
| 1.3 | API 문서 자동 생성 (OpenAPI/Swagger) | 1주 | Flask-RESTX 또는 Flasgger |
| 1.4 | 개발자 포털 (docs.mories.dev) | 2주 | Docusaurus/MkDocs |
| 1.5 | 빠른 시작 튜토리얼 5종 | 1주 | 온보딩 필수 |
| 1.6 | LangChain/LangGraph 통합 플러그인 | 2주 | 생태계 진입 핵심 |
| 1.7 | CrewAI/AutoGen 통합 플러그인 | 1주 | 시장 확장 |

### Phase 2: 프로덕션 인프라 (3-6개월) — "Production Ready"

| # | 작업 | 예상 공수 | 비고 |
|---|------|---------|------|
| 2.1 | JWT + OAuth2 인증 레이어 | 3주 | Keycloak 또는 Auth0 |
| 2.2 | TLS/HTTPS 기본 적용 | 1주 | Let's Encrypt |
| 2.3 | STM 영속화 (Redis 전환) | 2주 | 서버 재시작 시 STM 유실 방지 |
| 2.4 | Storage ABC 인터페이스 + Mock 테스트 | 2주 | CI/CD 해금 |
| 2.5 | Kubernetes Helm Chart | 2주 | 프로덕션 배포 |
| 2.6 | CI/CD 파이프라인 (GitHub Actions) | 1주 | PR 자동 테스트 |
| 2.7 | Grafana 대시보드 + 알림 | 1주 | 운영 관측성 |
| 2.8 | 벡터 검색 통합 (pgvector or Qdrant) | 3주 | 시맨틱 검색 = 경쟁력 |
| 2.9 | 부하 테스트 + 벤치마크 게시 | 2주 | 성능 신뢰성 |

### Phase 3: 클라우드 서비스 (6-12개월) — "SaaS Launch"

| # | 작업 | 예상 공수 | 비고 |
|---|------|---------|------|
| 3.1 | 멀티 테넌트 아키텍처 | 6주 | 가장 큰 리팩터링 |
| 3.2 | 관리형 인스턴스 프로비저닝 | 4주 | Terraform/Pulumi |
| 3.3 | 과금 통합 (Stripe) | 2주 | Free/Pro/Enterprise 티어 |
| 3.4 | 대시보드 React SPA 재구축 | 6주 | HTML → React/Next.js |
| 3.5 | GDPR/SOC2 준수 | 8주+ | 법무 + 기술 |
| 3.6 | 글로벌 CDN + 리전 선택 | 2주 | US/EU/AP |

---

## 3. 가격 모델 제안

### 3.1 OSS + Cloud 하이브리드 모델

```
┌─────────────────────────────────────────────────────┐
│                    Mories Pricing                    │
├─────────────┬───────────────┬───────────────────────┤
│   Community │     Pro       │     Enterprise        │
│   (Free)    │   ($29/mo)    │   ($299/mo+)          │
├─────────────┼───────────────┼───────────────────────┤
│ Self-hosted │ Cloud managed │ Dedicated instance    │
│ 5K memories │ 100K memories │ Unlimited             │
│ 1 agent     │ 10 agents     │ Unlimited agents      │
│ No SLA      │ 99.9% SLA    │ 99.99% SLA + Support  │
│ Community   │ Email support │ Slack/Phone + CSM     │
│ support     │               │                       │
│             │ Analytics     │ SSO/SAML              │
│             │ Harness v4    │ SOC2 / HIPAA          │
│             │               │ Custom deployment     │
└─────────────┴───────────────┴───────────────────────┘
```

### 3.2 수익 화 경로

| 시점 | 전략 | 예상 MRR |
|------|------|---------|
| M1-3 | PyPI 무료 배포 → 사용자 확보 | $0 |
| M4-6 | Pro 클라우드 서비스 출시 | $500-2K |
| M7-12 | 기업 파일럿 + 인디 개발자 확산 | $5K-20K |
| M13-18 | Enterprise 계약 | $50K-100K |

---

## 4. 위험 요소 (Risk Assessment)

### 4.1 기술 위험

| 위험 | 확률 | 영향 | 완화 전략 |
|------|------|------|---------|
| Neo4j 성능 한계 (100M+ 노드) | 중 | 높음 | 샤딩/티어링 전략 사전 설계 |
| LLM Healer의 비용/지연 | 중 | 중 | 캐시 + 로컬 모델 폴백 |
| Ray/Nomad 클러스터 복잡도 | 높 | 중 | 단순 모드 (local executor) 기본 제공 |
| 멀티테넌트 전환 복잡도 | 높 | 높음 | 초기부터 테넌트 식별자 주입 |

### 4.2 시장 위험

| 위험 | 확률 | 영향 | 완화 전략 |
|------|------|------|---------|
| OpenAI/Google이 빌트인 메모리 출시 | 높 | 매우 높음 | 오픈소스 + 멀티 LLM 지원으로 벤더 종속 해소 |
| Mem0/Zep이 오케스트레이션 추가 | 중 | 높음 | 인지 심리학 기반 차별화 강화 |
| MCP 생태계가 성장하지 않음 | 낮 | 중 | REST API/SDK 다중 인터페이스 |

### 4.3 실행 위험

| 위험 | 확률 | 영향 | 완화 전략 |
|------|------|------|---------|
| 1인 개발 한계 | 매우 높 | 매우 높음 | OSS 컨트리뷰터 유치 또는 2인체 확장 |
| 번아웃 | 높 | 높음 | Phase별 마일스톤 + 작은 승리 축적 |
| 커뮤니티 구축 실패 | 중 | 높음 | 초기에 "1 killer use case" 집중 |

---

## 5. 추천 전략: "Memory-First SDK"

### 5.1 핵심 전략

> **인지 메모리 엔진을 독립 Python 라이브러리로 추출하여, 모든 AI 에이전트 프레임워크에서 `pip install mories`만으로 사용 가능하게 만든다.**

```python
# 목표: 개발자가 5분 안에 이것을 실행할 수 있어야 한다
from mories import MemoryEngine

memory = MemoryEngine(backend="neo4j", uri="bolt://localhost:7687")
memory.remember("Flask app should use Blueprint pattern", salience=0.9)

results = memory.recall("Flask architecture best practices")
# → [{content: "Flask app should use Blueprint pattern", salience: 0.86}, ...]

memory.run_decay()  # Ebbinghaus 감쇠 실행
```

### 5.2 왜 이 전략인가?

1. **가장 빠른 PMF 경로** — SDK는 설치 1줄로 시작 가능
2. **생태계 진입** — LangChain/CrewAI/AutoGen과 즉시 통합
3. **커뮤니티 구축** — PyPI 다운로드 → GitHub Stars → 기여자
4. **SaaS 전환 용이** — `MemoryEngine(backend="cloud")` 한 줄로 전환

### 5.3 경쟁사 실수에서 배운 것

- **Mem0**: SDK-first 전략으로 25K stars → 빠른 성장. 그러나 오케스트레이션 없음
- **Zep**: Cloud-first 전략으로 기업 고객 확보. 그러나 인지 모델 부재
- **Letta**: 논문-first 전략으로 학술 인지도. 그러나 실용성 부족

**Mories의 최적 전략**: Mem0의 SDK 전략 + Zep의 Cloud 중심 + Mories만의 인지 심리학 차별화

---

## 6. 최종 판정

### 글로벌 범용 프로덕트가 될 수 있는가?

> **Yes, but conditionally.**

**전제 조건**:
1. ✅ 기술적 독창성이 있다 (인지 기억 모델, 메모리+오케스트레이션 통합)
2. ⚠️ 프로덕션 품질 갭이 크다 (보안, 확장성, SaaS)
3. ⚠️ 시장 진입 도구가 없다 (SDK, 문서, 커뮤니티)
4. 🔴 1인 실행 리스크가 가장 크다

**현실적 타임라인**:

| 마일스톤 | 시기 | 지표 |
|---------|------|------|
| PyPI 첫 릴리스 | M1 | `pip install mories` 가능 |
| 100 GitHub Stars | M3 | 얼리어답터 관심도 |
| LangChain 통합 | M4 | 생태계 인입 |
| 첫 유료 고객 | M8 | PMF 검증 |
| $10K MRR | M14 | 비즈니스 생존 가능성 |
| $50K MRR | M24 | 풀타임 전환 가능 |

---

## 7. 즉시 실행 가능한 액션 아이템 (Top 5)

| 순위 | 액션 | 기대 효과 | 소요 시간 |
|------|------|---------|---------|
| 1 | 레거시 코드 분리 + requirements extras | 설치 시간 90% 단축, 코드 24% 경량화 | 1주 |
| 2 | `mories` PyPI 패키지 추출 | 개발자 온보딩 5분 → PMF 검증 가능 | 3주 |
| 3 | OpenAPI/Swagger 문서 자동 생성 | API 신뢰성 + 클라이언트 자동 생성 | 1주 |
| 4 | GitHub Public 전환 + README 영문화 | OSS 커뮤니티 접근 | 3일 |
| 5 | LangChain Memory 플러그인 작성 | 생태계 최대 채널 진입 | 2주 |

---

> *"The best technology doesn't always win. The best developer experience does."*
> — Mories가 기억해야 할 가장 중요한 교훈

---

*이상으로 Mories 프로젝트 중간 보고서를 마칩니다.*
*2026-04-06, Antigravity Project Review*
