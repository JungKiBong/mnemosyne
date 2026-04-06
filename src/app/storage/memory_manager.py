"""
Memory Manager — Cognitive Memory Architecture (Phase 7 + 10)

Implements human-like memory mechanisms:
  1. Short-Term Memory (STM) Buffer — temporary storage with TTL
  2. Ebbinghaus Decay — time-based forgetting curve
  3. Retrieval Boost — reinforcement on access
  4. Consolidation — STM → LTM promotion via salience evaluation
  5. Audit Trail — all changes are tracked as MemoryRevision nodes (Phase 10)
  
Refactored (Phase 3 Backend Strategy): Uses BaseSTMBackend and BaseLTMBackend.
"""

import logging
import uuid
import time
from typing import Dict, Any, List, Optional
import threading

from neo4j import GraphDatabase

from ..config import Config
from .models import STMItem, MemoryConfig
from .backends.inmemory_stm import InMemorySTMBackend
from .backends.redis_stm import RedisSTMBackend
from .backends.neo4j_ltm import Neo4jLTMBackend

logger = logging.getLogger('mirofish.memory_manager')

class MemoryManager:
    """
    Core cognitive memory engine (Singleton Facade).
    Delegates to appropriate STM and LTM storage backends.
    """

    _instance: Optional['MemoryManager'] = None
    _initialized: bool = False

    @classmethod
    def get_instance(cls, config: Optional[MemoryConfig] = None,
                     driver=None) -> 'MemoryManager':
        if cls._instance is None:
            cls._instance = cls(config=config, driver=driver)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        if cls._instance is not None:
            try:
                if cls._instance._owns_driver:
                    cls._instance._driver.close()
            except Exception:
                pass
        cls._instance = None
        cls._initialized = False

    def __init__(self, config: Optional[MemoryConfig] = None, driver=None):
        if MemoryManager._initialized and MemoryManager._instance is self:
            return
            
        self.config = config or MemoryConfig()
        
        self._stats = {
            'total_ingested': 0,
            'total_promoted': 0,
            'total_forgotten': 0,
            'total_boosts': 0,
            'total_decays_run': 0,
        }

        if driver is not None:
            self._driver = driver
            self._owns_driver = False
        else:
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
            self._owns_driver = True

        # Initialize LTM Backend
        self._ltm_backend = Neo4jLTMBackend(driver=self._driver, config=self.config)
        self._ltm_backend.ensure_schema()

        # Initialize STM Backend
        self._stm_backend = None
        if hasattr(Config, 'REDIS_URL') and Config.REDIS_URL:
            try:
                import redis
                redis_client = redis.from_url(Config.REDIS_URL, decode_responses=True)
                redis_client.ping()
                self._stm_backend = RedisSTMBackend(redis_client, self.config)
                logger.info("Redis STM backend initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis STM backend: {e}. Falling back to InMemory buffer.")
        
        if not self._stm_backend:
            self._stm_backend = InMemorySTMBackend(self.config)
            logger.info("InMemory STM backend initialized successfully")

        MemoryManager._initialized = True
        logger.info("MemoryManager singleton initialized with strategy backends.")

    def close(self):
        if self._owns_driver:
            self._driver.close()

    # 1. STM Buffer Operations
    def stm_add(self, content: str, source: str = "unknown",
                metadata: Optional[dict] = None,
                ttl: Optional[float] = None) -> STMItem:
        item = STMItem(
            id=str(uuid.uuid4()),
            content=content,
            source=source,
            created_at=time.time(),
            ttl=ttl or self.config.stm_default_ttl,
            metadata=metadata or {},
        )
        self._stm_backend.add(item)
        self._stats['total_ingested'] += 1
        return item

    def stm_list(self) -> List[dict]:
        return self._stm_backend.list_all()

    def stm_get(self, item_id: str) -> Optional[dict]:
        return self._stm_backend.get(item_id)

    def stm_evaluate(self, item_id: str, salience: float) -> dict:
        result = self._stm_backend.evaluate(item_id, salience, self.config)
        if result:
            return result
        return {"error": "Item not found"}

    def stm_promote(self, item_id: str, graph_id: str = "") -> dict:
        item = self._stm_backend.pop(item_id)
        if not item:
            return {"error": "Item not found in STM"}
            
        result = self._ltm_backend.promote(item, graph_id)
        self._stats['total_promoted'] += 1
        
        # Webhook for external orchestration
        try:
            from ..utils.webhook import get_webhook
            get_webhook().memory_promoted(
                stm_id=item_id,
                ltm_uuid=result["ltm_uuid"],
                salience=item.salience,
                scope=item.metadata.get('scope', 'personal'),
            )
        except Exception as wh_err:
            logger.debug(f"Webhook publish skipped: {wh_err}")
            
        return result

    def stm_discard(self, item_id: str) -> dict:
        if self._stm_backend.discard(item_id):
            self._stats['total_forgotten'] += 1
            return {"status": "discarded", "id": item_id}
        return {"error": "Item not found"}

    # 2. Ebbinghaus Decay
    def run_decay(self, dry_run: bool = False) -> dict:
        results = self._ltm_backend.run_decay(self.config, dry_run)
        self._stats['total_decays_run'] += 1
        
        # Webhook notification
        if not dry_run and (results['decayed'] > 0 or results['archived'] > 0):
            try:
                from ..utils.webhook import get_webhook
                import uuid as _uuid
                get_webhook().memory_decayed(
                    removed_count=results['archived'],
                    weakened_count=results['decayed'],
                    cycle_id=str(_uuid.uuid4())[:8],
                )
            except Exception as wh_err:
                logger.debug(f"Webhook publish skipped: {wh_err}")
                
        return results

    # 3. Retrieval Boost
    def boost_on_retrieval(self, uuids: List[str]) -> int:
        boosted = self._ltm_backend.boost_on_retrieval(uuids, self.config)
        self._stats['total_boosts'] += boosted
        return boosted

    def manual_boost(self, uuid: str, amount: float) -> dict:
        return self._ltm_backend.manual_boost(uuid, amount, self.config)

    # 4. Analytics
    def get_memory_overview(self) -> dict:
        overview = self._ltm_backend.get_overview()
        
        overview['stm'] = self.stm_list()
        overview['stm_count'] = len(overview['stm'])
        overview['stats'] = self._stats
        
        return overview

