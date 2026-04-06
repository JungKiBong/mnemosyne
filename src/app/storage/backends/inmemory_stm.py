import json
import logging
import threading
from typing import Dict, List, Optional

from ..base import BaseSTMBackend
from ..models import STMItem, MemoryConfig

logger = logging.getLogger('mirofish.inmemory_stm')

class InMemorySTMBackend(BaseSTMBackend):
    def __init__(self, config: MemoryConfig):
        self.config = config
        self._stm_buffer: Dict[str, STMItem] = {}
        self._lock = threading.Lock()

    def add(self, item: STMItem) -> None:
        with self._lock:
            if len(self._stm_buffer) >= self.config.stm_max_items:
                self.cleanup()
            self._stm_buffer[item.id] = item

    def list_all(self) -> List[dict]:
        with self._lock:
            self.cleanup()
            return [item.to_dict() for item in self._stm_buffer.values()]

    def get(self, item_id: str) -> Optional[dict]:
        with self._lock:
            item = self._stm_buffer.get(item_id)
            if item and not item.is_expired:
                return item.to_dict()
            return None

    def evaluate(self, item_id: str, salience: float, config: MemoryConfig) -> Optional[dict]:
        with self._lock:
            item = self._stm_buffer.get(item_id)
            if not item:
                return None

            item.salience = max(0.0, min(1.0, salience))
            item.evaluated = True

            if salience >= config.auto_promote_threshold:
                item.evaluation_result = 'promote'
            elif salience <= config.auto_discard_threshold:
                item.evaluation_result = 'discard'
            else:
                item.evaluation_result = 'pending_hitl'

            return item.to_dict()

    def pop(self, item_id: str) -> Optional[STMItem]:
        with self._lock:
            return self._stm_buffer.pop(item_id, None)

    def discard(self, item_id: str) -> bool:
        with self._lock:
            if item_id in self._stm_buffer:
                del self._stm_buffer[item_id]
                return True
            return False

    def cleanup(self) -> int:
        expired = [k for k, v in self._stm_buffer.items() if v.is_expired]
        for k in expired:
            del self._stm_buffer[k]
        return len(expired)
