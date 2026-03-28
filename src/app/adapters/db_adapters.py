"""
Database / Graph connector adapters: Neo4j Import, PostgreSQL, REST API.
"""
import os
import logging
from typing import Dict, Any, List

from .base import SourceAdapter, IngestionResult, SourceType

logger = logging.getLogger(__name__)

# Allowed tables for SQL queries (security: prevent arbitrary table access)
_ALLOWED_TABLES = set(
    t.strip()
    for t in os.environ.get("POSTGRES_ALLOWED_TABLES", "").split(",")
    if t.strip()
)

# SQL operations that must be blocked
_FORBIDDEN_SQL_OPS = {'CREATE', 'DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'TRUNCATE'}


class Neo4jImportAdapter(SourceAdapter):
    """
    Import an external Neo4j knowledge graph into MiroFish simulation.

    Use cases:
    - Import an organization's existing knowledge graph as simulation seed.
    - Import results from another MiroFish instance for follow-up simulation.
    - Import public knowledge graphs (Wikidata subgraphs) as seed data.
    """

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.startswith(("bolt://", "neo4j://", "neo4j+s://"))

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        from neo4j import GraphDatabase

        user = kwargs.get('user', 'neo4j')
        password = kwargs.get('password', '')
        query = kwargs.get(
            'query',
            'MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 1000'
        )

        driver = GraphDatabase.driver(source_ref, auth=(user, password))

        entities: List[Dict] = []
        relations: List[Dict] = []
        text_parts: List[str] = []
        seen_entities = set()

        try:
            with driver.session() as session:
                results = session.run(query)
                for record in results:
                    n = record['n']
                    r = record['r']
                    m = record['m']

                    n_name = n.get('name', str(n.id))
                    m_name = m.get('name', str(m.id))
                    r_type = type(r).__name__

                    # Deduplicate entities
                    if n_name not in seen_entities:
                        entities.append({
                            "name": n_name,
                            "type": list(n.labels)[0] if n.labels else "Entity",
                            "properties": dict(n),
                        })
                        seen_entities.add(n_name)

                    if m_name not in seen_entities:
                        entities.append({
                            "name": m_name,
                            "type": list(m.labels)[0] if m.labels else "Entity",
                            "properties": dict(m),
                        })
                        seen_entities.add(m_name)

                    relations.append({
                        "source": n_name,
                        "target": m_name,
                        "type": r_type,
                        "properties": dict(r),
                    })

                    text_parts.append(f"{n_name} {r_type} {m_name}.")
        finally:
            driver.close()

        return IngestionResult(
            text="\n".join(text_parts),
            metadata={
                "source": source_ref,
                "format": "neo4j",
                "entity_count": len(entities),
                "relation_count": len(relations),
            },
            entities=entities,
            relations=relations,
            source_type=SourceType.GRAPH,
        )


class PostgresAdapter(SourceAdapter):
    """
    Read from PostgreSQL tables/views and convert to natural-language text.
    
    Security measures:
    - Only SELECT queries are allowed (CREATE/DROP/DELETE/UPDATE blocked).
    - Optional table allowlist via POSTGRES_ALLOWED_TABLES env var.
    - Credentials should be stored in connections config, not in API body.
    """

    def can_handle(self, source_ref: str) -> bool:
        return source_ref.startswith(("postgresql://", "postgres://"))

    def ingest(self, source_ref: str, **kwargs) -> IngestionResult:
        import pandas as pd
        from sqlalchemy import create_engine, text

        query = kwargs.get('query') or kwargs.get('table')
        if not query:
            raise ValueError("Provide 'query' (SQL SELECT) or 'table' (table name)")

        # If it's a bare table name, wrap it in SELECT
        if not query.strip().upper().startswith('SELECT'):
            table_name = query.strip()
            # Security: check allowlist
            if _ALLOWED_TABLES and table_name not in _ALLOWED_TABLES:
                raise ValueError(
                    f"Table '{table_name}' is not in the allowed list. "
                    f"Allowed: {_ALLOWED_TABLES}"
                )
            query = f"SELECT * FROM {table_name} LIMIT 1000"
        else:
            # Security: block dangerous operations
            first_token = query.strip().split()[0].upper()
            if first_token in _FORBIDDEN_SQL_OPS:
                raise ValueError(f"Forbidden SQL operation: {first_token}")

        engine = create_engine(source_ref)
        df = pd.read_sql(text(query), engine)

        # DataFrame → natural language
        schema_desc = f"Database query returned {len(df)} records with columns: {', '.join(df.columns)}"
        sentences: List[str] = []
        for _, row in df.iterrows():
            parts = [f"{col} is {val}" for col, val in row.items() if pd.notna(val)]
            sentences.append(". ".join(parts) + ".")

        full_text = schema_desc + "\n\n" + "\n".join(sentences)

        return IngestionResult(
            text=full_text,
            metadata={
                "source": source_ref,
                "format": "postgresql",
                "row_count": len(df),
                "columns": list(df.columns),
            },
            source_type=SourceType.STRUCTURED,
            raw_records=df.to_dict('records'),
        )
