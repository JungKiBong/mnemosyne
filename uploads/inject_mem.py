from neo4j import GraphDatabase
import os

from_env = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
driver = GraphDatabase.driver("bolt://neo4j:7687", auth=("neo4j", "mirofish"))

with driver.session() as s:
    res = s.run("""
    CREATE (m:AgentMemory {
        uuid: randomUUID(),
        title: "Neo4j Backend Connection Bug Fix & Unified Dashboard Setup",
        content: "Fixed 500 internal server error on /api/query by mapping the mcp_server module via Docker volume mapping. Applied Nginx no-cache rules for front-end updating, fixed empty DOM TypeError caused by toggleLoader() in graph.html, and integrated global navigation system.",
        scope: "project",
        relevance: 1.0,
        tags: ["troubleshooting", "docker", "neo4j", "bugfix"],
        timestamp: datetime()
    })
    RETURN m.title AS title
    """)
    record = res.single()
    print("Memory injected:", record["title"])

driver.close()
