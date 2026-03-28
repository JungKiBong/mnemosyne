# AutoResearchClaw × Mories 통합 가이드

이 가이드는 [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw) 자율 연구 에이전트와 Mories 기억 시스템을 통합하여, 연구 간 지식을 축적하고 재사용하는 방법을 설명합니다.

## 통합의 이점

- **중복 작업 방지**: 과거 연구에서 이미 읽은 논문을 다시 검색하지 않고 가져옵니다.
- **실패 패턴 학습**: 이전 실험에서 실패한 파라미터나 접근 방식을 기억하여 실수를 방지합니다.
- **연구 지식망 구축**: 여러 번의 연구 결과, 인사이트, 피어 리뷰 피드백이 하나의 지식 그래프로 연결됩니다.

---

## 방법 1: n8n 워크플로우를 통한 무설정(Zero-config) 통합

가장 권장하는 방식입니다. AutoResearchClaw 측 코드를 수정할 필요 없이, 출력되는 결과물만 Mories으로 자동 수집합니다.

### 1-1. Mories 대시보드에서 워크플로우 배포
1. Mories 웹 대시보드의 **Workflows** 탭으로 이동합니다.
2. `14_researchclaw_ingest.json` 워크플로우를 클릭하여 n8n에 임포트합니다.
3. 임포트된 워크플로우의 Webhook URL을 확인하고 활성화합니다.

### 1-2. AutoResearchClaw 설정 연결
AutoResearchClaw의 `config.arc.yaml`을 직접 수정하지 않고, 서버 측에서 연구 완료 시 발생하는 아티팩트 데이터를 n8n Webhook으로 전송하는 간단한 쉘 또는 파이썬 스크립트를 추가합니다.

예시 (실행 후 훅으로 추가):
```bash
# 연구가 끝난 후 실행되는 스크립트 예시 (예: post_run.sh)
RUN_ID="rc-$(date +%s)"
ARTIFACT_DIR="./artifacts"
TOPIC=$(cat $ARTIFACT_DIR/topic.txt)

# 결과물 파싱 후 Webhook 전송 (curl 방식)
curl -X POST "http://[N8N_WEBHOOK_URL]/researchclaw-ingest" \
     -H "Content-Type: application/json" \
     -d '{
           "run_id": "'"$RUN_ID"'",
           "topic": "'"$TOPIC"'",
           "paper_draft": "'"$(cat $ARTIFACT_DIR/deliverables/paper_draft.md | jshon -s)"'",
           "experiment_results": "'"$(cat $ARTIFACT_DIR/experiment_results.json | jshon -s)"'",
           "reviews": "'"$(cat $ARTIFACT_DIR/peer_reviews.md | jshon -s)"'"
         }'
```

---

## 방법 2: MCP 도구 

AutoResearchClaw가 에이전트 프레임워크(예: LangChain, CrewAI, 자체 Framework)를 사용한다면, Mories의 MCP 도구를 직접 주입하여 **파이프라인 실행 중간**에 기억을 활용하게 할 수 있습니다.

### 통합할 주요 단계 (Stages)

#### Stage 4. LITERATURE_COLLECT & Stage 7. SYNTHESIS
연구 주제에 대한 과거 논문이나 인사이트를 가져옵니다.
* **사용 도구**: `research_context`
* **호출 예시**:
  ```json
  {
    "topic": "Transformer scaling laws",
    "limit": 10,
    "categories": ["paper", "citation", "synthesis"],
    "graph_id": "research-team-alpha"
  }
  ```

#### Stage 21. KNOWLEDGE_ARCHIVE
연구가 끝난 후, 생성된 논문과 교훈을 장기 기억으로 전송합니다.
* **사용 도구**: `research_archive`
* **호출 예시**:
  ```json
  {
    "run_id": "rc-2026-001",
    "topic": "Vision-Language Models Data Efficiency",
    "artifacts": {
      "paper_draft": "# Abstract...",
      "lessons": [{"severity": "high", "content": "batch size must be > 1024"}]
    },
    "graph_id": "research-team-alpha"
  }
  ```

---

## 방법 3: MetaClaw 하이브리드 연동 (고급)

AutoResearchClaw의 실패/복구 모듈인 **MetaClaw**가 생성하는 `skills`(교훈 파일)을 Mories가 직접 감시하고 학습하도록 설정할 수 있습니다.

### 설정 방법
1. AutoResearchClaw `config.arc.yaml`에서 MetaClaw를 활성화합니다:
    ```yaml
    metaclaw_bridge:
      enabled: true
      skills_dir: "~/.metaclaw/skills"
    ```
2. Mories를 구동하는 서버에 파일 감시 스크립트(또는 n8n 파일 감시 노드)를 설정하여 `~/.metaclaw/skills` 디렉토리 내에 `.json` 파일이 생성될 때마다 Mories의 `/api/gateway/webhook`으로 전송합니다.

```json
// 전송 페이로드 예시
{
  "content": "[MetaClaw Skill] GPU Timeout Avoidance\n...",
  "source": "metaclaw:skill",
  "scope": "global",
  "salience": 0.95,
  "metadata": {"type": "lesson_learned", "severity": "high"}
}
```

이렇게 하면, 특정 연구원이 혼자 겪은 실패 교훈(Skill)이 즉시 Mories `global` 스코프로 전개되어, 팀 내 다른 연구원(다른 에이전트)들의 파이프라인에도 자동으로 혜택을 주게 됩니다.
