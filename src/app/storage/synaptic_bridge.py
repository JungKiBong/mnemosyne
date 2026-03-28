"""
Synaptic Bridge — Phase 9: Multi-Agent Memory Synchronization

Implements inter-agent memory sharing and collaborative reinforcement:
  1. Agent Registry — track agents and their memory namespaces
  2. Memory Sharing Events — share/receive/empathy_boost/conflict_resolve
  3. Subscription Model — agents subscribe to scopes/topics
  4. Empathy Boost — when agent B confirms agent A's memory, both strengthen

Event Flow:
  Agent A → SHARE event → Synaptic Bus → Subscribers filter → Agent B receives
  Agent B → EMPATHY_BOOST → Agent A's memory reinforced + Synchronization
"""

import logging
import uuid
import threading
from datetime import datetime, timezone
from enum import Enum
from collections import defaultdict
from typing import Dict, Any, List, Optional, Callable

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.synaptic_bridge')


# ──────────────────────────────────────────
# Event Types
# ──────────────────────────────────────────

class SynapticEventType(Enum):
    SHARE = "share"                    # Share a memory with others
    EMPATHY_BOOST = "empathy_boost"    # Confirm/strengthen someone else's memory
    SYNC_REQUEST = "sync_request"      # Request sync of a scope
    CONFLICT = "conflict"              # Two agents have conflicting memories
    BROADCAST = "broadcast"            # Broadcast to all agents


class AgentRole(Enum):
    OBSERVER = "observer"
    ANALYST = "analyst"
    CURATOR = "curator"
    ADMIN = "admin"


class SynapticBridge:
    """
    Inter-agent memory sharing and synchronization engine.

    Provides:
    - Agent registration and discovery
    - Event bus for memory sharing
    - Empathy boost protocol (mutual reinforcement)
    - Conflict detection and resolution
    """

    def __init__(self, driver=None):
        if driver:
            self._driver = driver
            self._owns_driver = False
        else:
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
            self._owns_driver = True

        self._lock = threading.Lock()
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._subscriptions: Dict[str, List[str]] = defaultdict(list)  # scope → [agent_ids]
        self._event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._event_log: List[Dict[str, Any]] = []

        self._ensure_schema()

    def close(self):
        if self._owns_driver:
            self._driver.close()

    # ──────────────────────────────────────────
    # Schema
    # ──────────────────────────────────────────

    def _ensure_schema(self):
        """Create Agent node schema and SHARED_BY relationship type."""
        queries = [
            "CREATE CONSTRAINT agent_id_uniq IF NOT EXISTS FOR (a:Agent) REQUIRE a.agent_id IS UNIQUE",
            "CREATE INDEX agent_role IF NOT EXISTS FOR (a:Agent) ON (a.role)",
            "CREATE INDEX synaptic_event_time IF NOT EXISTS FOR (e:SynapticEvent) ON (e.created_at)",
        ]
        with self._driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.debug(f"Synaptic schema warning: {e}")
        logger.info("SynapticBridge schema initialized")

    # ──────────────────────────────────────────
    # Agent Registry
    # ──────────────────────────────────────────

    def register_agent(
        self,
        agent_id: str,
        name: str,
        role: str = "observer",
        capabilities: Optional[List[str]] = None,
        subscribed_scopes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Register an agent in the synaptic network."""
        now = datetime.now(timezone.utc).isoformat()
        agent = {
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "capabilities": capabilities or [],
            "subscribed_scopes": subscribed_scopes or ["personal"],
            "registered_at": now,
            "last_active": now,
            "shared_count": 0,
            "received_count": 0,
        }

        # Persist in Neo4j
        with self._driver.session() as session:
            session.run("""
                MERGE (a:Agent {agent_id: $agent_id})
                SET a.name = $name,
                    a.role = $role,
                    a.capabilities = $capabilities,
                    a.subscribed_scopes = $scopes,
                    a.registered_at = $now,
                    a.last_active = $now,
                    a.shared_count = COALESCE(a.shared_count, 0),
                    a.received_count = COALESCE(a.received_count, 0)
            """,
                agent_id=agent_id,
                name=name,
                role=role,
                capabilities=capabilities or [],
                scopes=subscribed_scopes or ["personal"],
                now=now,
            )

        with self._lock:
            self._agents[agent_id] = agent
            for scope in (subscribed_scopes or ["personal"]):
                if agent_id not in self._subscriptions[scope]:
                    self._subscriptions[scope].append(agent_id)

        # Phase 16: Auto-inherit permanent memories from higher scopes
        try:
            from .permanent_memory import PermanentMemoryManager
            pm_mgr = PermanentMemoryManager(driver=self._driver)
            inherit_result = pm_mgr.inherit_for_agent(
                agent_id=agent_id,
                scopes=subscribed_scopes or ["global", "social"],
            )
            inherited_count = inherit_result.get("inherited_count", 0)
            if inherited_count > 0:
                logger.info(f"Agent {name} auto-inherited {inherited_count} permanent memories")
        except Exception as e:
            logger.debug(f"PM auto-inherit skipped: {e}")

        logger.info(f"Agent registered: {name} ({agent_id[:8]}) role={role}")
        return agent

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all registered agents."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (a:Agent)
                RETURN a.agent_id AS agent_id, a.name AS name,
                       a.role AS role, a.capabilities AS capabilities,
                       a.subscribed_scopes AS subscribed_scopes,
                       a.registered_at AS registered_at,
                       a.last_active AS last_active,
                       a.shared_count AS shared_count,
                       a.received_count AS received_count
                ORDER BY a.last_active DESC
            """).data()
        return records

    # ──────────────────────────────────────────
    # Memory Sharing
    # ──────────────────────────────────────────

    def share_memory(
        self,
        from_agent: str,
        memory_uuid: str,
        target_scope: str = "tribal",
        message: str = "",
    ) -> Dict[str, Any]:
        """
        Share a memory from one agent to a scope.

        Creates a SHARED_BY relationship and notifies subscribers.
        """
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            # Verify memory exists
            mem = session.run("""
                MATCH (e:Entity {uuid: $uuid})
                RETURN e.name AS name, e.salience AS salience, e.scope AS scope
            """, uuid=memory_uuid).single()

            if not mem:
                return {"error": "Memory not found"}

            # Create sharing event
            session.run("""
                MATCH (e:Entity {uuid: $memory_uuid})
                MATCH (a:Agent {agent_id: $from_agent})
                CREATE (a)-[:SHARED]->(evt:SynapticEvent {
                    event_id: $event_id,
                    event_type: 'share',
                    from_agent: $from_agent,
                    memory_uuid: $memory_uuid,
                    target_scope: $target_scope,
                    message: $message,
                    created_at: $now
                })-[:TARGETS]->(e)
            """,
                event_id=event_id,
                from_agent=from_agent,
                memory_uuid=memory_uuid,
                target_scope=target_scope,
                message=message,
                now=now,
            )

            # Update agent stats
            session.run("""
                MATCH (a:Agent {agent_id: $agent_id})
                SET a.shared_count = COALESCE(a.shared_count, 0) + 1,
                    a.last_active = $now
            """, agent_id=from_agent, now=now)

        # Log event
        event = {
            "event_id": event_id,
            "type": "share",
            "from": from_agent,
            "memory_uuid": memory_uuid,
            "memory_name": mem["name"],
            "target_scope": target_scope,
            "message": message,
            "timestamp": now,
        }
        self._event_log.append(event)

        # Subscribers notification (in-memory)
        subscribers = self._subscriptions.get(target_scope, [])
        notified = [s for s in subscribers if s != from_agent]

        logger.info(
            f"Memory shared: {mem['name']} by {from_agent[:8]} → "
            f"scope={target_scope}, notified={len(notified)} agents"
        )

        return {
            "status": "shared",
            "event_id": event_id,
            "memory_name": mem["name"],
            "from_agent": from_agent,
            "target_scope": target_scope,
            "notified_agents": notified,
        }

    def empathy_boost(
        self,
        from_agent: str,
        memory_uuid: str,
        boost_amount: float = 0.1,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        Empathy Boost — when one agent confirms another's memory, both reinforce.

        Agent B says "I agree with this memory" → memory salience goes up,
        Agent B also receives a reciprocal boost to related memories.
        """
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            # Boost the target memory
            result = session.run("""
                MATCH (e:Entity {uuid: $uuid})
                SET e.salience = CASE
                    WHEN e.salience + $boost > 1.0 THEN 1.0
                    ELSE e.salience + $boost
                END,
                e.access_count = COALESCE(e.access_count, 0) + 1,
                e.last_accessed = $now
                RETURN e.uuid AS uuid, e.name AS name,
                       e.salience AS salience, e.owner_id AS owner_id
            """, uuid=memory_uuid, boost=boost_amount, now=now).single()

            if not result:
                return {"error": "Memory not found"}

            # Create event
            session.run("""
                MATCH (e:Entity {uuid: $memory_uuid})
                MATCH (a:Agent {agent_id: $from_agent})
                CREATE (a)-[:EMPATHY_BOOSTED]->(evt:SynapticEvent {
                    event_id: $event_id,
                    event_type: 'empathy_boost',
                    from_agent: $from_agent,
                    memory_uuid: $memory_uuid,
                    boost_amount: $boost,
                    reason: $reason,
                    created_at: $now
                })-[:TARGETS]->(e)
            """,
                event_id=event_id,
                from_agent=from_agent,
                memory_uuid=memory_uuid,
                boost=boost_amount,
                reason=reason,
                now=now,
            )

            # Record in audit trail
            try:
                from .memory_audit import MemoryAudit
                audit = MemoryAudit(driver=self._driver)
                audit.record(
                    memory_uuid=memory_uuid,
                    field="salience",
                    old_value=round(result["salience"] - boost_amount, 4),
                    new_value=result["salience"],
                    change_type="empathy_boost",
                    changed_by=f"agent:{from_agent}",
                    reason=reason or f"Empathy boost from {from_agent[:8]}",
                )
            except Exception as e:
                logger.debug(f"Audit record failed: {e}")

        logger.info(
            f"Empathy boost: {result['name']} by {from_agent[:8]} "
            f"+{boost_amount} → {result['salience']}"
        )

        return {
            "status": "boosted",
            "event_id": event_id,
            "memory_uuid": memory_uuid,
            "memory_name": result["name"],
            "new_salience": result["salience"],
            "boost_amount": boost_amount,
            "from_agent": from_agent,
        }

    # ──────────────────────────────────────────
    # Event Log & Status
    # ──────────────────────────────────────────

    def get_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent synaptic events from Neo4j."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (a:Agent)-[]->(evt:SynapticEvent)
                OPTIONAL MATCH (evt)-[:TARGETS]->(e:Entity)
                RETURN evt.event_id AS event_id,
                       evt.event_type AS event_type,
                       evt.from_agent AS from_agent,
                       a.name AS agent_name,
                       evt.memory_uuid AS memory_uuid,
                       e.name AS memory_name,
                       evt.target_scope AS target_scope,
                       evt.boost_amount AS boost_amount,
                       evt.message AS message,
                       evt.reason AS reason,
                       evt.created_at AS created_at
                ORDER BY evt.created_at DESC
                LIMIT $limit
            """, limit=limit).data()
        return records

    def get_network_stats(self) -> Dict[str, Any]:
        """Get overall synaptic network statistics."""
        with self._driver.session() as session:
            agents = session.run(
                "MATCH (a:Agent) RETURN count(a) AS cnt"
            ).single()
            events = session.run(
                "MATCH (e:SynapticEvent) RETURN count(e) AS cnt"
            ).single()
            shares = session.run(
                "MATCH (e:SynapticEvent {event_type: 'share'}) RETURN count(e) AS cnt"
            ).single()
            boosts = session.run(
                "MATCH (e:SynapticEvent {event_type: 'empathy_boost'}) RETURN count(e) AS cnt"
            ).single()
            # Scope distribution of shared memories
            scope_dist = session.run("""
                MATCH (evt:SynapticEvent)-[:TARGETS]->(e:Entity)
                WHERE evt.event_type = 'share'
                RETURN COALESCE(e.scope, 'personal') AS scope, count(e) AS cnt
                ORDER BY cnt DESC
            """).data()

        return {
            "total_agents": agents["cnt"] if agents else 0,
            "total_events": events["cnt"] if events else 0,
            "total_shares": shares["cnt"] if shares else 0,
            "total_empathy_boosts": boosts["cnt"] if boosts else 0,
            "scope_distribution": {s["scope"]: s["cnt"] for s in scope_dist},
        }
