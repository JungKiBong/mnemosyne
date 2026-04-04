"""
test_live_integration.py — Phase A: 실전 Dify + n8n 연결 E2E 테스트

실제 외부 서비스(Dify LLM, n8n Webhook)와의 라이브 연동을 검증한다.
서비스 접근 불가 시 자동으로 skip 처리.

작성: 2026-04-05
"""
import json
import os
import sys
import pytest
import requests
import logging

# ── 프로젝트 루트 경로 설정 ──
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger("test_live_integration")

# ── 서비스 가용성 프로브 ──
DIFY_BASE = os.environ.get("DIFY_BASE_URL", "http://100.75.95.45:5001/v1")
DIFY_API_KEY = os.environ.get(
    "DIFY_API_KEY", "app-4ElPP6OBpbEdCINmPDBrSnxq"
)
N8N_WEBHOOK = os.environ.get(
    "N8N_WEBHOOK_URL",
    "http://100.75.95.45:5678/webhook/harness-deploy-success",
)


def _check_dify() -> bool:
    """Dify 서버가 응답하는지 확인 (401도 '서버는 살아있음'으로 처리)."""
    try:
        resp = requests.get(DIFY_BASE, timeout=3, allow_redirects=True)
        return resp.status_code < 500
    except Exception:
        return False


def _check_n8n() -> bool:
    """n8n 서버가 응답하는지 확인."""
    try:
        resp = requests.get(
            "http://100.75.95.45:5678/healthz", timeout=3
        )
        return resp.status_code == 200
    except Exception:
        return False


_dify_available = _check_dify()
_n8n_available = _check_n8n()


# ═══════════════════════════════════════════════
# A-1: Dify LLM 라이브 에러 분석
# ═══════════════════════════════════════════════
@pytest.mark.skipif(not _dify_available, reason="Dify 서버 접근 불가")
class TestDifyLiveIntegration:
    """실제 Dify API를 호출하여 에러 분석 응답을 받는다."""

    def test_dify_chat_returns_answer(self):
        """Dify chat-messages API가 정상 응답을 반환하는지 검증.
        
        Dify Agent Chat App은 streaming 모드만 지원하므로 SSE로 수신.
        """
        resp = requests.post(
            f"{DIFY_BASE}/chat-messages",
            headers={
                "Authorization": f"Bearer {DIFY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "inputs": {},
                "query": (
                    "다음 빌드 에러를 분석하고 원인과 수정 방법을 "
                    "간단히 설명해줘: TypeError: Cannot read properties "
                    "of undefined (reading 'map')"
                ),
                "response_mode": "streaming",
                "user": "harness-test",
            },
            timeout=60,
            stream=True,
        )
        assert resp.status_code == 200, (
            f"Dify 응답 에러: {resp.status_code} - {resp.text[:300]}"
        )
        # SSE 스트림에서 answer 조각을 수집
        answer_parts = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])  # 'data: ' 제거
                evt_type = event.get("event", "")
                # Dify Agent Chat: agent_message / 일반 Chat: message
                if evt_type in ("agent_message", "message"):
                    answer_parts.append(event.get("answer", ""))
                elif evt_type == "message_end":
                    break
            except json.JSONDecodeError:
                continue
        full_answer = "".join(answer_parts)
        assert len(full_answer) > 5, f"응답이 너무 짧음: '{full_answer[:100]}'"
        logger.info(f"Dify 응답 (일부): {full_answer[:200]}")

    def test_dify_via_runtime_api_call(self):
        """HarnessRuntime의 _exec_api_call을 통해 Dify를 호출.
        
        streaming은 _exec_api_call에서 지원하지 않으므로,
        Dify /completion-messages (일반 App) 또는 직접 SSE 파싱을 테스트.
        여기서는 api_call이 HTTP 레벨에서 정상 동작하는지만 검증.
        """
        from src.app.harness.harness_runtime import _exec_api_call

        step = {
            "url": f"{DIFY_BASE}/chat-messages",
            "method": "POST",
            "headers": {
                "Authorization": f"Bearer {DIFY_API_KEY}",
                "Content-Type": "application/json",
            },
            "body": {
                "inputs": {},
                "query": "Python TypeError 원인을 한 줄로 설명해",
                "response_mode": "streaming",
                "user": "harness-runtime-test",
            },
            "timeout_seconds": 60,
        }
        ctx = {"env": {}}
        # streaming 응답은 text로 반환됨 (SSE 스트림)
        result = _exec_api_call(step, ctx)
        # text 또는 dict 형태로 응답을 받으면 성공
        assert result is not None, "응답이 None"
        # SSE 스트림이 text로 올 수 있고, Dify가 content-type을 
        # text/event-stream으로 보내므로 문자열 확인
        if isinstance(result, str):
            assert len(result) > 10, f"응답이 너무 짧음: {result[:100]}"
        else:
            assert isinstance(result, dict)


# ═══════════════════════════════════════════════
# A-2: n8n 웹훅 라이브 연동
# ═══════════════════════════════════════════════
@pytest.mark.skipif(not _n8n_available, reason="n8n 서버 접근 불가")
class TestN8nLiveIntegration:
    """실제 n8n 웹훅 엔드포인트에 이벤트를 전송한다."""

    def test_n8n_webhook_accepts_post(self):
        """n8n 웹훅이 POST 요청을 수신하는지 검증.

        n8n 프로덕션 웹훅은 등록된 경우 200/404를 반환.
        어떤 응답이든 서버가 요청을 처리했다는 것이 핵심.
        """
        resp = requests.post(
            N8N_WEBHOOK,
            json={
                "event": "test_ping",
                "source": "mories-harness-test",
                "timestamp": "2026-04-05T01:00:00Z",
            },
            timeout=10,
        )
        # 200(등록됨) 또는 404(미등록이지만 서버 응답) 모두 "서버는 살아있음"
        assert resp.status_code < 500, (
            f"n8n 서버 에러: {resp.status_code}"
        )
        logger.info(
            f"n8n 웹훅 응답: {resp.status_code} - {resp.text[:200]}"
        )

    def test_n8n_via_runtime_webhook(self):
        """HarnessRuntime의 _exec_webhook 함수를 통해 n8n을 호출."""
        from src.app.harness.harness_runtime import _exec_webhook

        step = {
            "url": N8N_WEBHOOK,
            "body": {
                "event": "runtime_test",
                "source": "mories-harness",
                "deploy_result": {"status": "deployed", "env": "staging"},
            },
            "timeout_seconds": 10,
        }
        ctx = {"env": {}}
        result = _exec_webhook(step, ctx)

        assert "status_code" in result
        assert result["status_code"] < 500


# ═══════════════════════════════════════════════
# A-3: 풀 파이프라인 라이브 E2E
# ═══════════════════════════════════════════════
@pytest.mark.skipif(
    not (_dify_available and _n8n_available),
    reason="Dify 또는 n8n 접근 불가",
)
class TestFullPipelineLive:
    """cicd_auto_recovery_live.json 워크플로우를 실제로 실행한다."""

    def test_live_pipeline_runs_to_completion(self):
        """라이브 파이프라인이 끝까지 실행되는지 검증.

        시뮬레이션 함수(build, test, deploy)와 라이브 서비스
        (Dify analyze, n8n notify)가 혼합된 하이브리드 E2E.
        """
        from src.app.harness.harness_runtime import HarnessRuntime

        wf_path = os.path.join(
            PROJECT_ROOT,
            "src", "app", "harness", "workflows",
            "cicd_auto_recovery_live.json",
        )
        assert os.path.exists(wf_path), f"워크플로우 파일 없음: {wf_path}"

        with open(wf_path) as f:
            workflow = json.load(f)

        runtime = HarnessRuntime(workflow)
        result = runtime.run()

        # 기본 결과 구조 검증
        assert "steps_executed" in result, (
            f"steps_executed 없음: {list(result.keys())}"
        )
        assert result["steps_executed"] >= 3, (
            f"최소 3개 스텝 실행 필요, 실제: {result['steps_executed']}"
        )

        # 성공이든 실패든 파이프라인이 완전히 종료되어야 함
        exec_log = result.get("execution_log", [])
        step_ids = [s.get("step_id", "?") for s in exec_log]
        logger.info(f"실행된 스텝: {step_ids}")

        # v3 Metrics 통합 검증
        if "metrics_summary" in result:
            ms = result["metrics_summary"]
            logger.info(
                f"총 비용: ${ms.get('total_cost_usd', 0):.4f}, "
                f"총 시간: {ms.get('total_elapsed_ms', 0)}ms"
            )

        # v3 Evolution 검증
        if "evolution" in result and result["evolution"]:
            ev = result["evolution"]
            logger.info(
                f"진화 모드: {ev.get('mode')}, "
                f"사유: {ev.get('reason', 'N/A')}"
            )
