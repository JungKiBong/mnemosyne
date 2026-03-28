# Mories n8n 워크플로우 카탈로그

> Mories 메모리 시스템과 다양한 데이터 소스를 연결하는 n8n 워크플로우 모음

## 개요

이 디렉토리에는 **13개**의 즉시 사용 가능한(ready-to-import)한 n8n 워크플로우가 포함되어 있습니다.
모든 워크플로우는 Mories의 **Gateway API** (`/api/gateway/webhook`)를 통해 데이터를 인제스트하며,
STM → 평가 → LTM 프로모션 파이프라인을 자동으로 거칩니다.

## 설치 방법

### 방법 1: n8n UI에서 직접 가져오기
1. n8n 편집기 열기
2. `⋮` → **Import from File** 클릭
3. 원하는 `.json` 파일 선택
4. 환경변수 설정 후 활성화

### 방법 2: n8n API로 일괄 설치
```bash
for f in n8n_workflows/*.json; do
  curl -X POST "http://localhost:5678/api/v1/workflows" \
    -H "Content-Type: application/json" \
    -H "X-N8N-API-KEY: $N8N_API_KEY" \
    -d @"$f"
done
```

### 방법 3: 대시보드에서 설치
대시보드(`/dashboard`) → **n8n Workflows** 탭에서 워크플로우를 선택하고 설치할 수 있습니다.

## 워크플로우 카탈로그

### 📚 기본 (01-03)

| # | 이름 | 트리거 | 데이터 소스 | 설명 |
|:--|:-----|:-------|:-----------|:-----|
| 01 | 지식 그래프 검색 | Manual | Mories | MCP를 통한 메모리 검색 |
| 02 | 뉴스 자동 수집 | ⏰ 6시간 | NewsAPI | 한국 뉴스를 자동으로 수집하여 기억에 저장 |
| 03 | 에이전트 스냅샷 | Manual | Mories | 에이전트 프로필을 Google Sheets로 내보내기 |

### 🔌 데이터 소스 연동 (04-10)

| # | 이름 | 트리거 | 데이터 소스 | 설명 |
|:--|:-----|:-------|:-----------|:-----|
| 04 | GitHub 저장소 감시 | ⏰ 1시간 | GitHub API | 커밋 메시지를 자동으로 기억에 저장 |
| 05 | RSS 피드 수집 | ⏰ 4시간 | RSS/Atom | arXiv, 블로그, 뉴스 등 RSS 피드 구독 |
| 06 | Slack → 기억 | 🔗 Webhook | Slack Events | `📝`, `#remember` 태그 메시지를 기억으로 |
| 07 | 파일 업로드 | 🔗 Webhook | 파일(txt/json/csv) | 텍스트 파일을 청킹하여 메모리에 인제스트 |
| 08 | 웹 스크래핑 | 🔗 Webhook | 웹 페이지 | URL을 입력하면 페이지 내용을 기억으로 |
| 09 | Email 수신 | ⏰ 30분 | Gmail | 별표/태그된 이메일을 자동 기억 저장 |
| 10 | DB 변경 동기화 | ⏰ 15분 | PostgreSQL | DB 변경 사항을 실시간 기억 동기화 |

### 🔗 외부 플랫폼 (11-13)

| # | 이름 | 트리거 | 데이터 소스 | 설명 |
|:--|:-----|:-------|:-----------|:-----|
| 11 | 기억 건강 모니터 | ⏰ 12시간 | Mories API | 시스템 상태 체크 & Slack 알림 |
| 12 | Notion 동기화 | ⏰ 2시간 | Notion API | Notion DB 변경을 기억에 반영 |
| 13 | YouTube → 기억 | 🔗 Webhook | YouTube API | 영상 자막/메타를 기억으로 저장 |

## 환경변수

모든 워크플로우는 n8n 환경변수를 통해 설정됩니다:

```env
# ─── Mories 공통 ───
MORIES_URL=http://localhost:5001
MORIES_GRAPH_ID=default

# ─── GitHub (04) ───
GITHUB_TOKEN=ghp_xxx
GITHUB_OWNER=your-org
GITHUB_REPO=your-repo

# ─── RSS (05) ───
RSS_FEED_URL=https://arxiv.org/rss/cs.AI
RSS_FEED_NAME=arxiv-ai

# ─── News API (02) ───
NEWS_API_KEY=your-newsapi-key

# ─── Slack (06, 11) ───
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx

# ─── Gmail (09) ───
# Gmail OAuth2 자격증명은 n8n 크레덴셜에서 설정

# ─── Notion (12) ───
NOTION_API_KEY=ntn_xxx
NOTION_DATABASE_ID=xxx-xxx

# ─── YouTube (13) ───
YOUTUBE_API_KEY=AIza_xxx
```

## 아키텍처

```
┌─────────────────────────────────────────────────────┐
│                    n8n Workflows                     │
│  ┌────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐  │
│  │ GitHub │ │   RSS   │ │  Slack   │ │  Notion  │  │
│  └────┬───┘ └────┬────┘ └────┬─────┘ └────┬─────┘  │
│       │          │           │             │         │
│       ▼          ▼           ▼             ▼         │
│  ┌──────────────────────────────────────────────┐   │
│  │          Transform & Normalize               │   │
│  └────────────────────┬─────────────────────────┘   │
└───────────────────────┼─────────────────────────────┘
                        │ HTTP POST
                        ▼
┌───────────────────────┼─────────────────────────────┐
│ Mories Gateway     │  /api/gateway/webhook       │
│  ┌────────────────────▼──────────────────────────┐  │
│  │           MemoryPipeline                      │  │
│  │  ┌───────┐    ┌──────────┐    ┌───────────┐  │  │
│  │  │  STM  │ →  │ Evaluate │ →  │ Promote   │  │  │
│  │  │Create │    │ Salience │    │ to LTM    │  │  │
│  │  └───────┘    └──────────┘    └───────────┘  │  │
│  └───────────────────────────────────────────────┘  │
│                        │                             │
│                        ▼                             │
│  ┌───────────────────────────────────────────────┐  │
│  │              Neo4j Knowledge Graph            │  │
│  └───────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

## 커스텀 워크플로우 만들기

새 데이터 소스를 추가하려면 다음 패턴을 따르세요:

```json
{
  "method": "POST",
  "url": "http://localhost:5001/api/gateway/webhook",
  "body": {
    "content": "수집된 텍스트 내용",
    "source": "소스유형:출처이름",
    "graph_id": "그래프 ID",
    "scope": "personal | tribal | social",
    "metadata": {
      "key": "추가 메타데이터"
    }
  }
}
```

### scope 가이드
- `personal`: 개인 일기, 노트, 개인 이메일
- `tribal`: 팀/조직 공유 지식, 코드 변경, 회의록
- `social`: 공개 뉴스, 논문, 웹 자료

### graph_id 가이드
- `default`: 범용
- `dev-knowledge`: 개발 관련 지식
- `research`: 연구/논문
- `communications`: 커뮤니케이션
- `documents`: 문서 관리
- 원하는 이름으로 자유 생성 가능
