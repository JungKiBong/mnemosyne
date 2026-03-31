# n8n Harness Integration Guide

이 가이드는 Mories Memory System이 방출하는 Webhook 이벤트를 n8n에서 수신하고 안전하게 오케스트레이션(예: Slack 전송)하기 위한 방법을 설명합니다.

## 1. 개요
Mories가 단기기억(STM)을 장기기억(LTM)으로 승격(`memory.promoted`)시키거나, 기억 감쇠(`memory.decayed`)가 일어날 때마다 지정된 `WEBHOOK_URL`로 비동기 HTTP 요청을 보냅니다.  
n8n은 이를 수신하고 **보안(HMAC-SHA256) 검증** 후 적절한 후속 작업을 처리합니다.

## 2. n8n 워크플로우 임포트 (Import)
1. n8n 대시보드에서 `[+] Add Workflow`를 클릭합니다.
2. 새 워크플로우 페이지에서 오른쪽 상단의 메뉴(`...`)를 누르고 **"Import from File"** 을 선택합니다.
3. 이 디렉토리에 있는 `mories_harness_workflow.json` 파일을 선택하여 임포트합니다.
4. (선택사항) 임포트 후 `Webhook` 노드를 더블클릭하여 "Test URL" 또는 "Production URL" 주소를 복사합니다.

## 3. Webhook URL Mories 환경변수 적용
`mirofish-supermemory/.env` 파일을 편집하여 n8n의 URL과 Secret을 맞춰줍니다.

```env
WEBHOOK_ENABLED=true
WEBHOOK_URL=http://localhost:5678/webhook/mories-events  # n8n Webhook 노드(Production) URL
WEBHOOK_SECRET=my-development-secret                    # 반드시 안전한 문자열로 변경
WEBHOOK_TIMEOUT=5.0
```
*주의: `WEBHOOK_SECRET`을 변경했다면 n8n의 `Crypto (Verify Signature)` 노드 내부의 `Secret` 값도 동일하게 맞춰야 합니다.*

## 4. 커스텀 Slack 알림 설정 (후속 처리)
템플릿 내의 "Alert: Promoted", "Alert: Decayed" 노드는 `httpRequest` 노드로 세팅되어 있습니다.  
이 노드들을 클릭하여 `url` 설정을 여러분의 실제 **[Slack Incoming Webhook URL]** 로 바꿔주세요.  
(메일 발송, Notion 기록 등 자유롭게 변경하시면 됩니다)

## 5. Webhook 모의 테스트 (RED -> GREEN)
n8n 캔버스에서 `[Test Workflow]`를 눌러 Listening 상태로 만듭니다.  
그런 다음 터미널에서 아래 테스트 스크립트를 실행하여 Mories와 동일한 형태의 HMAC 시그니처가 담긴 이벤트를 발포해 봅니다.

```bash
# 가상환경 내에서 실행
python scripts/test_webhook_harness.py --url "http://localhost:5678/webhook-test/mories-events" --secret "my-development-secret" --event all
```

* `$node["Webhook"].json["headers"]["x-mories-signature"]`와 `$json["generated_signature"]` 값이 동일하여 서명을 통과하는지 확인하세요.
* `event` 필드 값에 따라 Event Router 노드 안에서 라우팅이 잘 분기되는지 확인하세요.
