# Mories 핸드오버 — Part 4: 기술 상세 & 아키텍처 참조 (v2.0)
# 문서 경로: docs/handover/HANDOVER_v2.0_part4_technical.md
# 버전: v2.0 | 갱신일: 2026-04-02

---

## 1. 대시보드 i18n 시스템 아키텍처

### 1.1 구조
```
dashboard/
├── i18n.js                  # 중앙 번역 사전 (ko/en, 464줄)
├── nav-component.js         # 사이드바 (자체 I18N 사전 내장)
├── nav-component.css        # 사이드바 스타일 (접기/펴기 포함)
└── [각 페이지].html         # data-i18n 속성 + window.t() 사용
```

### 1.2 번역 적용 방법

**정적 HTML 요소:**
```html
<h2 data-i18n="pageTitle">기본값</h2>
```

**동적 JS 문자열:**
```javascript
const text = window.t('key_name');
document.getElementById('el').textContent = text;
```

**날짜/시간 포맷:**
```javascript
const lang = localStorage.getItem('moriesLang') || 'ko';
const formatted = new Date().toLocaleString(lang === 'ko' ? 'ko-KR' : 'en-US');
```

### 1.3 새 키 추가 절차
1. `dashboard/i18n.js`의 `DICTIONARY` 객체에 `ko`와 `en` 키 쌍 추가
2. HTML에 `data-i18n="새키"` 속성 추가 또는 JS에서 `window.t('새키')` 사용
3. `nav-component.js`의 I18N 객체는 사이드바 전용 (수정 별도)

---

## 2. 사이드바 접기/펴기 기술 상세

### 2.1 상태 관리
```
localStorage('moriesSidebarCollapsed') → '0' (펼침) | '1' (접힘)
```

### 2.2 CSS 클래스 체계
```
.mories-sidebar                      # 기본 260px
.mories-sidebar.collapsed            # 접힘 72px
body.mories-has-sidebar              # padding-left: 260px
body.mories-has-sidebar.mories-sidebar-collapsed  # padding-left: 72px
```

### 2.3 접힌 상태 동작
- 라벨(`.mories-sidebar__label`): opacity 0, width 0
- 그룹 제목(`.mories-sidebar__group-title`): height 0, overflow hidden
- 브랜드 텍스트: 숨김 (로고 M만 표시)
- 테마/언어 토글: `display: none`
- 상태 pill: 도트만 표시 (`font-size: 0`)
- 아이콘 hover: CSS `::after` 의사 요소로 `data-tooltip` 표시

---

## 3. Nginx 라우팅 매핑 (dashboard/nginx.conf)

| URL 경로 | 파일 | 비고 |
|----------|------|------|
| `/` | `index.html` | 대시보드 |
| `/graph` | `graph.html` | try_files $uri.html |
| `/memory` | `memory.html` | 〃 |
| `/synaptic` | `synaptic.html` | 〃 |
| `/memory_history` | `memory_history.html` | 〃 |
| `/terminology` | `terminology.html` | 〃 |
| `/maturity` | `maturity.html` | 〃 |
| `/workflows` | `workflows.html` | 〃 |
| `/api-docs` | `api-docs.html` | 〃 |
| `/guide` | `guide.html` | 〃 |
| `/api/*` | proxy → mirofish-api:5000 | API 프록시 |

---

## 4. 주요 파일 맵 (갱신)

```
mirofish-supermemory/
├── src/app/
│   ├── api/            # Flask 라우트
│   ├── storage/        # Neo4j 스토리지
│   ├── services/       # 비즈니스 로직
│   ├── adapters/       # 파일 인제스천 어댑터
│   ├── utils/          # 유틸 (webhook, llm_client, logger)
│   ├── security/       # 암호화 (memory_encryption)
│   └── config.py       # 환경변수 중앙 관리
├── mcp_server/         # MCP 프로토콜 서버
├── dashboard/
│   ├── i18n.js         # 중앙 번역 사전 (464줄)
│   ├── nav-component.js  # 사이드바 공유 컴포넌트
│   ├── nav-component.css # 사이드바 스타일
│   ├── nginx.conf      # 라우팅 설정
│   ├── assets/css/tokens.css  # CSS 변수/테마
│   ├── docs/           # 마크다운 가이드 (동적 로딩)
│   └── [10개 HTML]     # 각 페이지
├── tests/
│   ├── e2e/    unit/    integration/
│   └── temp/           # 임시 테스트 (안전 삭제 가능)
├── docs/handover/      # 핸드오버 문서 (v1.0 + v2.0)
├── docker-compose.yml  # 개발 환경
└── docker-compose.prod.yml  # 프로덕션 오버라이드
```

---

## 5. 환경변수 요약 (.env)

```bash
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=mirofish     # 하드코딩 금지, .env에서만 관리

LLM_PROVIDER=ollama          # ollama | openai | vllm
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL_NAME=qwen2.5:32b
LLM_API_KEY=ollama

EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://host.docker.internal:11434
EMBEDDING_MODEL=nomic-embed-text

WEBHOOK_ENABLED=false
WEBHOOK_URL=
WEBHOOK_SECRET=
MCP_API_KEY=
```

> ⚠️ `.env` 파일은 Git 커밋 금지. `.env.example`만 커밋.
