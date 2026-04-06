"""
Memory Manager — Cognitive Memory Architecture (Phase 7 + 10)

Implements human-like memory mechanisms:
  1. Short-Term Memory (STM) Buffer — temporary storage with TTL
  2. Ebbinghaus Decay — time-based forgetting curve
  3. Retrieval Boost — reinforcement on access
  4. Consolidation — STM → LTM promotion via salience evaluation
  5. Audit Trail — all changes are tracked as MemoryRevision nodes (Phase 10)
"""

import json
import logging
import time
import uuid
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.memory_manager')


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

@dataclass
class STMItem:
    """A short-term memory item waiting for consolidation."""
    id: str
    content: str
    source: str
    created_at: float  # Unix timestamp
    ttl: float  # seconds before auto-forget
    salience: float = 0.5  # Initial salience (0~1)
    metadata: Dict[str, Any] = field(default_factory=dict)
    evaluated: bool = False
    evaluation_result: Optional[str] = None  # 'promote' | 'discard' | 'pending_hitl'

    @property
    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d['is_expired'] = self.is_expired
        d['age_seconds'] = self.age_seconds
        d['age_human'] = self._format_age(self.age_seconds)
        return d

    @staticmethod
    def _format_age(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds / 60)}m"
        elif seconds < 86400:
            return f"{int(seconds / 3600)}h"
        return f"{int(seconds / 86400)}d"


@dataclass
class MemoryConfig:
    """Configuration for cognitive memory parameters."""
    # STM settings
    stm_default_ttl: float = 86400.0  # 24 hours
    stm_max_items: int = 100

    # Decay settings
    decay_rate: float = 0.95  # Daily decay multiplier (salience *= 0.95^days)
    decay_archive_threshold: float = 0.05  # Below this = archived
    decay_warn_threshold: float = 0.2  # Below this = warn

    # Reinforcement settings
    retrieval_boost: float = 0.05  # Salience boost per retrieval
    max_salience: float = 1.0
    min_salience: float = 0.0

    # Consolidation settings
    auto_promote_threshold: float = 0.7  # Auto-promote STM → LTM
    auto_discard_threshold: float = 0.3  # Auto-discard from STM
    # Between 0.3 and 0.7 → needs HITL review

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────
# Memory Manager
# ──────────────────────────────────────────────

class MemoryManager:
    """
    Core cognitive memory engine (Singleton).

    Manages STM buffer, decay scheduling, and retrieval reinforcement.
    Uses Neo4j as the long-term memory backend.
    
    Usage:
        # In create_app() — initialize once with shared driver:
        mm = MemoryManager.get_instance(driver=neo4j_driver)
        
        # Everywhere else — retrieve the singleton:
        mm = MemoryManager.get_instance()
    """

    _instance: Optional['MemoryManager'] = None
    _initialized: bool = False

    @classmethod
    def get_instance(cls, config: Optional['MemoryConfig'] = None,
                     driver=None) -> 'MemoryManager':
        """Get or create the singleton MemoryManager instance."""
        if cls._instance is None:
            cls._instance = cls(config=config, driver=driver)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing only)."""
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
        self._stm_buffer: Dict[str, STMItem] = {}
        self._lock = threading.Lock()
        self._stats = {
            'total_ingested': 0,
            'total_promoted': 0,
            'total_forgotten': 0,
            'total_boosts': 0,
            'total_decays_run': 0,
        }

        # Neo4j connection — prefer injected driver, fallback to self-created
        if driver is not None:
            self._driver = driver
            self._owns_driver = False
        else:
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
            self._owns_driver = True

        # Phase 10: Audit Trail
        from .memory_audit import MemoryAudit
        self._audit = MemoryAudit(driver=self._driver)

        # Ensure salience-related properties exist
        self._ensure_salience_schema()

        # Redis setup
        self._redis = None
        if hasattr(Config, 'REDIS_URL') and Config.REDIS_URL:
            try:
                import redis
                self._redis = redis.from_url(Config.REDIS_URL, decode_responses=True)
                self._redis.ping()
                logger.info("Redis STM backend initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis STM backend: {e}. Falling back to InMemory buffer.")
                self._redis = None

        MemoryManager._initialized = True
        logger.info("MemoryManager singleton initialized with config: "
                     f"decay_rate={self.config.decay_rate}, "
                     f"stm_ttl={self.config.stm_default_ttl}s")

    def _stm_key(self, item_id: str) -> str:
        return f"mories:stm:{item_id}"

    def close(self):
        """Close driver only if we own it (self-created)."""
        if self._owns_driver:
            self._driver.close()

    # ──────────────────────────────────────────
    # Schema Enhancement
    # ──────────────────────────────────────────

    def _ensure_salience_schema(self):
        """Add salience/access properties to existing nodes if missing."""
        queries = [
            # Set default salience for existing entities
            """
            MATCH (n:Entity) WHERE n.salience IS NULL
            SET n.salience = 0.5, n.access_count = 0,
                n.last_accessed = n.created_at
            """,
            # Set default salience for existing relations
            """
            MATCH ()-[r:RELATION]-() WHERE r.salience IS NULL
            SET r.salience = 0.5, r.access_count = 0,
                r.last_accessed = r.created_at
            """,
        ]
        with self._driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.warning(f"Schema enhancement warning: {e}")

    # ──────────────────────────────────────────
    # 1. STM Buffer Operations
    # ──────────────────────────────────────────

    def stm_add(self, content: str, source: str = "unknown",
                metadata: Optional[dict] = None,
                ttl: Optional[float] = None) -> STMItem:
        """Add item to short-term memory buffer."""
        item = STMItem(
            id=str(uuid.uuid4()),
            content=content,
            source=source,
            created_at=time.time(),
            ttl=ttl or self.config.stm_default_ttl,
            metadata=metadata or {},
        )

        with self._lock:
            self._stats['total_ingested'] += 1
            if self._redis:
                self._redis.setex(
                    self._stm_key(item.id),
                    int(item.ttl),
                    json.dumps(asdict(item))
                )
            else:
                # Enforce max items
                if len(self._stm_buffer) >= self.config.stm_max_items:
                    self._stm_cleanup()
                self._stm_buffer[item.id] = item

        logger.info(f"STM added: {item.id} (source={source}, ttl={item.ttl}s)")
        return item

    def stm_list(self) -> List[dict]:
        """List all STM items (expired items are cleaned first)."""
        with self._lock:
            if self._redis:
                keys = self._redis.keys("mories:stm:*")
                items = []
                for k in keys:
                    data = self._redis.get(k)
                    if data:
                        try:
                            item_dict = json.loads(data)
                            items.append(STMItem(**item_dict).to_dict())
                        except Exception:
                            pass
                return items
            else:
                self._stm_cleanup()
                return [item.to_dict() for item in self._stm_buffer.values()]

    def stm_get(self, item_id: str) -> Optional[dict]:
        """Get a specific STM item."""
        with self._lock:
            if self._redis:
                data = self._redis.get(self._stm_key(item_id))
                if data:
                    try:
                        item_dict = json.loads(data)
                        return STMItem(**item_dict).to_dict()
                    except Exception:
                        return None
                return None
            else:
                item = self._stm_buffer.get(item_id)
                if item and not item.is_expired:
                    return item.to_dict()
                return None

    def stm_evaluate(self, item_id: str, salience: float) -> dict:
        """Manually set salience for an STM item (HITL evaluation)."""
        with self._lock:
            if self._redis:
                data = self._redis.get(self._stm_key(item_id))
                if not data:
                    return {"error": "Item not found"}
                item_dict = json.loads(data)
                item = STMItem(**item_dict)
            else:
                item = self._stm_buffer.get(item_id)
                if not item:
                    return {"error": "Item not found"}

            item.salience = max(0.0, min(1.0, salience))
            item.evaluated = True

            if salience >= self.config.auto_promote_threshold:
                item.evaluation_result = 'promote'
            elif salience <= self.config.auto_discard_threshold:
                item.evaluation_result = 'discard'
            else:
                item.evaluation_result = 'pending_hitl'

            if self._redis:
                ttl = self._redis.ttl(self._stm_key(item_id))
                if ttl > 0:
                    self._redis.setex(self._stm_key(item_id), ttl, json.dumps(asdict(item)))

            return item.to_dict()

    def stm_promote(self, item_id: str, graph_id: str = "") -> dict:
        """Promote an STM item to LTM (Neo4j)."""
        with self._lock:
            if self._redis:
                data = self._redis.get(self._stm_key(item_id))
                if not data:
                    return {"error": "Item not found in STM"}
                item_dict = json.loads(data)
                item = STMItem(**item_dict)
                self._redis.delete(self._stm_key(item_id))
            else:
                item = self._stm_buffer.pop(item_id, None)
                if not item:
                    return {"error": "Item not found in STM"}

        # Store to Neo4j with salience
        now = datetime.now(timezone.utc).isoformat()
        node_uuid = str(uuid.uuid4())

        with self._driver.session() as session:
            session.run("""
                CREATE (n:Entity:Memory {
                    uuid: $uuid,
                    graph_id: $graph_id,
                    name: $name,
                    name_lower: $name_lower,
                    summary: $content,
                    attributes_json: $meta_json,
                    salience: $salience,
                    access_count: 0,
                    last_accessed: $now,
                    created_at: $now,
                    source: $source,
                    promoted_from_stm: true
                })
            """,
                uuid=node_uuid,
                graph_id=graph_id,
                name=item.content[:80],
                name_lower=item.content[:80].lower(),
                content=item.content,
                meta_json=str(item.metadata),
                salience=item.salience,
                now=now,
                source=item.source,
            )

        self._stats['total_promoted'] += 1

        # Phase 10: Record creation in audit trail
        try:
            self._audit.record(
                memory_uuid=node_uuid,
                field='salience',
                old_value=0.0,
                new_value=item.salience,
                change_type='create',
                changed_by='stm_promote',
                reason=f'Promoted from STM (source: {item.source})',
            )
        except Exception as e:
            logger.debug(f"Audit record failed: {e}")

        logger.info(f"STM → LTM promoted: {item_id} → {node_uuid} (salience={item.salience})")

        # Harness: notify external orchestration layer
        try:
            from ..utils.webhook import get_webhook
            get_webhook().memory_promoted(
                stm_id=item_id,
                ltm_uuid=node_uuid,
                salience=item.salience,
                scope=item.metadata.get('scope', 'personal'),
            )
        except Exception as wh_err:
            logger.debug(f"Webhook publish skipped: {wh_err}")

        return {
            "status": "promoted",
            "stm_id": item_id,
            "ltm_uuid": node_uuid,
            "salience": item.salience,
        }

    def stm_discard(self, item_id: str) -> dict:
        """Discard an STM item (explicit forgetting)."""
        with self._lock:
            if self._redis:
                deleted = self._redis.delete(self._stm_key(item_id))
                if deleted == 0:
                    return {"error": "Item not found"}
            else:
                item = self._stm_buffer.pop(item_id, None)
                if not item:
                    return {"error": "Item not found"}

        self._stats['total_forgotten'] += 1
        logger.info(f"STM discarded: {item_id}")
        return {"status": "discarded", "id": item_id}

    def _stm_cleanup(self):
        """Remove expired items from STM buffer."""
        expired = [k for k, v in self._stm_buffer.items() if v.is_expired]
        for k in expired:
            del self._stm_buffer[k]
            self._stats['total_forgotten'] += 1
        if expired:
            logger.info(f"STM cleanup: removed {len(expired)} expired items")

    # ──────────────────────────────────────────
    # 2. Ebbinghaus Decay (Forgetting Curve)
    # ──────────────────────────────────────────

    def run_decay(self, dry_run: bool = False) -> dict:
        """
        Run the Ebbinghaus decay cycle on all LTM memories.

        salience_new = salience_old × (decay_rate ^ days_since_last_access)

        Returns statistics about what was decayed, warned, or archived.
        """
        now = datetime.now(timezone.utc).isoformat()
        results = {
            'total_processed': 0,
            'decayed': 0,
            'archived': 0,
            'warned': 0,
            'unchanged': 0,
            'details': [],
        }

        with self._driver.session() as session:
            # Get all entities with salience (Phase 16: skip immutable/permanent)
            records = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                  AND (n.immutable IS NULL OR n.immutable = false)
                RETURN n.uuid AS uuid, n.name AS name,
                       n.salience AS salience,
                       n.access_count AS access_count,
                       n.last_accessed AS last_accessed,
                       n.created_at AS created_at,
                       COALESCE(n.scope, 'personal') AS scope,
                       COALESCE(n.memory_category, 'declarative') AS memory_category,
                       COALESCE(n.attributes_json, '{}') AS meta_json
                ORDER BY n.salience ASC
            """).data()

            for record in records:
                results['total_processed'] += 1
                old_salience = record.get('salience', 0.5)
                last_accessed = record.get('last_accessed') or record.get('created_at')

                # Calculate days since last access
                try:
                    if isinstance(last_accessed, str):
                        la_dt = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
                    else:
                        la_dt = last_accessed
                    days_idle = max(0, (datetime.now(timezone.utc) - la_dt).total_seconds() / 86400)
                except Exception:
                    days_idle = 0

                # Phase 8: Use scope-specific decay rate (global = no decay)
                scope = record.get('scope', 'personal')
                if scope == 'global':
                    new_salience = old_salience  # Global memories never decay
                else:
                    from .memory_scopes import MemoryScopeManager
                    scope_decay = MemoryScopeManager.get_decay_rate_static(scope)
                    effective_rate = min(self.config.decay_rate, scope_decay)

                    # Phase 16: Apply category-specific decay modifier
                    mem_cat = record.get('memory_category', 'declarative')
                    if mem_cat == 'procedural':
                        from .memory_categories import MemoryCategoryManager
                        cat_modifier = MemoryCategoryManager.calculate_decay_modifier(
                            mem_cat, record.get('meta_json', '{}')
                        )
                        effective_rate = min(1.0, effective_rate * cat_modifier)

                    new_salience = old_salience * (effective_rate ** days_idle)
                new_salience = max(self.config.min_salience, new_salience)

                detail = {
                    'uuid': record['uuid'],
                    'name': record.get('name', ''),
                    'old_salience': round(old_salience, 4),
                    'new_salience': round(new_salience, 4),
                    'days_idle': round(days_idle, 1),
                    'action': 'none',
                }

                if new_salience < self.config.decay_archive_threshold:
                    detail['action'] = 'archived'
                    results['archived'] += 1
                    if not dry_run:
                        session.run("""
                            MATCH (n:Entity {uuid: $uuid})
                            SET n.salience = $new_sal, n:ArchivedMemory
                            REMOVE n:Memory
                        """, uuid=record['uuid'], new_sal=new_salience)
                elif new_salience < self.config.decay_warn_threshold:
                    detail['action'] = 'warned'
                    results['warned'] += 1
                    if not dry_run:
                        session.run("""
                            MATCH (n:Entity {uuid: $uuid})
                            SET n.salience = $new_sal
                        """, uuid=record['uuid'], new_sal=new_salience)
                elif abs(new_salience - old_salience) > 0.001:
                    detail['action'] = 'decayed'
                    results['decayed'] += 1
                    if not dry_run:
                        session.run("""
                            MATCH (n:Entity {uuid: $uuid})
                            SET n.salience = $new_sal
                        """, uuid=record['uuid'], new_sal=new_salience)
                        # Phase 10: Record decay in audit trail
                        try:
                            self._audit.record(
                                memory_uuid=record['uuid'],
                                field='salience',
                                old_value=round(old_salience, 4),
                                new_value=round(new_salience, 4),
                                change_type='decay',
                                changed_by='ebbinghaus_scheduler',
                                reason=f'Daily decay ({days_idle:.1f}d idle)',
                            )
                        except Exception:
                            pass
                else:
                    results['unchanged'] += 1

                results['details'].append(detail)

            # Also decay relations
            rel_records = session.run("""
                MATCH ()-[r:RELATION]-()
                WHERE r.salience IS NOT NULL
                RETURN r.uuid AS uuid, r.name AS name,
                       r.salience AS salience,
                       r.last_accessed AS last_accessed,
                       r.created_at AS created_at
            """).data()

            for record in rel_records:
                old_salience = record.get('salience', 0.5)
                last_accessed = record.get('last_accessed') or record.get('created_at')

                try:
                    if isinstance(last_accessed, str):
                        la_dt = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
                    else:
                        la_dt = last_accessed
                    days_idle = max(0, (datetime.now(timezone.utc) - la_dt).total_seconds() / 86400)
                except Exception:
                    days_idle = 0

                new_salience = old_salience * (self.config.decay_rate ** days_idle)
                new_salience = max(self.config.min_salience, new_salience)

                if abs(new_salience - old_salience) > 0.001 and not dry_run:
                    session.run("""
                        MATCH ()-[r:RELATION {uuid: $uuid}]-()
                        SET r.salience = $new_sal
                    """, uuid=record['uuid'], new_sal=new_salience)

        self._stats['total_decays_run'] += 1
        results['dry_run'] = dry_run
        logger.info(f"Decay cycle complete: {results['decayed']} decayed, "
                     f"{results['archived']} archived, {results['warned']} warned")

        # Harness: notify external orchestration layer (only on real run)
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


    # ──────────────────────────────────────────
    # 3. Retrieval Boost (Reinforcement)
    # ──────────────────────────────────────────

    def boost_on_retrieval(self, uuids: List[str]) -> int:
        """Boost salience for retrieved items (called by search)."""
        if not uuids:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        boosted = 0

        with self._driver.session() as session:
            for uid in uuids:
                try:
                    # Boost entities
                    result = session.run("""
                        MATCH (n:Entity {uuid: $uuid})
                        SET n.access_count = COALESCE(n.access_count, 0) + 1,
                            n.last_accessed = $now,
                            n.salience = CASE
                                WHEN COALESCE(n.salience, 0.5) + $boost > $max
                                THEN $max
                                ELSE COALESCE(n.salience, 0.5) + $boost
                            END
                        RETURN n.uuid AS uuid
                    """,
                        uuid=uid,
                        now=now,
                        boost=self.config.retrieval_boost,
                        max=self.config.max_salience,
                    )
                    if result.single():
                        boosted += 1
                        continue

                    # Boost relations
                    result = session.run("""
                        MATCH ()-[r:RELATION {uuid: $uuid}]-()
                        SET r.access_count = COALESCE(r.access_count, 0) + 1,
                            r.last_accessed = $now,
                            r.salience = CASE
                                WHEN COALESCE(r.salience, 0.5) + $boost > $max
                                THEN $max
                                ELSE COALESCE(r.salience, 0.5) + $boost
                            END
                        RETURN r.uuid AS uuid
                    """,
                        uuid=uid,
                        now=now,
                        boost=self.config.retrieval_boost,
                        max=self.config.max_salience,
                    )
                    if result.single():
                        boosted += 1
                except Exception as e:
                    logger.warning(f"Boost failed for {uid}: {e}")

        self._stats['total_boosts'] += boosted
        return boosted

    def manual_boost(self, uuid: str, amount: float) -> dict:
        """Manually adjust salience for a specific memory."""
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            # Try entity first
            result = session.run("""
                MATCH (n:Entity {uuid: $uuid})
                SET n.salience = CASE
                    WHEN COALESCE(n.salience, 0.5) + $amount > $max THEN $max
                    WHEN COALESCE(n.salience, 0.5) + $amount < $min THEN $min
                    ELSE COALESCE(n.salience, 0.5) + $amount
                END,
                n.last_accessed = $now
                RETURN n.uuid AS uuid, n.name AS name, n.salience AS salience
            """,
                uuid=uuid, amount=amount, now=now,
                max=self.config.max_salience,
                min=self.config.min_salience,
            )
            record = result.single()
            if record:
                # Phase 10: Record boost in audit trail
                try:
                    self._audit.record(
                        memory_uuid=uuid,
                        field='salience',
                        old_value=round(record['salience'] - amount, 4),
                        new_value=record['salience'],
                        change_type='boost',
                        changed_by='manual',
                        reason=f'Manual boost amount={amount}',
                    )
                except Exception as e:
                    logger.debug(f"Audit record failed: {e}")
                return {"uuid": record['uuid'], "name": record['name'],
                        "salience": record['salience'], "type": "entity"}

            # Try relation
            result = session.run("""
                MATCH ()-[r:RELATION {uuid: $uuid}]-()
                SET r.salience = CASE
                    WHEN COALESCE(r.salience, 0.5) + $amount > $max THEN $max
                    WHEN COALESCE(r.salience, 0.5) + $amount < $min THEN $min
                    ELSE COALESCE(r.salience, 0.5) + $amount
                END,
                r.last_accessed = $now
                RETURN r.uuid AS uuid, r.name AS name, r.salience AS salience
            """,
                uuid=uuid, amount=amount, now=now,
                max=self.config.max_salience,
                min=self.config.min_salience,
            )
            record = result.single()
            if record:
                return {"uuid": record['uuid'], "name": record['name'],
                        "salience": record['salience'], "type": "relation"}

        return {"error": "UUID not found"}

    # ──────────────────────────────────────────
    # 4. Analytics & Dashboard Data
    # ──────────────────────────────────────────

    def get_memory_overview(self) -> dict:
        """Get overview statistics for the dashboard."""
        with self._driver.session() as session:
            # Entity stats
            entity_stats = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                RETURN count(n) AS total,
                       avg(n.salience) AS avg_salience,
                       min(n.salience) AS min_salience,
                       max(n.salience) AS max_salience,
                       sum(n.access_count) AS total_accesses
            """).single()

            # Relation stats
            rel_stats = session.run("""
                MATCH ()-[r:RELATION]-()
                WHERE r.salience IS NOT NULL
                RETURN count(r) AS total,
                       avg(r.salience) AS avg_salience
            """).single()

            # Salience distribution (buckets)
            distribution = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                WITH CASE
                    WHEN n.salience >= 0.9 THEN 'critical'
                    WHEN n.salience >= 0.7 THEN 'strong'
                    WHEN n.salience >= 0.5 THEN 'moderate'
                    WHEN n.salience >= 0.2 THEN 'fading'
                    ELSE 'near_forgotten'
                END AS bucket, count(n) AS cnt
                RETURN bucket, cnt
                ORDER BY cnt DESC
            """).data()

            # Archived count
            archived = session.run(
                "MATCH (n:ArchivedMemory) RETURN count(n) AS cnt"
            ).single()

            # At-risk memories (low salience, high access)
            at_risk = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL AND n.salience < 0.3
                    AND COALESCE(n.access_count, 0) > 2
                RETURN n.uuid AS uuid, n.name AS name,
                       n.salience AS salience,
                       n.access_count AS access_count,
                       n.last_accessed AS last_accessed
                ORDER BY n.access_count DESC
                LIMIT 10
            """).data()

        if self._redis:
            keys = self._redis.keys("mories:stm:*")
            stm_count = len(keys)
            stm_items = []
            for k in keys[:20]:
                data = self._redis.get(k)
                if data:
                    try:
                        item_dict = json.loads(data)
                        stm_items.append(STMItem(**item_dict).to_dict())
                    except Exception:
                        pass
        else:
            stm_count = len(self._stm_buffer)
            stm_items = [item.to_dict() for item in self._stm_buffer.values()
                         if not item.is_expired]

        return {
            'stm': {
                'count': stm_count,
                'items': stm_items[:20],
                'max_items': self.config.stm_max_items,
            },
            'ltm': {
                'entity_count': entity_stats['total'] if entity_stats else 0,
                'relation_count': rel_stats['total'] if rel_stats else 0,
                'avg_salience': round(entity_stats['avg_salience'] or 0, 3) if entity_stats else 0,
                'min_salience': round(entity_stats['min_salience'] or 0, 3) if entity_stats else 0,
                'max_salience': round(entity_stats['max_salience'] or 0, 3) if entity_stats else 0,
                'total_accesses': entity_stats['total_accesses'] or 0 if entity_stats else 0,
            },
            'distribution': {d['bucket']: d['cnt'] for d in distribution},
            'archived_count': archived['cnt'] if archived else 0,
            'at_risk': at_risk,
            'config': self.config.to_dict(),
            'stats': self._stats,
        }

    def get_salience_timeline(self, uuid: str) -> dict:
        """Get salience info for a single memory item."""
        with self._driver.session() as session:
            record = session.run("""
                MATCH (n:Entity {uuid: $uuid})
                RETURN n.uuid AS uuid, n.name AS name,
                       n.salience AS salience,
                       n.access_count AS access_count,
                       n.last_accessed AS last_accessed,
                       n.created_at AS created_at,
                       n.summary AS summary
            """, uuid=uuid).single()

            if not record:
                return {"error": "Not found"}

            return dict(record)

    def get_top_memories(self, limit: int = 20, sort_by: str = 'salience') -> List[dict]:
        """Get top memories sorted by salience or access_count."""
        order = 'n.salience DESC' if sort_by == 'salience' else 'n.access_count DESC'
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL
                RETURN n.uuid AS uuid, n.name AS name,
                       n.salience AS salience,
                       n.access_count AS access_count,
                       n.last_accessed AS last_accessed,
                       n.created_at AS created_at,
                       labels(n) AS labels
                ORDER BY {order}
                LIMIT $limit
            """, limit=limit).data()

            return records

    def get_weakest_memories(self, limit: int = 20) -> List[dict]:
        """Get memories closest to being forgotten."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (n:Entity)
                WHERE n.salience IS NOT NULL AND n.salience > 0
                RETURN n.uuid AS uuid, n.name AS name,
                       n.salience AS salience,
                       n.access_count AS access_count,
                       n.last_accessed AS last_accessed,
                       n.created_at AS created_at
                ORDER BY n.salience ASC
                LIMIT $limit
            """, limit=limit).data()

            return records

    def update_config(self, updates: dict) -> dict:
        """Update memory configuration parameters."""
        for key, value in updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"Config updated: {key} = {value}")
        return self.config.to_dict()
