"""
Mories MCP Tools — 8 core tools for external AI agents.

Tools:
  1. mories_search        — Compact index search (Progressive Disclosure Layer 1)
  2. mories_detail        — Full content retrieval (Progressive Disclosure Layer 3)
  3. mories_timeline      — Temporal neighborhood (Progressive Disclosure Layer 2)
  4. mories_update_status — Lightweight Whiteboard (status/priority management)
  5. mories_ingest        — Data ingestion from file/URL/text
  6. mories_profile       — Agent profile lookup
  7. mories_graph_query   — Read-only Cypher queries
  8. mories_stream        — Stream ingestion control
"""

import json
import time
import logging
import httpx
from neo4j import GraphDatabase

from .config import MCPConfig

logger = logging.getLogger("mories.mcp.tools")

# ---------------------------------------------------------------------------
#  Shared helpers
# ---------------------------------------------------------------------------

_api = None

def _get_api_client() -> httpx.Client:
    """Lazy singleton HTTP client for Flask API."""
    global _api
    if _api is None:
        _api = httpx.Client(base_url=MCPConfig.API_BASE_URL, timeout=30.0)
    return _api


_driver = None

def _get_neo4j_driver():
    """Lazy singleton Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            MCPConfig.NEO4J_URI,
            auth=(MCPConfig.NEO4J_USER, MCPConfig.NEO4J_PASSWORD),
        )
    return _driver


# Rate limiter (simple token-bucket)
_call_timestamps: list[float] = []

def _rate_check():
    """Raise if rate limit exceeded."""
    now = time.time()
    window = 60.0
    _call_timestamps[:] = [t for t in _call_timestamps if now - t < window]
    if len(_call_timestamps) >= MCPConfig.RATE_LIMIT_PER_MIN:
        raise RuntimeError(
            f"Rate limit exceeded: max {MCPConfig.RATE_LIMIT_PER_MIN} calls/min"
        )
    _call_timestamps.append(now)


# ---------------------------------------------------------------------------
#  Type icons for Semantic Compression
# ---------------------------------------------------------------------------

_TYPE_ICONS = {
    "person": "👤", "organization": "🏢", "event": "📅",
    "concept": "💡", "decision": "🟤", "rule": "📏",
    "gotcha": "🔴", "fix": "🟡", "how-it-works": "🔵",
    "memory": "🧠", "project": "📦", "design": "🏗️",
    "task": "🎯", "entity": "📌", "fact": "📝",
}

def _type_icon(entity_type: str) -> str:
    """Return emoji icon for entity type."""
    if not entity_type:
        return "📌"
    return _TYPE_ICONS.get(entity_type.lower(), "📌")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed content."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
#  Tool 1: mories_search (Progressive Disclosure — Layer 1: Compact Index)
# ---------------------------------------------------------------------------

SEARCH_DESCRIPTION = (
    "Search the Mories memory system. Returns a COMPACT INDEX of results "
    "(~50-100 tokens/result) with type icons, relevance scores, and token costs. "
    "Filter by status (pending/in_progress/completed/blocked) for task tracking. "
    "Use mories_detail for full content, mories_timeline for temporal context."
)


def mories_search(query: str, graph_id: str = "", limit: int = 10, status: str = "", **kwargs) -> dict:
    """
    Search the knowledge graph — returns compact index only.

    Progressive Disclosure Layer 1:
    - Returns type icon + name + score + estimated token cost
    - Agent decides which items need full detail (→ mories_detail)
    - Saves ~80% context vs returning full content
    - Optional status filter for lightweight Whiteboard tracking

    Args:
        query: Natural language search query
        graph_id: Optional graph/project ID to scope the search
        limit: Max results to return (default 10)
        status: Filter by status (pending/in_progress/completed/blocked). Empty = all.

    Returns:
        Compact index with token budget metadata
    """
    _rate_check()
    _allowed_scopes = kwargs.get("_allowed_scopes", ["*"])
    is_admin = "*" in _allowed_scopes

    driver = _get_neo4j_driver()
    results = []

    with driver.session() as session:
        # 1) Fulltext search on entities
        # Build optional status filter clause
        status_clause = "AND node.status = $status" if status else ""

        entity_cypher = f"""
        CALL db.index.fulltext.queryNodes('entity_fulltext', $q)
        YIELD node, score
        WHERE score > 0.3
        {status_clause}
        OPTIONAL MATCH (g:Graph)-[:CONTAINS]->(node)
        WITH node, score, collect(g.uuid) AS gids, collect(COALESCE(g.is_public, false)) AS pubs
        WHERE $is_admin = true
           OR any(p IN pubs WHERE p = true)
           OR any(gid IN gids WHERE gid IN $allowed_scopes)
           OR size(gids) = 0
        RETURN node.uuid AS uuid,
               node.name AS name,
               node.entity_type AS type,
               node.summary AS summary,
               node.description AS description,
               node.status AS status,
               labels(node) AS labels,
               score
        ORDER BY score DESC
        LIMIT $lim
        """
        try:
            params = dict(q=query, lim=limit, is_admin=is_admin, allowed_scopes=_allowed_scopes)
            if status:
                params["status"] = status
            entity_results = session.run(entity_cypher, **params)
            for r in entity_results:
                etype = r["type"] or "entity"
                full_content = r["description"] or r["summary"] or r["name"] or ""
                entry = {
                    "icon": _type_icon(etype),
                    "uuid": r["uuid"],
                    "name": r["name"],
                    "type": etype,
                    "score": round(r["score"], 3),
                    "preview": (r["summary"] or r["name"] or "")[:80],
                    "token_cost": _estimate_tokens(full_content),
                    "source": "entity",
                }
                if r.get("status"):
                    entry["status"] = r["status"]
                results.append(entry)
        except Exception as e:
            logger.warning("Entity fulltext search failed: %s", e)

        # 2) Fulltext search on facts
        fact_cypher = """
        CALL db.index.fulltext.queryNodes('fact_fulltext', $q)
        YIELD node, score
        WHERE score > 0.3
        OPTIONAL MATCH (g:Graph)-[:CONTAINS]->(node)
        WITH node, score, collect(g.uuid) AS gids, collect(COALESCE(g.is_public, false)) AS pubs
        WHERE $is_admin = true
           OR any(p IN pubs WHERE p = true)
           OR any(gid IN gids WHERE gid IN $allowed_scopes)
           OR size(gids) = 0
        RETURN node.uuid AS uuid,
               node.subject AS subject,
               node.predicate AS predicate,
               node.object AS object,
               score
        ORDER BY score DESC
        LIMIT $lim
        """
        try:
            fact_results = session.run(fact_cypher, q=query, lim=limit, is_admin=is_admin, allowed_scopes=_allowed_scopes)
            for r in fact_results:
                fact_text = f"{r['subject']} → {r['predicate']} → {r['object']}"
                results.append({
                    "icon": "📝",
                    "uuid": r["uuid"],
                    "name": fact_text[:60],
                    "type": "fact",
                    "score": round(r["score"], 3),
                    "preview": fact_text[:80],
                    "token_cost": _estimate_tokens(fact_text),
                    "source": "fact",
                })
        except Exception as e:
            logger.warning("Fact fulltext search failed: %s", e)

        # 3) Graph-id scoped search (if provided)
        if graph_id:
            graph_cypher = """
            MATCH (g:Graph {uuid: $graph_id})-[:CONTAINS]->(e:Entity)
            WHERE (e.name CONTAINS $query OR e.description CONTAINS $query)
              AND ($is_admin = true OR g.is_public = true OR g.uuid IN $allowed_scopes)
            RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS type,
                   e.summary AS summary, e.description AS description
            LIMIT $limit
            """
            try:
                graph_results = session.run(
                    graph_cypher, graph_id=graph_id, query=query, limit=limit,
                    is_admin=is_admin, allowed_scopes=_allowed_scopes
                )
                for r in graph_results:
                    etype = r["type"] or "entity"
                    full_content = r["description"] or r["summary"] or r["name"] or ""
                    results.append({
                        "icon": _type_icon(etype),
                        "uuid": r["uuid"],
                        "name": r["name"],
                        "type": etype,
                        "score": 1.0,
                        "preview": (r["summary"] or r["name"] or "")[:80],
                        "token_cost": _estimate_tokens(full_content),
                        "source": "graph_scope",
                    })
            except Exception as e:
                logger.warning("Graph scoped search failed: %s", e)

    total_token_cost = sum(r["token_cost"] for r in results)
    index_token_cost = _estimate_tokens(str(results))

    return {
        "query": query,
        "graph_id": graph_id or "(all)",
        "total": len(results),
        "results": results,
        "_budget": {
            "index_tokens": index_token_cost,
            "full_tokens": total_token_cost,
            "savings_pct": round((1 - index_token_cost / max(total_token_cost, 1)) * 100, 1),
            "hint": "Use mories_detail(uuid) for full content of selected items",
        },
    }


# ---------------------------------------------------------------------------
#  Tool 2: mories_detail (Progressive Disclosure — Layer 3: Full Content)
# ---------------------------------------------------------------------------

DETAIL_DESCRIPTION = (
    "Retrieve FULL content of a specific memory by UUID. "
    "Use after mories_search to get complete details for selected items. "
    "Returns all properties, relationships, and full text content."
)


def mories_detail(uuid: str, include_relations: bool = True, **kwargs) -> dict:
    """
    Get full details of a memory node by UUID.

    Progressive Disclosure Layer 3:
    - Returns complete content, all properties, and relations
    - Only call this for items you actually need

    Args:
        uuid: Memory/entity UUID from mories_search results
        include_relations: Whether to include connected nodes

    Returns:
        Full memory content with relationships
    """
    _rate_check()
    _allowed_scopes = kwargs.get("_allowed_scopes", ["*"])
    is_admin = "*" in _allowed_scopes

    driver = _get_neo4j_driver()

    with driver.session() as session:
        # Get the node with all properties
        node_cypher = """
        MATCH (n {uuid: $uuid})
        OPTIONAL MATCH (g:Graph)-[:CONTAINS]->(n)
        WITH n, collect(g.uuid) AS gids, collect(COALESCE(g.is_public, false)) AS pubs
        WHERE $is_admin = true
           OR any(p IN pubs WHERE p = true)
           OR any(gid IN gids WHERE gid IN $allowed_scopes)
           OR size(gids) = 0
        RETURN n, labels(n) AS labels
        """
        try:
            result = session.run(node_cypher, uuid=uuid, is_admin=is_admin, allowed_scopes=_allowed_scopes)
            record = result.single()
            if not record:
                return {"error": f"Not found: {uuid}", "hint": "Check UUID from mories_search results"}

            node = record["n"]
            labels = record["labels"]
            props = dict(node.items())

            # Build response
            full_content = props.get("description", "") or props.get("summary", "") or props.get("name", "")
            response = {
                "uuid": uuid,
                "labels": labels,
                "icon": _type_icon(props.get("entity_type", "")),
                "name": props.get("name", ""),
                "type": props.get("entity_type", "unknown"),
                "content": full_content,
                "properties": {k: v for k, v in props.items()
                               if k not in ("uuid", "name", "entity_type", "description", "summary")},
                "token_cost": _estimate_tokens(str(props)),
            }

        except Exception as e:
            return {"error": str(e)}

        # Get relationships if requested
        if include_relations:
            rel_cypher = """
            MATCH (n {uuid: $uuid})-[r]-(other)
            RETURN type(r) AS rel_type,
                   startNode(r).uuid = n.uuid AS outgoing,
                   other.uuid AS other_uuid,
                   other.name AS other_name,
                   other.entity_type AS other_type
            LIMIT 20
            """
            try:
                rel_results = session.run(rel_cypher, uuid=uuid)
                relations = []
                for r in rel_results:
                    direction = "→" if r["outgoing"] else "←"
                    relations.append({
                        "direction": direction,
                        "type": r["rel_type"],
                        "target_uuid": r["other_uuid"],
                        "target_name": r["other_name"],
                        "target_type": r["other_type"],
                    })
                response["relations"] = relations
                response["relation_count"] = len(relations)
            except Exception as e:
                logger.warning("Relation lookup failed: %s", e)
                response["relations"] = []

    return response


# ---------------------------------------------------------------------------
#  Tool 3: mories_timeline (Progressive Disclosure — Layer 2: Temporal Context)
# ---------------------------------------------------------------------------

TIMELINE_DESCRIPTION = (
    "Get temporal neighbors of a memory node. "
    "Shows what happened before and after a specific memory, "
    "providing narrative context. Use after mories_search "
    "to understand the timeline around important events."
)


def mories_timeline(uuid: str, window: int = 5, **kwargs) -> dict:
    """
    Get temporal neighborhood of a memory.

    Progressive Disclosure Layer 2:
    - Returns compact timeline of nearby memories
    - Helps build narrative arc without loading full content

    Args:
        uuid: Center memory UUID
        window: Number of items before/after (default 5)

    Returns:
        Timeline with before/after compact entries
    """
    _rate_check()
    _allowed_scopes = kwargs.get("_allowed_scopes", ["*"])
    is_admin = "*" in _allowed_scopes

    driver = _get_neo4j_driver()

    with driver.session() as session:
        # Get the center node's timestamp
        center_cypher = """
        MATCH (n {uuid: $uuid})
        RETURN n.name AS name, n.entity_type AS type,
               n.created_at AS created_at, n.last_accessed AS last_accessed,
               n.summary AS summary
        """
        try:
            center_result = session.run(center_cypher, uuid=uuid).single()
            if not center_result:
                return {"error": f"Not found: {uuid}"}

            center_ts = center_result["created_at"] or center_result["last_accessed"]
            center_name = center_result["name"]
        except Exception as e:
            return {"error": str(e)}

        # Find temporal neighbors (by created_at or last_accessed)
        timeline_cypher = """
        MATCH (n)
        WHERE (n:Entity OR n:Memory) AND n.uuid <> $uuid
          AND (n.created_at IS NOT NULL OR n.last_accessed IS NOT NULL)
        WITH n, COALESCE(n.created_at, n.last_accessed) AS ts
        ORDER BY ts DESC
        LIMIT 100
        WITH collect({uuid: n.uuid, name: n.name, type: n.entity_type,
                      ts: ts, summary: n.summary}) AS all_items
        RETURN all_items
        """
        try:
            timeline_result = session.run(timeline_cypher, uuid=uuid).single()
            all_items = timeline_result["all_items"] if timeline_result else []
        except Exception as e:
            logger.warning("Timeline query failed: %s", e)
            all_items = []

        # Split into before/after relative to center
        before = []
        after = []
        for item in all_items:
            entry = {
                "icon": _type_icon(item.get("type", "")),
                "uuid": item["uuid"],
                "name": item["name"],
                "type": item.get("type", "unknown"),
                "preview": (item.get("summary") or item.get("name") or "")[:60],
            }
            if center_ts and item.get("ts"):
                try:
                    if item["ts"] < center_ts:
                        before.append(entry)
                    else:
                        after.append(entry)
                except (TypeError, ValueError):
                    after.append(entry)
            else:
                after.append(entry)

        before = before[-window:]  # last N before
        after = after[:window]     # first N after

    return {
        "center": {
            "uuid": uuid,
            "name": center_name,
            "icon": _type_icon(center_result["type"] or ""),
        },
        "before": before,
        "after": after,
        "total_neighbors": len(before) + len(after),
        "_budget": {
            "tokens_used": _estimate_tokens(str(before) + str(after)),
            "hint": "Use mories_detail(uuid) for full content of any item",
        },
    }


# ---------------------------------------------------------------------------
#  Tool 2: mories_ingest
# ---------------------------------------------------------------------------

INGEST_DESCRIPTION = (
    "Ingest data into Mories's knowledge graph. "
    "Supports files (PDF, CSV, JSON, MD, DOCX, etc.), "
    "text content, and batch processing via 11 data adapters."
)


def mories_ingest(
    graph_id: str,
    source_ref: str = "",
    text_content: str = "",
    source_type: str = "auto",
    **kwargs
) -> dict:
    """
    Ingest data into the knowledge graph.

    Args:
        graph_id: Target graph/project ID
        source_ref: File path or URL to ingest (e.g. "/data/report.csv")
        text_content: Raw text to ingest directly (alternative to source_ref)
        source_type: Adapter hint: auto, csv, json, pdf, md, etc.

    Returns:
        dict with ingestion result
    """
    _rate_check()
    _allowed_scopes = kwargs.get("_allowed_scopes", ["*"])
    if "*" not in _allowed_scopes and graph_id not in _allowed_scopes:
        return {"error": f"Unauthorized. Missing permission to write to graph_id: '{graph_id}'."}

    client = _get_api_client()

    if text_content:
        # Write text to temp file and ingest
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="mcp_ingest_"
        ) as f:
            f.write(text_content)
            source_ref = f.name

    if not source_ref:
        return {"error": "Either source_ref or text_content is required"}

    payload = {
        "graph_id": graph_id,
        "source_ref": source_ref,
        "options": {"source_type": source_type} if source_type != "auto" else {},
    }

    try:
        resp = client.post("/api/ingest", json=payload)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
#  Tool 3: mories_profile
# ---------------------------------------------------------------------------

PROFILE_DESCRIPTION = (
    "Look up an agent's profile from the Mories memory system. "
    "Returns the agent's traits, dynamic state, memory count, "
    "and recent interactions from the knowledge graph."
)


def mories_profile(
    agent_name: str = "",
    agent_id: str = "",
    graph_id: str = "",
    **kwargs
) -> dict:
    """
    Look up agent profile from Neo4j.

    Args:
        agent_name: Agent's display name (e.g. "Alice Chen")
        agent_id: Agent's UUID (alternative to name)
        graph_id: Optional graph scope

    Returns:
        dict with agent profile data
    """
    _rate_check()

    driver = _get_neo4j_driver()

    with driver.session() as session:
        if agent_id:
            cypher = """
            MATCH (a:Entity {uuid: $id})
            OPTIONAL MATCH (a)-[r]->(other)
            WITH a, count(r) AS rel_count,
                 collect(DISTINCT type(r))[..5] AS rel_types
            RETURN a.uuid AS uuid, a.name AS name,
                   a.entity_type AS type,
                   a.description AS description,
                   a.traits AS traits,
                   a.dynamic_state AS dynamic_state,
                   rel_count, rel_types
            """
            result = session.run(cypher, id=agent_id)
        else:
            cypher = """
            MATCH (a:Entity)
            WHERE a.name CONTAINS $name
            OPTIONAL MATCH (a)-[r]->(other)
            WITH a, count(r) AS rel_count,
                 collect(DISTINCT type(r))[..5] AS rel_types
            RETURN a.uuid AS uuid, a.name AS name,
                   a.entity_type AS type,
                   a.description AS description,
                   a.traits AS traits,
                   a.dynamic_state AS dynamic_state,
                   rel_count, rel_types
            LIMIT 5
            """
            result = session.run(cypher, name=agent_name)

        profiles = []
        for r in result:
            prof = {
                "uuid": r["uuid"],
                "name": r["name"],
                "type": r["type"],
                "description": r["description"],
                "traits": r["traits"],
                "dynamic_state": r["dynamic_state"],
                "relationship_count": r["rel_count"],
                "relationship_types": r["rel_types"],
            }
            profiles.append(prof)

        if not profiles:
            return {
                "found": False,
                "query": agent_name or agent_id,
                "message": "No agent found with that name/id",
            }

        return {
            "found": True,
            "count": len(profiles),
            "profiles": profiles,
        }


# ---------------------------------------------------------------------------
#  Tool 4: mories_graph_query
# ---------------------------------------------------------------------------

GRAPH_QUERY_DESCRIPTION = (
    "Execute a Cypher query against the Neo4j knowledge graph. "
    "READ-ONLY mode enforced for security. "
    "Use this for custom graph traversals, aggregations, and pattern matching."
)

# Forbidden Cypher keywords for write protection
_WRITE_KEYWORDS = {
    "CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP",
    "DETACH", "CALL {", "FOREACH",
}


def mories_graph_query(
    cypher: str,
    params: dict | None = None,
    limit: int = 50,
    **kwargs
) -> dict:
    """
    Execute a read-only Cypher query.

    Args:
        cypher: Cypher query string (READ-ONLY enforced)
        params: Optional query parameters dict
        limit: Safety limit appended if no LIMIT in query

    Returns:
        dict with 'columns' and 'rows'
    """
    _rate_check()
    _allowed_scopes = kwargs.get("_allowed_scopes", ["*"])
    if "*" not in _allowed_scopes:
        return {"error": "Unauthorized. `mories_graph_query` requires full admin scope (*)."}

    # Security: block write operations
    if MCPConfig.READ_ONLY_CYPHER:
        upper = cypher.upper().strip()
        for kw in _WRITE_KEYWORDS:
            if kw in upper:
                return {
                    "error": f"Write operation blocked: '{kw}' not allowed in read-only mode",
                    "hint": "Set MCP_READ_ONLY=false to allow writes",
                }

    # Safety: append LIMIT if not present
    if "LIMIT" not in cypher.upper():
        cypher = cypher.rstrip().rstrip(";") + f"\nLIMIT {limit}"

    driver = _get_neo4j_driver()
    params = params or {}

    try:
        with driver.session() as session:
            result = session.run(cypher, **params)
            columns = result.keys()
            rows = []
            for record in result:
                row = {}
                for col in columns:
                    val = record[col]
                    # Convert Neo4j node/relationship to dict
                    if hasattr(val, "items"):
                        row[col] = dict(val.items())
                    elif hasattr(val, "__iter__") and not isinstance(val, str):
                        row[col] = list(val)
                    else:
                        row[col] = val
                rows.append(row)

            return {
                "columns": list(columns),
                "row_count": len(rows),
                "rows": rows,
            }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
#  Tool 5: mories_stream
# ---------------------------------------------------------------------------

STREAM_DESCRIPTION = (
    "Control stream ingestion adapters (Webhook, Kafka, REST polling). "
    "Start, stop, or list active real-time data streams."
)


def mories_stream(
    action: str,
    graph_id: str = "",
    source_ref: str = "",
    config: dict | None = None,
    **kwargs
) -> dict:
    """
    Control stream ingestion.

    Args:
        action: One of 'start', 'stop', 'list'
        graph_id: Target graph ID (for start)
        source_ref: Stream source (e.g. 'kafka://broker:9092')
        config: Stream configuration dict

    Returns:
        dict with stream status
    """
    _rate_check()
    _allowed_scopes = kwargs.get("_allowed_scopes", ["*"])
    if action in ["start"] and "*" not in _allowed_scopes and graph_id not in _allowed_scopes:
        return {"error": f"Unauthorized. Missing permission for graph_id: '{graph_id}'."}

    client = _get_api_client()

    if action == "list":
        try:
            resp = client.get("/api/ingest/streams")
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    elif action == "start":
        if not graph_id or not source_ref:
            return {"error": "graph_id and source_ref required for start"}
        payload = {
            "graph_id": graph_id,
            "source_ref": source_ref,
            "config": config or {},
        }
        try:
            resp = client.post("/api/ingest/stream", json=payload)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    elif action == "stop":
        if not source_ref:
            return {"error": "source_ref required for stop"}
        try:
            resp = client.delete(
                "/api/ingest/stream", params={"source_ref": source_ref}
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    else:
        return {"error": f"Unknown action: {action}. Use start/stop/list"}


# ---------------------------------------------------------------------------
#  Tool 8: mories_update_status (Lightweight Whiteboard)
# ---------------------------------------------------------------------------

_VALID_STATUSES = {"pending", "in_progress", "completed", "blocked"}


def mories_update_status(
    uuid: str,
    status: str = "",
    priority: int | None = None,
    assigned_to: str = "",
    **kwargs
) -> dict:
    """
    Update status fields on a memory/entity node — Lightweight Whiteboard.

    Replaces the deleted Orchestration Blackboard (384 lines, was causing
    zombie Neo4j drivers). Instead of a separate state management system,
    we add simple status fields to existing Entity/Memory nodes.

    Args:
        uuid: Target node UUID
        status: New status (pending/in_progress/completed/blocked)
        priority: Task priority (1=highest, optional)
        assigned_to: Agent UUID to assign the task to (optional)

    Returns:
        dict with updated node summary
    """
    _rate_check()

    if not uuid:
        return {"error": "uuid is required"}

    if status and status not in _VALID_STATUSES:
        return {
            "error": f"Invalid status '{status}'. Must be one of: {sorted(_VALID_STATUSES)}"
        }

    if not status and priority is None and not assigned_to:
        return {"error": "At least one of status, priority, or assigned_to must be provided"}

    driver = _get_driver()

    # Build dynamic SET clause
    set_parts = ["n.updated_at = datetime()"]
    params = {"uuid": uuid}

    if status:
        set_parts.append("n.status = $status")
        params["status"] = status
    if priority is not None:
        set_parts.append("n.priority = $priority")
        params["priority"] = priority
    if assigned_to:
        set_parts.append("n.assigned_to = $assigned_to")
        params["assigned_to"] = assigned_to

    set_clause = ", ".join(set_parts)

    cypher = f"""
    MATCH (n)
    WHERE n.uuid = $uuid AND (n:Entity OR n:Memory)
    SET {set_clause}
    RETURN n.uuid AS uuid,
           n.name AS name,
           n.entity_type AS type,
           n.status AS status,
           n.priority AS priority,
           n.assigned_to AS assigned_to,
           n.updated_at AS updated_at
    """

    try:
        with driver.session() as session:
            result = session.run(cypher, **params).single()
            if not result:
                return {"error": f"Node not found: {uuid}"}

            response = {
                "uuid": result["uuid"],
                "name": result["name"],
                "type": result["type"],
                "status": result["status"],
                "updated_at": str(result["updated_at"]),
            }
            if result["priority"] is not None:
                response["priority"] = result["priority"]
            if result["assigned_to"]:
                response["assigned_to"] = result["assigned_to"]

            return {
                "result": response,
                "_hint": "Use mories_search(status='in_progress') to find active tasks",
            }
    except Exception as e:
        return {"error": str(e)}

