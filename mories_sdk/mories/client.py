"""
Mories SDK — Python Client for the Mories Cognitive Engine.
"""

import httpx
from typing import Dict, Any, Optional
from .errors import parse_api_error, MoriesError


class MoriesClient:
    """Client for interacting with the Mories Cognitive Engine.

    Supports both context-manager (``with``) and long-lived usage patterns.

    Example (ephemeral)::

        client = MoriesClient(base_url="http://localhost:5001", token="...")
        print(client.health())

    Example (persistent session)::

        with MoriesClient(base_url="http://localhost:5001") as client:
            print(client.search("agents"))
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5001",
        token: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers: Dict[str, str] = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        # Persistent session — created lazily or via context‐manager
        self._client: Optional[httpx.Client] = None

    def _handle_error(self, response: httpx.Response):
        """Raises specific SDK exceptions if the response has an error status code."""
        if not response.is_success:
            try:
                data = response.json()
                if "error" in data:
                    raise parse_api_error(response.status_code, data)
            except ValueError:
                pass # Not JSON
            response.raise_for_status()

    # --- context-manager support ---

    def __enter__(self):
        self._client = httpx.Client(
            headers=self._headers, timeout=self.timeout
        )
        return self

    def __exit__(self, *exc):
        if self._client:
            self._client.close()
            self._client = None

    # --- internal helpers ---

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        if self._client:
            resp = self._client.request(method, url, **kwargs)
        else:
            with httpx.Client(
                headers=self._headers, timeout=self.timeout
            ) as c:
                resp = c.request(method, url, **kwargs)
        self._handle_error(resp)
        return resp

    # --- public API ---

    def info(self) -> Dict[str, Any]:
        """Get the API v1 info."""
        return self._request("GET", "/api/v1/info").json()

    def search(
        self,
        query: str,
        limit: int = 10,
        graph_id: str = "",
    ) -> Dict[str, Any]:
        """Search the Mories knowledge graph."""
        return self._request(
            "POST",
            "/api/v1/search",
            json={"query": query, "limit": limit, "graph_id": graph_id},
        ).json()

    def health(self) -> Dict[str, Any]:
        """Get the health status of the Mories cluster."""
        return self._request("GET", "/api/health").json()

    def ingest(self, content: str, source: str = "sdk", salience: float = 0.7) -> Dict[str, Any]:
        """Ingest content into the Mories knowledge pipeline."""
        return self._request(
            "POST",
            "/api/v1/ingest/pipeline/process",
            json={"content": content, "source": source, "salience": salience},
        ).json()

    def stm_add(self, content: str, source: str = "sdk", ttl: Optional[float] = None) -> Dict[str, Any]:
        """Add an item to Short-Term Memory."""
        payload: Dict[str, Any] = {"content": content, "source": source}
        if ttl is not None:
            payload["ttl"] = ttl
        return self._request("POST", "/api/v1/memory/stm/add", json=payload).json()

    def stm_list(self) -> Dict[str, Any]:
        """List all Short-Term Memory items."""
        return self._request("GET", "/api/v1/memory/stm/list").json()
