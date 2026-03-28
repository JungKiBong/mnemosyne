import os
import requests
import json

MORIES_URL = "http://localhost:5001"
# Mories의 Webhook Gateway 엔드포인트를 통해 직접 Ingest 합니다.
WEBHOOK_URL = f"{MORIES_URL}/api/gateway/webhook"

session_memory_content = """
# 🧠 Mories (전 Mnemosyne) 핵심 아키텍처 및 개발 세션 저장 기록

**작업 일시:** 2026-03-28 (Session ID: 11db367a)
**해결 과제:** AutoResearchClaw 통합 및 "Mories" 리브랜딩, 다중 에이전트 공유망 구축

## 1. Mories 리브랜딩 (Mnemosyne -> Mories)
* **의의:** "Memories"에서 나(Me)를 뺀 **공유 지식과 집단 기억(Global Shared Knowledge)**이라는 철학을 반영.
* **작업사항:** 
  - 코드베이스 전체 48+개 파일 대상 대소문자 매칭 일괄 치환 (Mnemosyne -> Mories).
  - 디렉토리 구조 및 파일 명칭(`01_mories_search.json` 등)에서 모두 `mnemosyne` 문자열 제거 및 `mories`로 완벽 교체 완료.
  - 대시보드 UI, Python Logger 이름 등 시스템 전반부 반영.

## 2. AutoResearchClaw 및 타 에이전트 통합 (Opencode, Nemoclaw 등)
* **n8n 추가 워크플로우:** 
  - `14_researchclaw_ingest.json`: 연구 산출물(논문 초안, 피어 리뷰, 실험 결과)을 메타데이터와 중요도(Salience)를 반영해 기억 그래프로 저장.
  - `15_researchclaw_context.json`: 연구 시작 전 과거 유사 지식을 검색하여 에이전트 프롬프트에 제공.
* **MCP 특화 도구 추가 (`mcp_server/tools.py` 등에 추가):** 
  - `research_context`: 과거 연구 맥락 조회를 위한 API 연동.
  - `research_archive`: 논문 등 다양한 아티팩트를 Batch로 Mories 지식 그래프에 등록.

## 3. Mories Memory Protocol (스킬) 정의 및 플러그인화
* Antigravity 등 다른 PC에서 작동하는 에이전트가 단일된 허브(Mories)의 지식을 공유할 수 있도록 규칙(Skill) 생성.
* **스킬 핵심 지침:** 세션 초기화 시 `mories_search`로 맥락 파악 & 종료 시 `mories_ingest`로 결과 저장.
* **스킬 배포 형태:** `.gemini/antigravity/skills/mories-memory-protocol` 로 관리되며 `mories_skill_bundle.zip` 파일로 추출하여 타 PC 에이전트에 이식이 가능하도록 구축.

## 4. 인프라 실행 편의성 & 안정성 확보
* **실행 셸 (`bin/start_mories.sh`, `bin/stop_mories.sh`):**
  - Mories REST API (Port 5001) 및 공유용 MCP 원격 서버 (SSE mode, Port 3100) 백그라운드 구동.
  - 동작 프로세스의 PID를 `run/*.pid`에 기록하여 완벽히 추적 및 제어.
  - **Fail-safe (좀비 프로세스 킬러):** 만약 포트를 이미 선점 중이면 `lsof`와 `kill -9`를 조합하여 무조건 포트 점유를 해제하도록 `stop` 스크립트 고도화 완료.
  
## 5. Next Steps / Action Items
* 공유된 MCP 주소(`http://<Hub_IP>:3100/mcp`)를 다른 PC의 Agent에 연결하여 멀티 에이전트 협업 테스트를 진행한다.
* AutoResearchClaw나 Nemoclaw가 코딩을 수행 전 이 저장소를 조회하여 이전 코드 리뷰 교훈을 얻는지 확인.
"""

payload = {
    "source": "antigravity_agent",
    "metadata_type": "coding_task",
    "graph_id": "mories_core",
    "content": {
        "title": "Mories 시스템 리브랜딩 및 다중 에이전트 아키텍처 완성 세션",
        "body": session_memory_content
    }
}

try:
    print(f"Sending memory to {WEBHOOK_URL}...")
    response = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"})
    
    if response.status_code == 200 or response.status_code == 202:
        print("[SUCCESS] Memory integrated into Mories Knowledge Graph.")
        print(response.json())
    else:
        print("[ERROR] Failed to ingest memory.")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
except Exception as e:
    print(f"[FATAL] Connection error: {e}")
