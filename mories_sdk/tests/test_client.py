"""
Mories SDK 단위 테스트 — MoriesClient

MoriesClient의 HTTP 요청 동작을 httpx mock으로 검증합니다.
외부 서버 의존 없이 실행 가능합니다.
"""

import pytest
import httpx
from unittest.mock import patch, MagicMock
from mories.client import MoriesClient


# ─────────────────────────────────────────────
# 테스트 픽스처
# ─────────────────────────────────────────────

@pytest.fixture
def client():
    """기본 MoriesClient 인스턴스"""
    return MoriesClient(base_url="http://test-server:5050", timeout=5.0)


@pytest.fixture
def auth_client():
    """JWT 토큰이 포함된 MoriesClient 인스턴스"""
    return MoriesClient(
        base_url="http://test-server:5050",
        token="test-jwt-token",
        timeout=5.0,
    )


def _mock_response(json_data, status_code=200):
    """httpx.Response 목 객체 생성 헬퍼"""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ─────────────────────────────────────────────
# 초기화 테스트
# ─────────────────────────────────────────────

class TestClientInit:
    """MoriesClient 초기화 동작 검증"""

    def test_default_values(self):
        """기본값: base_url 후행 슬래시 제거, 헤더 설정"""
        c = MoriesClient(base_url="http://localhost:5050/")
        assert c.base_url == "http://localhost:5050"
        assert c._headers["Content-Type"] == "application/json"
        assert "Authorization" not in c._headers

    def test_token_header(self, auth_client):
        """토큰 전달 시 Authorization 헤더 설정 확인"""
        assert auth_client._headers["Authorization"] == "Bearer test-jwt-token"

    def test_timeout_setting(self, client):
        """타임아웃 값 설정 확인"""
        assert client.timeout == 5.0

    def test_no_initial_session(self, client):
        """초기 상태에서는 내부 httpx.Client 없음"""
        assert client._client is None


# ─────────────────────────────────────────────
# 컨텍스트 매니저 테스트
# ─────────────────────────────────────────────

class TestContextManager:
    """with문을 사용한 세션 관리 동작 검증"""

    def test_enter_creates_session(self, client):
        """__enter__에서 httpx.Client 생성"""
        with patch("mories.client.httpx.Client") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            
            result = client.__enter__()
            assert result is client
            assert client._client is mock_instance

    def test_exit_closes_session(self, client):
        """__exit__에서 httpx.Client 정리"""
        mock_session = MagicMock()
        client._client = mock_session
        
        client.__exit__(None, None, None)
        mock_session.close.assert_called_once()
        assert client._client is None


# ─────────────────────────────────────────────
# API 메서드 테스트
# ─────────────────────────────────────────────

class TestAPIMethods:
    """각 API 메서드의 올바른 HTTP 요청 검증"""

    @patch("mories.client.httpx.Client")
    def test_health(self, MockClient, client):
        """health() — GET /api/health"""
        mock_resp = _mock_response({"status": "ok", "neo4j": "connected"})
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.request.return_value = mock_resp
        MockClient.return_value = mock_ctx

        result = client.health()
        assert result["status"] == "ok"
        mock_ctx.request.assert_called_once_with(
            "GET", "http://test-server:5050/api/health"
        )

    @patch("mories.client.httpx.Client")
    def test_info(self, MockClient, client):
        """info() — GET /api/v1/info"""
        mock_resp = _mock_response({"version": "v1", "endpoints": []})
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.request.return_value = mock_resp
        MockClient.return_value = mock_ctx

        result = client.info()
        assert result["version"] == "v1"

    @patch("mories.client.httpx.Client")
    def test_search(self, MockClient, client):
        """search() — POST /api/search (파라미터 전달 검증)"""
        mock_resp = _mock_response({"results": [{"name": "test", "salience": 0.8}]})
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.request.return_value = mock_resp
        MockClient.return_value = mock_ctx

        result = client.search("아키텍처 결정", limit=5)
        assert len(result["results"]) == 1
        mock_ctx.request.assert_called_once_with(
            "POST",
            "http://test-server:5050/api/v1/search",
            json={"query": "아키텍처 결정", "limit": 5, "graph_id": ""},
        )

    @patch("mories.client.httpx.Client")
    def test_ingest(self, MockClient, client):
        """ingest() — POST /api/ingest/text"""
        mock_resp = _mock_response({"success": True, "uuid": "abc-123"})
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.request.return_value = mock_resp
        MockClient.return_value = mock_ctx

        result = client.ingest("테스트 내용", source="unit-test", salience=0.9)
        assert result["success"] is True
        mock_ctx.request.assert_called_once_with(
            "POST",
            "http://test-server:5050/api/v1/ingest/pipeline/process",
            json={"content": "테스트 내용", "source": "unit-test", "salience": 0.9},
        )

    @patch("mories.client.httpx.Client")
    def test_stm_add(self, MockClient, client):
        """stm_add() — POST /api/memory/stm (TTL 선택적 전달)"""
        mock_resp = _mock_response({"id": "stm-123"})
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.request.return_value = mock_resp
        MockClient.return_value = mock_ctx

        # TTL 없이 호출
        result = client.stm_add("기억 내용")
        assert result["id"] == "stm-123"
        call_args = mock_ctx.request.call_args
        payload = call_args[1]["json"]
        assert "ttl" not in payload

    @patch("mories.client.httpx.Client")
    def test_stm_add_with_ttl(self, MockClient, client):
        """stm_add() — TTL 파라미터 포함 시 payload에 반영"""
        mock_resp = _mock_response({"id": "stm-456"})
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.request.return_value = mock_resp
        MockClient.return_value = mock_ctx

        result = client.stm_add("기억 내용", ttl=3600.0)
        call_args = mock_ctx.request.call_args
        payload = call_args[1]["json"]
        assert payload["ttl"] == 3600.0

    @patch("mories.client.httpx.Client")
    def test_stm_list(self, MockClient, client):
        """stm_list() — GET /api/memory/stm"""
        mock_resp = _mock_response({"items": [], "count": 0})
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.request.return_value = mock_resp
        MockClient.return_value = mock_ctx

        result = client.stm_list()
        assert result["count"] == 0


# ─────────────────────────────────────────────
# 세션 기반 요청 테스트
# ─────────────────────────────────────────────

class TestSessionBasedRequest:
    """컨텍스트 매니저 세션으로 호출 시 행동 검증"""

    def test_uses_existing_session(self, client):
        """_client가 존재하면 해당 세션으로 요청"""
        mock_session = MagicMock()
        mock_resp = _mock_response({"status": "ok"})
        mock_session.request.return_value = mock_resp
        client._client = mock_session

        result = client.health()
        assert result["status"] == "ok"
        mock_session.request.assert_called_once()


# ─────────────────────────────────────────────
# 에러 핸들링 테스트
# ─────────────────────────────────────────────

class TestErrorHandling:
    """HTTP 에러 시 예외 전파 검증"""

    @patch("mories.client.httpx.Client")
    def test_http_error_raises(self, MockClient, client):
        """서버 에러(4xx/5xx) 시 MoriesError(NotFoundError) 발생"""
        from mories.errors import NotFoundError
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.is_success = False
        mock_resp.status_code = 404
        mock_resp.json.return_value = {
            "error": {"code": "NOT_FOUND", "message": "Item missing", "details": {}}
        }
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_resp,
        )
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ctx.request.return_value = mock_resp
        MockClient.return_value = mock_ctx

        with pytest.raises(NotFoundError) as exc:
            client.health()
        assert exc.value.status_code == 404
        assert exc.value.code == "NOT_FOUND"
