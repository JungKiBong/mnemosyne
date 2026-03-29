"""
Orchestration Storage — Neo4j integration for Mories Phase 3 Blackboard.
Tracks execution Sessions, Tasks, Error Logs, and Reviews natively inside the Graph.

Production-grade: Retry logic, connection pooling, input validation.
"""

import json
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import (
    TransientError,
    ServiceUnavailable,
    SessionExpired,
)

from ..config import Config

logger = logging.getLogger('mirofish.orchestration_storage')

# Valid status whitelists
VALID_TASK_STATUSES = frozenset({
    'pending', 'processing', 'in_progress', 'completed', 'failed', 'review'
})
VALID_SESSION_STATUSES = frozenset({
    'active', 'completed', 'failed', 'paused'
})


class OrchestrationStorage:
    """Manages the Orchestration Blackboard inside Neo4j.
    
    This class should be instantiated ONCE (singleton) and shared across
    the API layer, OrchestratorService, and all ObserverAgents.
    """

    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1  # seconds

    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self._uri = uri or Config.NEO4J_URI
        self._user = user or Config.NEO4J_USER
        self._password = password or Config.NEO4J_PASSWORD
        self._driver = GraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )

    def close(self):
        """Close the Neo4j driver connection pool."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ----------------------------------------------------------------
    # Retry wrapper (matches Neo4jStorage._call_with_retry pattern)
    # ----------------------------------------------------------------

    def _call_with_retry(self, func, *args, **kwargs):
        """Execute a function with retry on Neo4j transient errors."""
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (TransientError, ServiceUnavailable, SessionExpired) as e:
                last_error = e
                wait = self.RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(
                    "Neo4j transient error (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, self.MAX_RETRIES, wait, e
                )
                time.sleep(wait)
            except Exception:
                raise
        raise last_error  # type: ignore

    def _run_query(self, query: str, **params):
        """Run a Cypher write query with retry logic. Returns None."""
        def _execute():
            with self._driver.session() as session:
                session.run(query, **params).consume()
        self._call_with_retry(_execute)

    def _run_query_single(self, query: str, **params):
        """Run a Cypher query and return a single record (or None)."""
        def _execute():
            with self._driver.session() as session:
                result = session.run(query, **params)
                return result.single()
        return self._call_with_retry(_execute)

    def _run_query_list(self, query: str, **params) -> list:
        """Run a Cypher query and return all records as a list."""
        def _execute():
            with self._driver.session() as session:
                result = session.run(query, **params)
                return list(result)
        return self._call_with_retry(_execute)

    # ----------------------------------------------------------------
    # Session Management
    # ----------------------------------------------------------------

    def create_session(self, graph_id: str, name: str, goal: str) -> str:
        session_id = str(uuid.uuid4())
        now = self._now()

        query = """
        MERGE (s:Entity:`session` {graph_id: $gid, name_lower: $name_lower})
        ON CREATE SET
            s.uuid = $uuid,
            s.name = $name,
            s.summary = $goal,
            s.status = 'active',
            s.node_type = 'session',
            s.created_at = $now,
            s.updated_at = $now
        RETURN s.uuid AS uuid
        """
        record = self._run_query_single(
            query,
            gid=graph_id, name_lower=name.lower(), uuid=session_id,
            name=name, goal=goal, now=now,
        )
        return record["uuid"] if record else session_id

    def finish_session(self, graph_id: str, session_id: str, status: str = "completed"):
        if status not in VALID_SESSION_STATUSES:
            raise ValueError(f"Invalid session status: '{status}'. Must be one of {sorted(VALID_SESSION_STATUSES)}")

        query = """
        MATCH (s:Entity:`session` {uuid: $uuid, graph_id: $gid})
        SET s.status = $status, s.updated_at = $now
        """
        self._run_query(query, uuid=session_id, gid=graph_id, status=status, now=self._now())

    # ----------------------------------------------------------------
    # Task Management
    # ----------------------------------------------------------------

    def create_task(self, graph_id: str, session_id: str, name: str,
                    description: str, context_uuids: List[str] = None) -> str:
        """Create a Task and link it to the Session.
        
        Uses a two-step approach to avoid the empty-UNWIND problem
        where an empty list would cause the entire pattern to return no rows.
        """
        task_id = str(uuid.uuid4())
        now = self._now()
        context_uuids = context_uuids or []

        # Step 1: Create Task + link to Session (always succeeds)
        query_create = """
        CREATE (t:Entity:`task` {
            uuid: $task_id,
            graph_id: $gid,
            name: $name,
            name_lower: toLower($name),
            summary: $description,
            status: 'pending',
            node_type: 'task',
            attributes_json: '{}',
            created_at: $now,
            updated_at: $now
        })
        WITH t
        MATCH (s:Entity:`session` {uuid: $session_id, graph_id: $gid})
        MERGE (s)-[r:RELATION {name: 'contains'}]->(t)
        ON CREATE SET r.edge_type = 'contains', r.created_at = $now, r.uuid = randomUUID()
        """
        self._run_query(
            query_create,
            gid=graph_id, task_id=task_id, session_id=session_id,
            name=name, description=description, now=now,
        )

        # Step 2: Link context nodes (only if list is non-empty)
        if context_uuids:
            query_ctx = """
            MATCH (t:Entity:`task` {uuid: $task_id})
            UNWIND $context_uuids AS ctx_uuid
            MATCH (ctx:Entity {uuid: ctx_uuid})
            MERGE (t)-[rc:RELATION {name: 'references'}]->(ctx)
            ON CREATE SET rc.edge_type = 'references', rc.created_at = $now, rc.uuid = randomUUID()
            """
            self._run_query(query_ctx, task_id=task_id, context_uuids=context_uuids, now=now)

        return task_id

    def update_task_status(self, graph_id: str, task_id: str, status: str, message: str = ""):
        """Update a task's status with an optional message.
        
        The message is stored as JSON in attributes_json (NOT Cypher json.stringify).
        """
        if status not in VALID_TASK_STATUSES:
            raise ValueError(f"Invalid task status: '{status}'. Must be one of {sorted(VALID_TASK_STATUSES)}")

        attrs_json = json.dumps({"message": message})
        query = """
        MATCH (t:Entity:`task` {uuid: $task_id, graph_id: $gid})
        SET t.status = $status, t.attributes_json = $attrs_json, t.updated_at = $now
        """
        self._run_query(
            query,
            gid=graph_id, task_id=task_id, status=status,
            attrs_json=attrs_json, now=self._now(),
        )

    # ----------------------------------------------------------------
    # Error & Blockers
    # ----------------------------------------------------------------

    def log_error(self, graph_id: str, task_id: str, error_msg: str, traceback_text: str = "") -> str:
        """Create an ErrorLog node and link it as BLOCKS to the active Task."""
        error_id = str(uuid.uuid4())
        now = self._now()
        attrs = json.dumps({"traceback": traceback_text})

        query = """
        MATCH (t:Entity:`task` {uuid: $task_id, graph_id: $gid})
        CREATE (e:Entity:`error_log` {
            uuid: $err_id,
            graph_id: $gid,
            name: 'Error',
            name_lower: 'error',
            summary: $error_msg,
            attributes_json: $attrs,
            node_type: 'error_log',
            created_at: $now
        })
        MERGE (e)-[r:RELATION {name: 'blocks'}]->(t)
        ON CREATE SET r.edge_type = 'blocks', r.created_at = $now, r.uuid = randomUUID()
        """
        self._run_query(
            query,
            gid=graph_id, task_id=task_id, err_id=error_id,
            error_msg=error_msg, attrs=attrs, now=now,
        )
        return error_id

    # ----------------------------------------------------------------
    # Task-Driven Context Retrieval
    # ----------------------------------------------------------------

    def get_task_context(self, graph_id: str, task_id: str) -> Dict[str, Any]:
        """Retrieves the Task node, its Session, blocking ErrorLogs, and context nodes."""
        query = """
        MATCH (t:Entity:`task` {uuid: $task_id, graph_id: $gid})

        OPTIONAL MATCH (e:Entity:`error_log`)-[:RELATION {name: 'blocks'}]->(t)
        OPTIONAL MATCH (t)-[:RELATION {name: 'references'}]->(ctx:Entity)
        OPTIONAL MATCH (s:Entity:`session`)-[:RELATION {name: 'contains'}]->(t)

        RETURN
            t,
            collect(DISTINCT e) AS errors,
            collect(DISTINCT ctx) AS context_nodes,
            s AS session
        """
        record = self._run_query_single(query, gid=graph_id, task_id=task_id)
        if not record or not record.get("t"):
            return {}

        task_node = dict(record["t"])

        # Parse error nodes with traceback extraction
        errors_out = []
        for e_node in record["errors"]:
            if e_node is None:
                continue
            e_dict = dict(e_node)
            tb = ""
            try:
                attrs = json.loads(e_dict.get("attributes_json", "{}"))
                tb = attrs.get("traceback", "")
            except (json.JSONDecodeError, TypeError):
                pass
            errors_out.append({
                "error_id": e_dict.get("uuid"),
                "error_msg": e_dict.get("summary", ""),
                "traceback": tb,
                "created_at": e_dict.get("created_at"),
            })

        # Normalize context nodes
        context_out = []
        for c_node in record["context_nodes"]:
            if c_node is None:
                continue
            c_dict = dict(c_node)
            context_out.append({
                "uuid": c_dict.get("uuid"),
                "name": c_dict.get("name"),
                "type": c_dict.get("node_type"),
            })

        return {
            "task": {
                "task_id": task_node.get("uuid"),
                "name": task_node.get("name"),
                "description": task_node.get("summary"),
                "status": task_node.get("status"),
                "created_at": task_node.get("created_at"),
                "updated_at": task_node.get("updated_at"),
            },
            "session": dict(record["session"]) if record.get("session") else None,
            "errors": errors_out,
            "context": context_out,
        }

    # ----------------------------------------------------------------
    # Blackboard Polling (Dashboard & Agents)
    # ----------------------------------------------------------------

    def get_all_tasks(self, graph_id: str, limit: int = 200) -> List[Dict]:
        """Get ALL tasks for a graph (all statuses) for Kanban board display."""
        query = """
        MATCH (s:Entity:`session` {graph_id: $gid})-[:RELATION {name: 'contains'}]->(t:Entity:`task`)
        OPTIONAL MATCH (e:Entity:`error_log`)-[:RELATION {name: 'blocks'}]->(t)
        RETURN t, s.name AS session_name, collect(DISTINCT e.summary) AS error_summaries
        ORDER BY t.created_at DESC
        LIMIT $limit
        """
        records = self._run_query_list(query, gid=graph_id, limit=limit)

        tasks = []
        for rec in records:
            t_node = rec.get("t")
            if t_node is None:
                continue
            td = dict(t_node)
            error_summaries = [es for es in (rec.get("error_summaries") or []) if es]

            # Extract agent_id from attributes_json
            agent_id = ""
            try:
                attrs = json.loads(td.get("attributes_json", "{}"))
                msg = attrs.get("message", "")
                if msg.startswith("Picked up by "):
                    agent_id = msg[len("Picked up by "):]
            except (json.JSONDecodeError, TypeError):
                pass

            tasks.append({
                "task_id": td.get("uuid"),
                "name": td.get("name", "Untitled"),
                "description": td.get("summary", ""),
                "status": td.get("status", "pending"),
                "agent_id": agent_id,
                "session_name": rec.get("session_name", ""),
                "error": error_summaries[0] if error_summaries else None,
                "created_at": td.get("created_at"),
                "updated_at": td.get("updated_at"),
            })

        return tasks

    def get_active_tasks(self, graph_id: str) -> List[Dict]:
        """Get only pending/processing tasks (for agent polling, not dashboard)."""
        query = """
        MATCH (s:Entity:`session` {graph_id: $gid, status: 'active'})
              -[:RELATION {name: 'contains'}]->(t:Entity:`task`)
        WHERE t.status IN ['pending', 'processing']
        RETURN t, s.name AS session_name
        ORDER BY t.created_at ASC
        """
        records = self._run_query_list(query, gid=graph_id)
        return [
            {
                "task_id": dict(rec["t"]).get("uuid"),
                "name": dict(rec["t"]).get("name"),
                "description": dict(rec["t"]).get("summary"),
                "status": dict(rec["t"]).get("status"),
                "session_name": rec.get("session_name"),
            }
            for rec in records if rec.get("t")
        ]
