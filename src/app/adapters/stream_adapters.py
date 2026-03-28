"""
Stream data adapters: Webhook, Kafka, SSE, REST-polling.
"""
import os
import hmac
import hashlib
import logging
import time
from datetime import datetime
from queue import Queue
from typing import Dict, Any, Iterator

from .base import SourceAdapter, StreamSourceAdapter, IngestionResult, SourceType

logger = logging.getLogger(__name__)


class WebhookAdapter(SourceAdapter):
    """
    Receive real-time data via HTTP POST (Webhooks).
    Register a Flask endpoint that pushes payloads into an internal queue.
    """

    def __init__(self):
        self._webhook_queue: Queue = Queue()
        self._secret = os.environ.get("WEBHOOK_SECRET", "")

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.startswith("webhook://")

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        raise NotImplementedError("Use register_endpoint() + ingest_stream() for webhooks")

    def ingest_stream(self, source_ref: str, **kwargs) -> Iterator[IngestionResult]:
        """Block-wait on internal queue and yield payloads as IngestionResults."""
        while True:
            payload = self._webhook_queue.get()  # blocking
            yield IngestionResult(
                text=self._payload_to_text(payload),
                metadata={
                    "source": source_ref,
                    "format": "webhook",
                    "received_at": datetime.now().isoformat(),
                },
                source_type=SourceType.STREAM,
            )

    def register_endpoint(self, app, path: str = "/api/webhook/ingest"):
        """Register a Flask route to accept webhook POSTs."""
        from flask import request, jsonify

        @app.route(path, methods=['POST'])
        def webhook_ingest():
            # HMAC Signature verification (if secret is set)
            if self._secret:
                signature = request.headers.get('X-Webhook-Signature', '')
                expected = hmac.new(
                    self._secret.encode(),
                    request.data,
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    return jsonify({"error": "Invalid signature"}), 401

            payload = request.get_json(silent=True)
            if payload is None:
                return jsonify({"error": "Invalid JSON body"}), 400

            self._webhook_queue.put(payload)
            return jsonify({"status": "accepted"}), 202

    @staticmethod
    def _payload_to_text(payload: Dict) -> str:
        """Convert a webhook JSON payload to plaintext."""
        if isinstance(payload, dict):
            parts = []
            for k, v in payload.items():
                parts.append(f"{k}: {v}")
            return ". ".join(parts)
        return str(payload)


class KafkaStreamAdapter(StreamSourceAdapter):
    """
    Consume messages from Apache Kafka topics.
    Useful for injecting real-time news / events during simulation.
    """

    def __init__(self):
        self.consumer = None
        self._connected = False

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.startswith("kafka://")

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        raise NotImplementedError("Use connect() + ingest_stream() for Kafka")

    def connect(self, config: Dict[str, Any]) -> None:
        try:
            from confluent_kafka import Consumer
        except ImportError:
            raise ImportError("confluent-kafka is required. pip install confluent-kafka")

        self.consumer = Consumer({
            'bootstrap.servers': config['bootstrap_servers'],
            'group.id': config.get('group_id', 'mirofish-ingest'),
            'auto.offset.reset': config.get('auto_offset_reset', 'latest'),
        })
        self.consumer.subscribe(config['topics'])
        self._connected = True
        logger.info("Kafka consumer connected to %s, topics: %s",
                     config['bootstrap_servers'], config['topics'])

    def disconnect(self) -> None:
        if self.consumer:
            self.consumer.close()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def ingest_stream(self, source_ref: str, **kwargs) -> Iterator[IngestionResult]:
        if not self._connected or not self.consumer:
            raise RuntimeError("Kafka consumer is not connected. Call connect() first.")

        while self._connected:
            msg = self.consumer.poll(timeout=1.0)
            if msg is None or msg.error():
                continue

            text = msg.value().decode('utf-8')
            yield IngestionResult(
                text=text,
                metadata={
                    "source": f"kafka://{msg.topic()}/{msg.partition()}",
                    "offset": msg.offset(),
                    "timestamp": msg.timestamp()[1] if msg.timestamp() else None,
                    "format": "kafka",
                },
                source_type=SourceType.STREAM,
            )


class RestPollingAdapter(SourceAdapter):
    """
    Poll a REST API at regular intervals to collect data.
    Supports JSON responses and converts them via JsonAdapter logic.
    """

    def can_handle(self, source_ref: str) -> bool:
        # Only handle if explicitly marked or when called directly
        return source_ref.startswith(("http://", "https://"))

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        import requests as req

        method = kwargs.get('method', 'GET')
        headers = kwargs.get('headers', {})
        params = kwargs.get('params', {})

        response = req.request(method, source_ref, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '')

        if 'json' in content_type:
            data = response.json()
            from .structured_adapters import JsonAdapter
            import tempfile, json

            tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
            json.dump(data, tmp)
            tmp.close()
            json_adapter = JsonAdapter()
            result = json_adapter.ingest(tmp.name, **kwargs)
            os.unlink(tmp.name)
            result.metadata["source"] = source_ref
            result.metadata["format"] = "rest_api"
            return result
        else:
            return IngestionResult(
                text=response.text,
                metadata={"source": source_ref, "format": "rest_api"},
                source_type=SourceType.API,
            )

    def ingest_stream(self, source_ref: str, **kwargs) -> Iterator[IngestionResult]:
        """Polling-based stream: call API every `poll_interval` seconds."""
        interval = kwargs.get('poll_interval', 60)
        while True:
            try:
                yield self.ingest(source_ref, **kwargs)
            except Exception as e:
                logger.warning(f"REST polling failed for {source_ref}: {e}")
            time.sleep(interval)
