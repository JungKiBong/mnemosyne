"""
Orchestration Blackboard API - Phase 3
Handles Session, Task, CodeUpdate, Review, and ErrorLog node management to track
long-running multi-agent execution states on the Neo4j Knowledge Graph.
"""

from flask import Blueprint, request, jsonify, current_app
from neo4j import GraphDatabase
import uuid
import datetime
from ..config import Config

orchestration_bp = Blueprint('orchestration', __name__)

def get_db_driver():
    return GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
    )

@orchestration_bp.route('/sessions', methods=['GET'])
def list_sessions():
    """List all orchestration sessions."""
    driver = get_db_driver()
    limit = request.args.get('limit', 50, type=int)
    try:
        with driver.session() as session:
            result = session.run('''
                MATCH (s:Entity)
                WHERE s.node_type = 'session'
                RETURN s.uuid as id, s.name as name, s.metadata as metadata
                ORDER BY s.created_at DESC LIMIT $limit
            ''', limit=limit)
            
            sessions = []
            for record in result:
                sessions.append({
                    "id": record["id"],
                    "name": record["name"],
                    "metadata": record["metadata"]
                })
            return jsonify({"sessions": sessions}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()

@orchestration_bp.route('/sessions', methods=['POST'])
def create_session():
    """Create a new overarching execution session."""
    data = request.json or {}
    name = data.get('name', f"Session Exploratory {datetime.datetime.now().strftime('%Y%m%d%H%M')}")
    session_id = f"session:{uuid.uuid4()}"
    
    driver = get_db_driver()
    try:
        with driver.session() as tx:
            tx.run('''
                MERGE (s:Entity {uuid: $id})
                SET s.name = $name,
                    s.node_type = 'session',
                    s.status = 'ACTIVE',
                    s.created_at = datetime()
            ''', id=session_id, name=name)
        return jsonify({"message": "Session created", "session_id": session_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()

@orchestration_bp.route('/sessions/<session_id>/tasks', methods=['POST'])
def create_task(session_id):
    """Add a new task to a session, optionally depending on other tasks."""
    data = request.json or {}
    name = data.get('name')
    if not name:
        return jsonify({"error": "Task name is required"}), 400
        
    task_id = f"task:{uuid.uuid4()}"
    depends_on = data.get('depends_on', []) # List of task_ids
    
    driver = get_db_driver()
    try:
        with driver.session() as tx:
            # 1. Create Task Node
            tx.run('''
                MERGE (t:Entity {uuid: $tid})
                SET t.name = $name,
                    t.node_type = 'task',
                    t.status = 'PENDING',
                    t.created_at = datetime(),
                    t.summary = $summary
            ''', tid=task_id, name=name, summary=data.get('summary', ''))
            
            # 2. Link to Session
            tx.run('''
                MATCH (s:Entity {uuid: $sid})
                MATCH (t:Entity {uuid: $tid})
                MERGE (s)-[:CONTAINS {edge_type: 'contains', weight: 1.0}]->(t)
            ''', sid=session_id, tid=task_id)
            
            # 3. Add Dependencies
            for dep_id in depends_on:
                tx.run('''
                    MATCH (t:Entity {uuid: $tid})
                    MATCH (dep:Entity {uuid: $dep_id})
                    MERGE (t)-[:DEPENDS_ON {edge_type: 'depends_on', weight: 0.9}]->(dep)
                ''', tid=task_id, dep_id=dep_id)
                
        return jsonify({"message": "Task created", "task_id": task_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()

@orchestration_bp.route('/sessions/<session_id>/tasks', methods=['GET'])
def list_tasks(session_id):
    """List tasks belonging to a session."""
    driver = get_db_driver()
    try:
        with driver.session() as tx:
            result = tx.run('''
                MATCH (s:Entity {uuid: $sid})-[:CONTAINS]->(t:Entity)
                WHERE s.node_type = 'session' AND t.node_type = 'task'
                RETURN t.uuid as id, t.name as name, t.status as status, t.summary as summary
            ''', sid=session_id)
            
            tasks = []
            for record in result:
                tasks.append({
                    "id": record["id"],
                    "name": record["name"],
                    "status": record["status"],
                    "summary": record["summary"]
                })
            return jsonify({"tasks": tasks}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()

@orchestration_bp.route('/tasks/<task_id>/status', methods=['PATCH'])
def update_task_status(task_id):
    """Update task execution status."""
    data = request.json or {}
    status = data.get('status')
    if not status:
        return jsonify({"error": "Status is required (e.g., PENDING, IN_PROGRESS, DONE, FAILED)"}), 400
        
    driver = get_db_driver()
    try:
        with driver.session() as tx:
            result = tx.run('''
                MATCH (t:Entity {uuid: $tid})
                WHERE t.node_type = 'task'
                SET t.status = $status, t.updated_at = datetime()
                RETURN t.uuid as id
            ''', tid=task_id, status=status)
            
            if not result.single():
                return jsonify({"error": "Task not found"}), 404
                
        return jsonify({"message": "Task status updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        driver.close()
