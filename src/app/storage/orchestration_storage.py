"""
Orchestration Storage — Neo4j integration for Mories Phase 3 Blackboard.
Tracks execution Sessions, Tasks, Error Logs, and Reviews natively inside the Graph.
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase, Session as Neo4jSession

from ..config import Config
from ..models.knowledge_types import NodeType, EdgeType

logger = logging.getLogger('mirofish.orchestration_storage')


class OrchestrationStorage:
    """Manages the Orchestration Blackboard inside Neo4j."""

    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self._uri = uri or Config.NEO4J_URI
        self._user = user or Config.NEO4J_USER
        self._password = password or Config.NEO4J_PASSWORD
        self._driver = GraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )

    def close(self):
        self._driver.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

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
        with self._driver.session() as session:
            result = session.run(query, gid=graph_id, name_lower=name.lower(), uuid=session_id, name=name, goal=goal, now=now)
            return result.single()["uuid"]

    def finish_session(self, graph_id: str, session_id: str, status: str = "completed"):
        query = """
        MATCH (s:Entity:`session` {uuid: $uuid, graph_id: $gid})
        SET s.status = $status, s.updated_at = $now
        """
        with self._driver.session() as session:
            session.run(query, uuid=session_id, gid=graph_id, status=status, now=self._now())

    # ----------------------------------------------------------------
    # Task Management
    # ----------------------------------------------------------------

    def create_task(self, graph_id: str, session_id: str, name: str, description: str, context_uuids: List[str] = None) -> str:
        """Create a Task and link it to the Session and relevant context nodes (Task-Driven Retrieval context)."""
        task_id = str(uuid.uuid4())
        now = self._now()
        context_uuids = context_uuids or []

        query = """
        // 1. Create the Task
        MERGE (t:Entity:`task` {uuid: $task_id})
        SET 
            t.graph_id = $gid,
            t.name = $name,
            t.name_lower = toLower($name),
            t.summary = $description,
            t.status = 'pending',
            t.node_type = 'task',
            t.created_at = $now,
            t.updated_at = $now

        // 2. Link Task to Session
        WITH t
        MATCH (s:Entity:`session` {uuid: $session_id})
        MERGE (s)-[r:RELATION {name: 'contains'}]->(t)
        ON CREATE SET r.edge_type = 'contains', r.created_at = $now, r.uuid = randomUUID()

        // 3. Link Context Context items
        WITH t
        UNWIND $context_uuids AS ctx_uuid
        MATCH (ctx:Entity {uuid: ctx_uuid})
        MERGE (t)-[rc:RELATION {name: 'references'}]->(ctx)
        ON CREATE SET rc.edge_type = 'references', rc.created_at = $now, rc.uuid = randomUUID()
        """
        
        with self._driver.session() as session:
            session.run(query, 
                        gid=graph_id, task_id=task_id, session_id=session_id, 
                        name=name, description=description, context_uuids=context_uuids, now=now)
        return task_id

    def update_task_status(self, graph_id: str, task_id: str, status: str, message: str = ""):
        query = """
        MATCH (t:Entity:`task` {uuid: $task_id, graph_id: $gid})
        SET t.status = $status, t.attributes_json = json.stringify({message: $msg}), t.updated_at = $now
        """
        with self._driver.session() as session:
            session.run(query, gid=graph_id, task_id=task_id, status=status, msg=message, now=self._now())

    # ----------------------------------------------------------------
    # Error & Blockers
    # ----------------------------------------------------------------

    def log_error(self, graph_id: str, task_id: str, error_msg: str, traceback: str = "") -> str:
        """Create an ErrorLog node and link it as BLOCKS to the active Task."""
        error_id = str(uuid.uuid4())
        now = self._now()
        
        query = """
        MATCH (t:Entity:`task` {uuid: $task_id, graph_id: $gid})

        MERGE (e:Entity:`error_log` {uuid: $err_id})
        SET 
            e.graph_id = $gid,
            e.name = 'Error',
            e.name_lower = 'error',
            e.summary = $error_msg,
            e.attributes_json = $attrs,
            e.node_type = 'error_log',
            e.created_at = $now

        MERGE (e)-[r:RELATION {name: 'blocks'}]->(t)
        ON CREATE SET r.edge_type = 'blocks', r.created_at = $now, r.uuid = randomUUID()
        """
        attrs = json.dumps({"traceback": traceback})
        with self._driver.session() as session:
            session.run(query, gid=graph_id, task_id=task_id, err_id=error_id, error_msg=error_msg, attrs=attrs, now=now)
        return error_id

    # ----------------------------------------------------------------
    # Task-Driven Context Retrieval
    # ----------------------------------------------------------------

    def get_task_context(self, graph_id: str, task_id: str) -> Dict[str, Any]:
        """
        Retrieves the Task node itself, its Session, any connected blocking ErrorLogs,
        and the semantic context nodes (code blocks, docs) it references.
        """
        query = """
        MATCH (t:Entity:`task` {uuid: $task_id, graph_id: $gid})
        
        // Find blockers
        OPTIONAL MATCH (e:Entity:`error_log`)-[rb:RELATION {name: 'blocks'}]->(t)
        
        // Find context targets
        OPTIONAL MATCH (t)-[rc:RELATION {name: 'references'}]->(ctx:Entity)
        
        // Find parent session
        OPTIONAL MATCH (s:Entity:`session`)-[rs:RELATION {name: 'contains'}]->(t)

        RETURN 
            t, 
            collect(DISTINCT e) AS errors, 
            collect(DISTINCT ctx) AS context_nodes,
            s AS session
        """
        with self._driver.session() as session:
            result = session.run(query, gid=graph_id, task_id=task_id)
            record = result.single()
            if not record or not record.get("t"):
                return {}
            
            # Format output
            task_node = dict(record["t"])
            return {
                "uuid": task_node.get("uuid"),
                "name": task_node.get("name"),
                "summary": task_node.get("summary"),
                "status": task_node.get("status"),
                "session": dict(record["session"]) if record.get("session") else None,
                "errors": [dict(e) for e in record["errors"] if e],
                "context_nodes": [dict(c) for c in record["context_nodes"] if c]
            }

    # ----------------------------------------------------------------
    # Blackboard Active Tasks Polling
    # ----------------------------------------------------------------

    def get_active_tasks(self, graph_id: str) -> List[Dict]:
        query = """
        MATCH (s:Entity:`session` {graph_id: $gid, status: 'active'})-[r:RELATION {name: 'contains'}]->(t:Entity:`task`)
        WHERE t.status IN ['pending', 'processing']
        RETURN t, s.name AS session_name
        ORDER BY t.created_at DESC
        """
        with self._driver.session() as session:
            result = session.run(query, gid=graph_id)
            return [
                {
                    "uuid": rec["t"].get("uuid"),
                    "name": rec["t"].get("name"),
                    "status": rec["t"].get("status"),
                    "session_name": rec["session_name"]
                } for rec in result
            ]
