import os
import pytest
from unittest.mock import patch, MagicMock

from src.app.harness.harness_runtime import HarnessRuntime

def test_api_call_thin_bridge():
    """
    Dify API 연동을 에뮬레이션하는 Thin Bridge 검증.
    api_call 스텝이 외부 요청을 하고 결과를 context에 저장하는지 확인.
    """
    workflow = {
        "harness_id": "harness_thin_bridge_api",
        "domain": "test",
        "env": {
            "DIFY_API_KEY": "test-sk-1234"
        },
        "steps": [
            {
                "id": "step_dify",
                "type": "api_call",
                "method": "POST",
                "url": "https://api.dify.ai/v1/chat-messages",
                "headers": {
                    "Authorization": "Bearer ${env.DIFY_API_KEY}",
                    "Content-Type": "application/json"
                },
                "body": {
                    "inputs": {},
                    "query": "Hello Dify",
                    "user": "mories-harness"
                },
                "output_key": "dify_response"
            },
            {
                "id": "step_branch",
                "type": "branch",
                "condition": "'${step_dify.dify_response.answer}' != 'null'",
                "then": "step_end",
                "else": "step_end"
            },
            {
                "id": "step_end",
                "type": "end"
            }
        ]
    }

    # 외부 요청을 Mocking
    with patch("src.app.harness.harness_runtime.requests.request") as mock_request:
        # Dify의 전형적인 응답 Mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "event": "message",
            "message_id": "msg-123",
            "conversation_id": "conv-456",
            "answer": "Hi from Dify!"
        }
        mock_request.return_value = mock_response

        # 런타임 실행 (이전 상태가 있을 경우를 대비해 임시 상태 경로 설정)
        workflow["state_storage"] = {"type": "memory", "path": "/tmp/thin_bridge_test_1"}
        runtime = HarnessRuntime(workflow)
        result = runtime.run()

        # 1. 실행 성공 확인
        assert result["success"] is True

        # 2. Mock이 정상적으로 호출되었고 변수 치환이 치루어졌는지 확인
        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        assert call_args[0] == "POST"
        assert call_args[1] == "https://api.dify.ai/v1/chat-messages"
        
        # 'Bearer test-sk-1234'로 치환되었어야 함
        assert call_kwargs["headers"]["Authorization"] == "Bearer test-sk-1234"

        # 3. 브랜치가 조건(dify_response.answer != null)을 통과해 step_end까지 실행되었는지 확인
        executed_steps = [s["step_id"] for s in result["execution_log"]]
        assert "step_dify" in executed_steps
        assert "step_end" in executed_steps

        # 4. 컨텍스트(문맥)에 외부 API 결과가 제대로 담겼는지 확인
        assert "step_dify" in runtime.context
        assert runtime.context["step_dify"]["dify_response"]["answer"] == "Hi from Dify!"

def test_webhook_thin_bridge():
    """
    n8n Webhook 연동을 에뮬레이션하는 Thin Bridge 검증.
    """
    workflow = {
        "harness_id": "harness_thin_bridge_webhook",
        "domain": "test",
        "env": {
            "N8N_WEBHOOK_URL": "http://n8n.local/webhook/trigger"
        },
        "steps": [
            {
                "id": "step_n8n",
                "type": "webhook",
                "url": "${env.N8N_WEBHOOK_URL}",
                "body": {
                    "event": "mories_harness_started",
                    "harness_id": "harness_thin_bridge_webhook"
                },
                "output_key": "n8n_result"
            },
            {
                "id": "step_end",
                "type": "end"
            }
        ]
    }

    # 웹훅용 requests.post Mocking
    with patch("src.app.harness.harness_runtime.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Webhook accepted"
        mock_post.return_value = mock_response

        workflow["state_storage"] = {"type": "memory", "path": "/tmp/thin_bridge_test_2"}
        runtime = HarnessRuntime(workflow)
        result = runtime.run()

        # 1. 실행 성공 확인
        assert result["success"] is True

        # 2. Webhook URL 변수 치환 확인
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args
        assert call_args[0] == "http://n8n.local/webhook/trigger"
        assert call_kwargs["json"]["event"] == "mories_harness_started"

        # 3. 컨텍스트 확인
        assert runtime.context["step_n8n"]["n8n_result"]["status_code"] == 200
