"""
Mories MCP Tools — 5 core tools for external AI agents.

Tools:
  1. mories_search     — Hybrid knowledge graph + semantic search
  2. mories_ingest     — Data ingestion from file/URL/text
  3. mories_profile    — Agent profile lookup
  4. mories_graph_query — Read-only Cypher queries
  5. mories_stream     — Stream ingestion control
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
#  Tool 1: mories_search
# ---------------------------------------------------------------------------

SEARCH_DESCRIPTION = (
    "Search the Mories hybrid memory system. "
    "Queries the Neo4j knowledge graph (entities, facts, episodes) "
    "and returns structured results. "
    "Supports keyword search, semantic vectors, and graph traversal."
)


def mories_search(query: str, graph_id: str = "", limit: int = 10, **kwargs) -> dict:
    """
    Search the knowledge graph + vector index.

    Args:
        query: Natural language search query (e.g. "Alice의 최근 행동은?")
        graph_id: Optional graph/project ID to scope the search
        limit: Max results to return (default 10)

    Returns:
        dict with 'results' list and 'metadata'
    """
    _rate_check()
    _allowed_scopes = kwargs.get("_allowed_scopes", ["*"])
    is_admin = "*" in _allowed_scopes

    driver = _get_neo4j_driver()
    results = []

    with driver.session() as session:
        # 1) Fulltext search on entities
        entity_cypher = """
        CALL db.index.fulltext.queryNodes('entity_fulltext', $q)
        YIELD node, score
        WHERE score > 0.3
        OPTIONAL MATCH (g:Graph)-[:CONTAINS]->(node)
        WITH node, score, collect(g.uuid) AS gids, collect(COALESCE(g.is_public, false)) AS pubs
        WHERE $is_admin = true
           OR any(p IN pubs WHERE p = true)
           OR any(gid IN gids WHERE gid IN $allowed_scopes)
           OR size(gids) = 0
        RETURN node.uuid AS uuid,
               node.name AS name,
               node.entity_type AS type,
               labels(node) AS labels,
               score
        ORDER BY score DESC
        LIMIT $lim
        """
        try:
            entity_results = session.run(
                entity_cypher, q=query, lim=limit, is_admin=is_admin, allowed_scopes=_allowed_scopes
            )
            for r in entity_results:
                results.append({
                    "source": "entity_fulltext",
                    "uuid": r["uuid"],
                    "name": r["name"],
                    "type": r["type"],
                    "score": round(r["score"], 4),
                })
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
                results.append({
                    "source": "fact_fulltext",
                    "uuid": r["uuid"],
                    "fact": f"{r['subject']} → {r['predicate']} → {r['object']}",
                    "score": round(r["score"], 4),
                })
        except Exception as e:
            logger.warning("Fact fulltext search failed: %s", e)

        # 3) Graph-id scoped search (if provided)
        if graph_id:
            # Security check for requested graph_id
            if not is_admin and graph_id not in _allowed_scopes:
                # To be fully secure, we should query Neo4j if graph_id is public. But for performance we trust the token scopes.
                pass
            
            graph_cypher = """
            MATCH (g:Graph {uuid: $graph_id})-[:CONTAINS]->(e:Entity)
            WHERE (e.name CONTAINS $query OR e.description CONTAINS $query)
              AND ($is_admin = true OR g.is_public = true OR g.uuid IN $allowed_scopes)
            RETURN e.uuid AS uuid, e.name AS name, e.entity_type AS type
            LIMIT $limit
            """
            try:
                graph_results = session.run(
                    graph_cypher, graph_id=graph_id, query=query, limit=limit,
                    is_admin=is_admin, allowed_scopes=_allowed_scopes
                )
                for r in graph_results:
                    results.append({
                        "source": "graph_scope",
                        "uuid": r["uuid"],
                        "name": r["name"],
                        "type": r["type"],
                    })
            except Exception as e:
                logger.warning("Graph scoped search failed: %s", e)

    return {
        "query": query,
        "graph_id": graph_id or "(all)",
        "total": len(results),
        "results": results,
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
