from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import threading
import time
import logging

from app.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

@dataclass
class OutboxEntry:
    action: str          # "add", "delete", "profile_update"
    graph_id: str
    text: str
    metadata: dict
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3


class OutboxWorker:
    """Asynchronous worker for eventually consistent transfers to Supermemory."""
    
    def __init__(self, supermemory_client, circuit_breaker: CircuitBreaker):
        self.sm = supermemory_client
        self.cb = circuit_breaker
        self.queue = deque()
        self.dead_letter = []
        self._running = False
        self._thread = None
    
    def enqueue(self, entry: OutboxEntry):
        self.queue.append(entry)
    
    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._process_loop, daemon=True)
            self._thread.start()
            logger.info("Outbox worker started.")
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _process_loop(self):
        while self._running:
            if not self.queue:
                time.sleep(0.5)
                continue
            
            entry = self.queue.popleft()
            try:
                # Call SM wrapper method safely via Circuit Breaker
                if entry.action == "add":
                    self.cb.call(
                        self.sm.add,
                        content=entry.text,
                        container_tag=entry.graph_id,
                        metadata=entry.metadata
                    )
                else:
                    logger.warning(f"Unknown outbox action: {entry.action}")
                
                logger.debug(f"Outbox: sent to SM [{entry.action}] {entry.graph_id}")
                
            except CircuitOpenError:
                # Put back and sleep longer
                self.queue.appendleft(entry)
                time.sleep(self.cb.recovery_timeout)
            except Exception as e:
                entry.retry_count += 1
                if entry.retry_count < entry.max_retries:
                    backoff = 2 ** entry.retry_count
                    logger.warning(
                        f"Outbox: retry {entry.retry_count}/{entry.max_retries} "
                        f"in {backoff}s — {e}"
                    )
                    time.sleep(backoff)
                    self.queue.appendleft(entry)
                else:
                    logger.error(f"Outbox: DEAD LETTER [{entry.action}] {entry.graph_id} — {e}")
                    self.dead_letter.append(entry)
    
    def get_dead_letters(self) -> list:
        return self.dead_letter.copy()
