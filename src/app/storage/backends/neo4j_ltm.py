import json
import logging
import uuid
import threading
from datetime import datetime, timezone
from typing import Any, List
from ..base import BaseLTMBackend
from ..models import STMItem, MemoryConfig
from ..memory_audit import MemoryAudit

logger = logging.getLogger('mirofish.neo4j_ltm')

class Neo4jLTMBackend(BaseLTMBackend):
    def __init__(self, driver: Any, config: MemoryConfig):
        self._driver = driver
        self.config = config
        self._audit = MemoryAudit(driver=self._driver)

    def ensure_schema(self) -> None:
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

    def promote(self, item: STMItem, graph_id: str = "") -> dict:
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
                meta_json=json.dumps(item.metadata, ensure_ascii=False),
                salience=item.salience,
                now=now,
                source=item.source,
            )

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

        logger.info(f"STM → LTM promoted: {item.id} → {node_uuid} (salience={item.salience})")

        return {
            "status": "promoted",
            "stm_id": item.id,
            "ltm_uuid": node_uuid,
            "salience": item.salience,
        }

    def run_decay(self, config: MemoryConfig, dry_run: bool = False) -> dict:
        """Run the Ebbinghaus decay cycle on all LTM memories."""
        results = {
            'total_processed': 0,
            'decayed': 0,
            'archived': 0,
            'warned': 0,
            'unchanged': 0,
            'details': [],
        }

        with self._driver.session() as session:
            # Get all entities with salience
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

                try:
                    if isinstance(last_accessed, str):
                        la_dt = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
                    else:
                        la_dt = last_accessed
                    days_idle = max(0, (datetime.now(timezone.utc) - la_dt).total_seconds() / 86400)
                except Exception:
                    days_idle = 0

                scope = record.get('scope', 'personal')
                if scope == 'global':
                    new_salience = old_salience
                else:
                    from ..memory_scopes import MemoryScopeManager
                    scope_decay = MemoryScopeManager.get_decay_rate_static(scope)
                    effective_rate = min(config.decay_rate, scope_decay)

                    mem_cat = record.get('memory_category', 'declarative')
                    if mem_cat == 'procedural':
                        from ..memory_categories import MemoryCategoryManager
                        cat_modifier = MemoryCategoryManager.calculate_decay_modifier(
                            mem_cat, record.get('meta_json', '{}')
                        )
                        effective_rate = min(1.0, effective_rate * cat_modifier)

                    new_salience = old_salience * (effective_rate ** days_idle)
                    
                new_salience = max(config.min_salience, new_salience)

                detail = {
                    'uuid': record['uuid'],
                    'name': record.get('name', ''),
                    'old_salience': round(old_salience, 4),
                    'new_salience': round(new_salience, 4),
                    'days_idle': round(days_idle, 1),
                    'action': 'none',
                }

                if new_salience < config.decay_archive_threshold:
                    detail['action'] = 'archived'
                    results['archived'] += 1
                    if not dry_run:
                        session.run("""
                            MATCH (n:Entity {uuid: $uuid})
                            SET n.salience = $new_sal, n:ArchivedMemory
                            REMOVE n:Memory
                        """, uuid=record['uuid'], new_sal=new_salience)
                elif new_salience < config.decay_warn_threshold:
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

                new_salience = old_salience * (config.decay_rate ** days_idle)
                new_salience = max(config.min_salience, new_salience)

                if abs(new_salience - old_salience) > 0.001 and not dry_run:
                    session.run("""
                        MATCH ()-[r:RELATION {uuid: $uuid}]-()
                        SET r.salience = $new_sal
                    """, uuid=record['uuid'], new_sal=new_salience)

        results['dry_run'] = dry_run
        return results

    def boost_on_retrieval(self, uuids: List[str], config: MemoryConfig) -> int:
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
                        boost=config.retrieval_boost,
                        max=config.max_salience,
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
                        boost=config.retrieval_boost,
                        max=config.max_salience,
                    )
                    if result.single():
                        boosted += 1
                except Exception as e:
                    logger.warning(f"Boost failed for {uid}: {e}")

        return boosted

    def manual_boost(self, uuid: str, amount: float, config: MemoryConfig) -> dict:
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
                max=config.max_salience,
                min=config.min_salience,
            )
            record = result.single()
            if record:
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
                max=config.max_salience,
                min=config.min_salience,
            )
            record = result.single()
            if record:
                return {"uuid": record['uuid'], "name": record['name'],
                        "salience": record['salience'], "type": "relation"}

        return {"error": "UUID not found"}

    def get_overview(self) -> dict:
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

        return {
            "entities": dict(entity_stats),
            "relations": dict(rel_stats),
            "distribution": distribution,
            "archived_count": archived['cnt'] if archived else 0,
            "at_risk": at_risk
        }

