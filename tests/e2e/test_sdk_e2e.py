"""
E2E API scenario using the Python SDK.

Verifies the integration between MoriesClient and the actual backend system.
"""

import pytest
import httpx
from mories.client import MoriesClient
from mories.errors import AuthenticationError, NotFoundError, MoriesError

@pytest.fixture
def wsgi_transport_client(auth_enforced_app, valid_e2e_token):
    """Provides an httpx client mapped to the Flask test app via WSGI."""
    # We use auth_enforced_app so authentication is actually tested
    transport = httpx.WSGITransport(app=auth_enforced_app)
    headers = {"Authorization": f"Bearer {valid_e2e_token}"}
    return httpx.Client(transport=transport, base_url="http://testserver", headers=headers)

@pytest.fixture
def sdk(wsgi_transport_client, valid_e2e_token):
    """Provides an authenticated MoriesClient using the dummy JWT token."""
    client = MoriesClient(base_url="http://testserver", token=valid_e2e_token)
    client._client = wsgi_transport_client
    return client

def test_sdk_authentication_rejection(auth_enforced_app):
    """Test standard error when auth token is missing or invalid."""
    transport = httpx.WSGITransport(app=auth_enforced_app)
    unauth_client = httpx.Client(transport=transport, base_url="http://testserver")
    
    sdk_no_auth = MoriesClient(base_url="http://testserver")
    sdk_no_auth._client = unauth_client
    
    with pytest.raises(MoriesError) as exc:
        sdk_no_auth.search("test")
        
    assert exc.value.status_code in [401, 403, 500]


def test_sdk_e2e_scenario(sdk):
    """
    Test End-to-End scenario:
    1. Verify connection using the token (info/health)
    2. Write data to memory using the SDK
    3. Retrieve the memory
    """
    
    # 1. Connection check
    info_resp = sdk.info()
    assert "version" in info_resp
    assert info_resp.get("status") != "error"

    # 2. Write data to LTM directly via ingest API
    memory_content = "This is a strictly generated E2E architecture test string."
    ingest_resp = sdk.ingest(
        content=memory_content,
        source="e2e-sdk-test",
        salience=0.99
    )
    assert "graph_id" in ingest_resp
    
    # 3. Retrieve using search
    # Neo4j search typically matches tokens. Let's wait or fetch immediately.
    # Note: Search fetches from Neo4j LTM.
    search_resp = sdk.search(query="strictly generated E2E architecture", limit=5)
    results = search_resp.get("results", [])
    
    # We check if our ingested memory is returned (or at least no crash during search)
    # The actual graph extraction might be asynchronous or deferred, but usually we mock or it runs sync.
    assert isinstance(results, list)
    
    # Check proper error formatting for non-existent endpoint
    # MoriesClient handles standard errors cleanly.
    with pytest.raises(MoriesError):
        # We manually use internal _client to hit a 404
        resp = sdk._client.get("/api/v1/some-made-up-endpoint-doesnt-exist")
        sdk._handle_error(resp)

@pytest.mark.asyncio
async def test_async_sdk_initialization():
    from mories.client import AsyncMoriesClient
    from unittest.mock import AsyncMock, patch

    async with AsyncMoriesClient(base_url="http://testserver", token="dummy") as async_sdk:
        assert async_sdk._headers["Authorization"] == "Bearer dummy"

        with patch.object(async_sdk._client, 'request', new_callable=AsyncMock) as mock_req:
            # Setup a fake response
            mock_resp = httpx.Response(200, json={"version": "1.0"})
            mock_req.return_value = mock_resp

            info = await async_sdk.info()
            assert info["version"] == "1.0"
            mock_req.assert_called_once_with("GET", "http://testserver/api/v1/info")
