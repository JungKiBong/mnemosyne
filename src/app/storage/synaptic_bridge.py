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
            "CREATE INDEX synaptic_event_type IF NOT EXISTS FOR (e:SynapticEvent) ON (e.event_type)",
            "CREATE INDEX synaptic_event_status IF NOT EXISTS FOR (e:SynapticEvent) ON (e.status)",
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

    def report_conflict(
        self,
        from_agent: str,
        memory_uuid: str,
        conflicting_memory_uuid: str,
        reason: str = ""
    ) -> Dict[str, Any]:
        """Report a conflict between two memories (single atomic transaction)."""
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            # Single atomic query: verify both entities exist AND create event
            res = session.run("""
                MATCH (e1:Entity {uuid: $m1})
                MATCH (e2:Entity {uuid: $m2})
                MATCH (a:Agent {agent_id: $from_agent})
                CREATE (a)-[:REPORTED]->(evt:SynapticEvent {
                    event_id: $event_id,
                    event_type: 'conflict',
                    from_agent: $from_agent,
                    memory_uuid: $m1,
                    conflicting_memory_uuid: $m2,
                    reason: $reason,
                    status: 'active',
                    created_at: $now
                })-[:TARGETS]->(e1)
                CREATE (evt)-[:CONFLICTS_WITH]->(e2)
                RETURN evt.event_id AS eid
            """,
                event_id=event_id,
                from_agent=from_agent,
                m1=memory_uuid,
                m2=conflicting_memory_uuid,
                reason=reason,
                now=now
            ).single()

            if not res:
                return {"error": "One or both memories (or agent) not found"}

            return {"status": "conflict_reported", "event_id": event_id}

    def resolve_conflict(
        self,
        admin_agent: str,
        event_id: str,
        resolution_action: str,
        boost_amount: float = 0.5
    ) -> Dict[str, Any]:
        """Resolve a reported conflict and boost the chosen memory."""
        now = datetime.now(timezone.utc).isoformat()
        with self._driver.session() as session:
            res = session.run("""
                MATCH (evt:SynapticEvent {event_id: $event_id, event_type: 'conflict'})
                RETURN evt
            """, event_id=event_id).single()
            if not res:
                return {"error": "Conflict event not found"}
            
            evt = res["evt"]
            status = evt.get("status", "active")
            if status == "resolved":
                return {"error": "Conflict already resolved"}

            m1_uuid = evt.get("memory_uuid")
            m2_uuid = evt.get("conflicting_memory_uuid")

            target_boost = m1_uuid if resolution_action == "favor_target" else m2_uuid
            target_decay = m2_uuid if resolution_action == "favor_target" else m1_uuid

            # Resolve event + boost winner + decay loser in one atomic write
            session.run("""
                MATCH (evt:SynapticEvent {event_id: $event_id})
                SET evt.status = 'resolved',
                    evt.resolved_by = $admin_agent,
                    evt.resolution_action = $action,
                    evt.resolved_at = $now
                WITH evt
                OPTIONAL MATCH (e1:Entity {uuid: $boost_uuid})
                SET e1.salience = CASE WHEN e1.salience + $boost > 1.0 THEN 1.0 ELSE e1.salience + $boost END
                WITH evt, e1
                OPTIONAL MATCH (e2:Entity {uuid: $decay_uuid})
                SET e2.salience = CASE WHEN e2.salience - $boost < 0.0 THEN 0.0 ELSE e2.salience - $boost END
            """,
                event_id=event_id,
                admin_agent=admin_agent,
                action=resolution_action,
                now=now,
                boost_uuid=target_boost,
                decay_uuid=target_decay,
                boost=boost_amount
            )
            
            logger.info(f"Conflict {event_id} resolved by {admin_agent} via {resolution_action}.")
            return {
                "status": "conflict_resolved",
                "event_id": event_id,
                "resolution_action": resolution_action
            }

    # ──────────────────────────────────────────
    # Event Log & Status
    # ──────────────────────────────────────────

    def get_events(self, limit: int = 50, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent synaptic events from Neo4j, optionally filtered by type."""
        with self._driver.session() as session:
            type_filter = "WHERE evt.event_type = $etype" if event_type else ""
            params = {"limit": limit}
            if event_type:
                params["etype"] = event_type

            records = session.run(f"""
                MATCH (a:Agent)-[]->(evt:SynapticEvent)
                {type_filter}
                OPTIONAL MATCH (evt)-[:TARGETS]->(e:Entity)
                OPTIONAL MATCH (evt)-[:CONFLICTS_WITH]->(ce:Entity)
                RETURN evt.event_id AS event_id,
                       evt.event_type AS event_type,
                       evt.from_agent AS from_agent,
                       a.name AS agent_name,
                       evt.memory_uuid AS memory_uuid,
                       e.name AS memory_name,
                       e.content AS memory_content,
                       evt.conflicting_memory_uuid AS conflicting_memory_uuid,
                       ce.name AS conflicting_memory_name,
                       ce.content AS conflicting_memory_content,
                       evt.target_scope AS target_scope,
                       evt.boost_amount AS boost_amount,
                       evt.message AS message,
                       evt.reason AS reason,
                       evt.status AS status,
                       evt.resolved_by AS resolved_by,
                       evt.resolution_action AS resolution_action,
                       evt.created_at AS created_at
                ORDER BY evt.created_at DESC
                LIMIT $limit
            """, **params).data()
        return records

    def get_network_stats(self) -> Dict[str, Any]:
        """Get overall synaptic network statistics in a single aggregation query."""
        with self._driver.session() as session:
            # Single query: aggregate all event-type counts at once
            row = session.run("""
                MATCH (a:Agent) WITH count(a) AS agent_cnt
                OPTIONAL MATCH (ev:SynapticEvent)
                WITH agent_cnt,
                     count(ev) AS total,
                     count(CASE WHEN ev.event_type = 'share' THEN 1 END) AS shares,
                     count(CASE WHEN ev.event_type = 'empathy_boost' THEN 1 END) AS boosts,
                     count(CASE WHEN ev.event_type = 'conflict' THEN 1 END) AS conflicts,
                     count(CASE WHEN ev.event_type = 'conflict' AND ev.status = 'resolved' THEN 1 END) AS resolved
                RETURN agent_cnt, total, shares, boosts, conflicts, resolved
            """).single()

            scope_dist = session.run("""
                MATCH (evt:SynapticEvent {event_type: 'share'})-[:TARGETS]->(e:Entity)
                RETURN COALESCE(e.scope, 'personal') AS scope, count(e) AS cnt
                ORDER BY cnt DESC
            """).data()

        return {
            "total_agents": row["agent_cnt"] if row else 0,
            "total_events": row["total"] if row else 0,
            "total_shares": row["shares"] if row else 0,
            "total_empathy_boosts": row["boosts"] if row else 0,
            "total_conflicts": row["conflicts"] if row else 0,
            "resolved_conflicts": row["resolved"] if row else 0,
            "scope_distribution": {s["scope"]: s["cnt"] for s in scope_dist},
        }
