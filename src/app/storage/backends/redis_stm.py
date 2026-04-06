import json
import logging
import threading
from dataclasses import asdict
from typing import Dict, List, Optional, Any

from ..base import BaseSTMBackend
from ..models import STMItem, MemoryConfig

logger = logging.getLogger('mirofish.redis_stm')

class RedisSTMBackend(BaseSTMBackend):
    def __init__(self, redis_client: Any, config: MemoryConfig):
        self._redis = redis_client
        self.config = config
        self._lock = threading.Lock()

    def _key(self, item_id: str) -> str:
        return f"mories:stm:{item_id}"

    def add(self, item: STMItem) -> None:
        with self._lock:
            self._redis.setex(
                self._key(item.id),
                int(item.ttl),
                json.dumps(asdict(item))
            )

    def list_all(self) -> List[dict]:
        with self._lock:
            items = []
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match="mories:stm:*", count=100)
                for k in keys:
                    data = self._redis.get(k)
                    if data:
                        try:
                            item_dict = json.loads(data)
                            items.append(STMItem(**item_dict).to_dict())
                        except Exception:
                            pass
                if cursor == 0:
                    break
            return items

    def get(self, item_id: str) -> Optional[dict]:
        with self._lock:
            data = self._redis.get(self._key(item_id))
            if data:
                try:
                    item_dict = json.loads(data)
                    return STMItem(**item_dict).to_dict()
                except Exception:
                    return None
            return None

    def evaluate(self, item_id: str, salience: float, config: MemoryConfig) -> Optional[dict]:
        with self._lock:
            data = self._redis.get(self._key(item_id))
            if not data:
                return None
            item_dict = json.loads(data)
            item = STMItem(**item_dict)

            item.salience = max(0.0, min(1.0, salience))
            item.evaluated = True

            if salience >= config.auto_promote_threshold:
                item.evaluation_result = 'promote'
            elif salience <= config.auto_discard_threshold:
                item.evaluation_result = 'discard'
            else:
                item.evaluation_result = 'pending_hitl'

            ttl = self._redis.ttl(self._key(item_id))
            if ttl > 0:
                self._redis.setex(self._key(item_id), ttl, json.dumps(asdict(item)))

            return item.to_dict()

    def pop(self, item_id: str) -> Optional[STMItem]:
        with self._lock:
            data = self._redis.get(self._key(item_id))
            if not data:
                return None
            
            item_dict = json.loads(data)
            item = STMItem(**item_dict)
            self._redis.delete(self._key(item_id))
            return item

    def discard(self, item_id: str) -> bool:
        with self._lock:
            deleted = self._redis.delete(self._key(item_id))
            return deleted > 0

    def cleanup(self) -> int:
        # Redis handles TTLs automatically, so no need for manual cleanup.
        return 0
