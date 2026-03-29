# 🔄 Mories n8n Workflows

> **Phase 4-3: Orchestration Externalization**  
> Harness=OS, Model=CPU — 오케스트레이션은 n8n이, 기억은 Mories가 담당합니다.

## 배경

기존 `OrchestrationBlackboard` (384줄, 삭제됨)가 담당하던 Observer 조율 로직을 n8n 워크플로우로 대체합니다.  
Mories MCP 서버(`v0.7.0`)를 외부 HTTP/MCP 프로토콜로 호출하는 방식입니다.

## 워크플로우 목록

| 파일 | 설명 | 트리거 |
|------|------|--------|
| `mories_observer_workflow.json` | 활성 태스크 폴링 → 에이전트 디스패치 | 5분 주기 Schedule |

## 설치 방법

### 1. 환경 변수 설정 (n8n)

```bash
# n8n 서버에서 설정
MORIES_MCP_URL=http://localhost:5002    # MCP 서버 주소
AGENT_WEBHOOK_URL=http://your-agent/webhook  # 에이전트 수신 주소
```

### 2. 워크플로우 Import

```bash
# n8n CLI 사용
n8n import:workflow --input=n8n/mories_observer_workflow.json

# 또는 n8n UI → Settings → Import from File
```

### 3. HTTP Header Auth 설정 (선택)

`Search Active Tasks` 노드에서 `X-API-Key` 헤더를 통한 MCP 서버 인증을 설정하세요.

## 워크플로우 흐름

```
[Schedule: 5분마다]
    │
    ▼
[mories_search(status=in_progress)]  ← Mories MCP 호출 (Layer 1)
    │
    ├─ 결과 없음 → [Log & 종료]
    │
    └─ 결과 있음
        │
        ▼
    [Split Tasks] → for each task:
        │
        ▼
    [mories_detail(uuid)]  ← Mories MCP 호출 (Layer 3)
        │
        ├─ priority > 3 → [Skip (저우선순위)]
        │
        └─ priority <= 3 (고우선순위)
            │
            ▼
        [POST → Agent Webhook]  ← 에이전트에 태스크 디스패치
            │
            ▼
        [mories_update_status(status=completed)]  ← 완료 처리
```

## MCP API 사용 예제

```bash
# 활성 태스크 검색
curl -X POST http://localhost:5002/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "mories_search",
      "arguments": {"query": "active", "status": "in_progress"}
    },
    "id": 1
  }'

# 태스크 완료 처리
curl -X POST http://localhost:5002/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "mories_update_status",
      "arguments": {"uuid": "<task-uuid>", "status": "completed"}
    },
    "id": 2
  }'
```

## Phase 4 아키텍처 원칙

- **Mories**: 기억의 저장·검색·그래프화에만 집중
- **n8n**: 에이전트 조율, 조건 분기, 알림 등 오케스트레이션 담당
- **에이전트(Claude 등)**: MCP 도구를 통해 Mories와 직접 상호작용
