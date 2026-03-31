"""
Webhook Event Publisher — Harness Architecture

Publishes Mories internal events to external orchestration layers
(n8n, Dify, custom agents) via HTTP POST webhooks.

Events:
  - memory.stored       — 새 기억이 LTM에 승격될 때
  - memory.promoted     — STM → LTM 자동 승격
  - memory.decayed      — 감쇠 사이클 후 삭제/약화
  - memory.shared       — 에이전트 간 기억 공유
  - graph.updated       — 지식 그래프 엔티티/관계 갱신
  - health.degraded     — 서비스 구성 요소 장애

Configuration (env vars):
  WEBHOOK_URL       — 웹훅 수신 엔드포인트 (쉼표로 복수 설정 가능)
  WEBHOOK_SECRET    — HMAC-SHA256 서명용 시크릿 (선택)
  WEBHOOK_TIMEOUT   — 요청 타임아웃(초), 기본 5
  WEBHOOK_ENABLED   — true/false, 기본 false (명시적 활성화 필요)
"""

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger('mirofish.webhook')


class WebhookPublisher:
    """
    비동기 Webhook 발행기.

    - 모든 발행은 별도 스레드에서 실행 (요청 레이턴시 영향 없음)
    - HMAC-SHA256 서명으로 수신 측 진위 확인 지원
    - 재시도 없음 (fire-and-forget): 외부 오케스트레이션 레이어가 幂等성을 보장해야 함
    """

    _instance: Optional['WebhookPublisher'] = None
    _lock = threading.Lock()

    def __init__(self):
        self.enabled = os.environ.get('WEBHOOK_ENABLED', 'false').lower() == 'true'
        self.secret = os.environ.get('WEBHOOK_SECRET', '')
        self.timeout = int(os.environ.get('WEBHOOK_TIMEOUT', '5'))

        raw_urls = os.environ.get('WEBHOOK_URL', '')
        self.urls: List[str] = [u.strip() for u in raw_urls.split(',') if u.strip()]

        if self.enabled and not self.urls:
            logger.warning("WEBHOOK_ENABLED=true but WEBHOOK_URL is not set. Webhooks disabled.")
            self.enabled = False

        if self.enabled:
            logger.info(f"Webhook publisher active → {self.urls}")

    @classmethod
    def get_instance(cls) -> 'WebhookPublisher':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ──────────────────────────────
    # Public API
    # ──────────────────────────────

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        이벤트를 발행합니다. 비동기(fire-and-forget).

        Args:
            event_type: 이벤트 종류 (e.g. 'memory.stored')
            payload:    이벤트 페이로드 (JSON-serializable dict)
        """
        if not self.enabled:
            return

        body = {
            'event': event_type,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'payload': payload,
        }

        for url in self.urls:
            t = threading.Thread(
                target=self._send,
                args=(url, body),
                name=f"webhook-{event_type}",
                daemon=True,
            )
            t.start()

    # ──────────────────────────────
    # Typed Event Helpers
    # ──────────────────────────────

    def memory_stored(self, uuid: str, content_preview: str, scope: str,
                      salience: float, source: str = 'agent') -> None:
        self.publish('memory.stored', {
            'uuid': uuid,
            'content_preview': content_preview[:200],
            'scope': scope,
            'salience': salience,
            'source': source,
        })

    def memory_promoted(self, stm_id: str, ltm_uuid: str, salience: float,
                        scope: str = 'personal') -> None:
        self.publish('memory.promoted', {
            'stm_id': stm_id,
            'ltm_uuid': ltm_uuid,
            'salience': salience,
            'scope': scope,
        })

    def memory_decayed(self, removed_count: int, weakened_count: int,
                       cycle_id: str = '') -> None:
        self.publish('memory.decayed', {
            'removed_count': removed_count,
            'weakened_count': weakened_count,
            'cycle_id': cycle_id,
        })

    def memory_shared(self, uuid: str, from_agent: str,
                      target_scope: str) -> None:
        self.publish('memory.shared', {
            'uuid': uuid,
            'from_agent': from_agent,
            'target_scope': target_scope,
        })

    def graph_updated(self, graph_id: str, entities_added: int,
                      relations_added: int) -> None:
        self.publish('graph.updated', {
            'graph_id': graph_id,
            'entities_added': entities_added,
            'relations_added': relations_added,
        })

    def batch_started(self, job_id: str, source_count: int) -> None:
        self.publish('batch.started', {
            'job_id': job_id,
            'source_count': source_count,
        })

    def batch_completed(self, job_id: str, success_count: int,
                        fail_count: int) -> None:
        self.publish('batch.completed', {
            'job_id': job_id,
            'success_count': success_count,
            'fail_count': fail_count,
        })

    def health_degraded(self, component: str, detail: str) -> None:
        self.publish('health.degraded', {
            'component': component,
            'detail': detail,
        })

    # ──────────────────────────────
    # Internal
    # ──────────────────────────────

    def _sign(self, body_bytes: bytes) -> str:
        """HMAC-SHA256 서명 생성."""
        return hmac.new(
            self.secret.encode('utf-8'),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

    def _send(self, url: str, body: Dict[str, Any]) -> None:
        """단일 URL로 웹훅을 발송합니다 (동기, 별도 스레드에서 호출)."""
        try:
            body_bytes = json.dumps(body, ensure_ascii=False, default=str).encode('utf-8')
            headers = {
                'Content-Type': 'application/json',
                'X-Mories-Event': body.get('event', 'unknown'),
                'X-Mories-Timestamp': body.get('timestamp', ''),
            }
            if self.secret:
                headers['X-Mories-Signature'] = f"sha256={self._sign(body_bytes)}"

            resp = requests.post(
                url,
                data=body_bytes,
                headers=headers,
                timeout=self.timeout,
            )
            if resp.status_code >= 400:
                logger.warning(
                    f"Webhook to {url} returned {resp.status_code}: {resp.text[:200]}"
                )
            else:
                logger.debug(f"Webhook [{body['event']}] → {url} OK ({resp.status_code})")
        except requests.exceptions.Timeout:
            logger.warning(f"Webhook to {url} timed out (>{self.timeout}s)")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Webhook to {url} connection failed: {e}")
        except Exception as e:
            logger.error(f"Webhook send error to {url}: {e}", exc_info=True)


# Convenience access
def get_webhook() -> WebhookPublisher:
    return WebhookPublisher.get_instance()
