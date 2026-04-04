"""
mories_mcp_backend.py — Mories MCP를 통한 실제 메모리 백엔드

MemoryBridge의 pluggable backend 구현체.
Mories MCP 도구(mories_ingest, mories_harness_record, mories_record_reflection)를
호출하여 하네스 경험을 중앙 지식 그래프에 실제로 저장한다.

이 모듈은 MCP 런타임(Antigravity 등)이 아닌 **서버 사이드**에서
직접 Mories API(REST 또는 MCP)를 호출하는 경우를 위한 어댑터이다.

작성: 2026-04-04
"""
import logging
import json
from typing import Dict, Any, List, Optional

logger = logging.getLogger("harness.mories_mcp_backend")


class MoriesMcpBackend:
    """
    Mories MCP 도구 호출을 시뮬레이션하는 백엔드.

    실제 배포 시 mcp_client를 주입받아 MCP 프로토콜로 통신하거나,
    REST API 엔드포인트로 직접 호출할 수 있다.
    """

    def __init__(self, mcp_client=None, api_base_url: str = ""):
        """
        Args:
            mcp_client: MCP 프로토콜 클라이언트 (있는 경우)
            api_base_url: Mories REST API base URL (예: http://localhost:8000)
        """
        self.mcp_client = mcp_client
        self.api_base_url = api_base_url
        self._fallback_store: list = []  # MCP/API 불가 시 로컬 저장

    def ingest(
        self,
        content: str,
        salience: float,
        scope: str,
        source: str,
        metadata: Dict[str, Any],
    ) -> dict:
        """
        Mories에 경험을 ingest한다.
        MCP: mories_ingest / REST: POST /api/memory/ingest
        """
        payload = {
            "content": content,
            "salience": salience,
            "scope": scope,
            "source": source,
        }

        # Strategy 1: MCP 클라이언트
        if self.mcp_client:
            try:
                return self.mcp_client.call(
                    "mories_ingest", **payload
                )
            except Exception as e:
                logger.warning(f"MCP ingest failed: {e}")

        # Strategy 2: REST API
        if self.api_base_url:
            try:
                import requests
                resp = requests.post(
                    f"{self.api_base_url}/api/memory/ingest",
                    json=payload,
                    timeout=10,
                )
                if resp.ok:
                    return resp.json()
                logger.warning(f"REST ingest failed: {resp.status_code}")
            except Exception as e:
                logger.warning(f"REST ingest error: {e}")

        # Strategy 3: 로컬 폴백
        self._fallback_store.append({"type": "ingest", **payload})
        logger.info("Stored to local fallback (no MCP/API available)")
        return {"status": "fallback_stored", "id": f"local_{len(self._fallback_store)}"}

    def record_pattern(
        self,
        domain: str,
        tool_chain: List[str],
        trigger: str,
        metadata: Dict[str, Any],
    ) -> dict:
        """
        하네스 패턴을 Mories에 등록한다.
        MCP: mories_harness_record
        """
        payload = {
            "domain": domain,
            "tool_chain": tool_chain,
            "trigger": trigger,
            "tags": [domain, "auto-captured"],
        }

        if self.mcp_client:
            try:
                return self.mcp_client.call(
                    "mories_harness_record", **payload
                )
            except Exception as e:
                logger.warning(f"MCP pattern record failed: {e}")

        if self.api_base_url:
            try:
                import requests
                resp = requests.post(
                    f"{self.api_base_url}/api/harness/record",
                    json=payload,
                    timeout=10,
                )
                if resp.ok:
                    return resp.json()
            except Exception as e:
                logger.warning(f"REST pattern record error: {e}")

        self._fallback_store.append({"type": "pattern", **payload})
        return {"status": "fallback_stored"}

    def record_reflection(
        self,
        event: str,
        lesson: str,
        domain: str,
        severity: str,
    ) -> dict:
        """
        교훈(reflection)을 Mories에 기록한다.
        MCP: mories_record_reflection
        """
        payload = {
            "event": event,
            "lesson": lesson,
            "domain": domain,
            "severity": severity,
        }

        if self.mcp_client:
            try:
                return self.mcp_client.call(
                    "mories_record_reflection", **payload
                )
            except Exception as e:
                logger.warning(f"MCP reflection failed: {e}")

        if self.api_base_url:
            try:
                import requests
                resp = requests.post(
                    f"{self.api_base_url}/api/reflection/record",
                    json=payload,
                    timeout=10,
                )
                if resp.ok:
                    return resp.json()
            except Exception as e:
                logger.warning(f"REST reflection error: {e}")

        self._fallback_store.append({"type": "reflection", **payload})
        return {"status": "fallback_stored"}

    def flush_fallback(self) -> List[dict]:
        """
        로컬 폴백에 쌓인 데이터를 반환하고 비운다.
        연결이 복구된 후 재전송에 사용.
        """
        data = list(self._fallback_store)
        self._fallback_store.clear()
        return data
