import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json

from neo4j import GraphDatabase

from ..config import Config
from .memory_audit import MemoryAudit
from ..security.memory_rbac import MemoryRBAC

logger = logging.getLogger('mirofish.terminology')


class TerminologyService:
    """
    Cognitive Governance — Terminology Standardization (Phase E)

    Manages TermMapping nodes to ensure consistent vocabulary across
    the knowledge graph. Supports versions (via SUPERSEDES), RBAC permissions,
    and retroactive migrations of memories.
    """

    def __init__(self, driver=None, audit=None, rbac=None):
        if driver:
            self._driver = driver
            self._owns_driver = False
        else:
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
            self._owns_driver = True

        self._audit = audit or MemoryAudit(driver=self._driver)
        self._rbac = rbac or MemoryRBAC(driver=self._driver)

        # In-memory cache for fast NER retrieval (TTL=60s)
        self._cache = {
            'timestamp': 0,
            'active_mappings': []
        }
        self._cache_ttl = 60

        self._ensure_schema()

    def close(self):
        if self._owns_driver:
            self._driver.close()

    # ──────────────────────────────────────────
    # Schema
    # ──────────────────────────────────────────

    def _ensure_schema(self):
        queries = [
            "CREATE CONSTRAINT term_uuid IF NOT EXISTS FOR (t:TermMapping) REQUIRE t.uuid IS UNIQUE",
            "CREATE INDEX term_scope_source IF NOT EXISTS FOR (t:TermMapping) ON (t.scope, t.source_term, t.is_active)",
            "CREATE INDEX term_scope IF NOT EXISTS FOR (t:TermMapping) ON (t.scope)",
            "CREATE INDEX term_owner IF NOT EXISTS FOR (t:TermMapping) ON (t.owner_id)",
        ]
        with self._driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.debug(f"Terminology schema warning: {e}")

    # ──────────────────────────────────────────
    # Cache & Extraction Support
    # ──────────────────────────────────────────

    def _invalidate_cache(self):
        self._cache['timestamp'] = 0

    def get_active_mappings_for_principal(self, principal_id: str) -> List[Dict[str, str]]:
        """
        Get collapsed mapping rules (Bottom-up priority: Personal > Tribal > Social > Global)
        for use in the NER pipeline. Uses cache.
        Returns: [{"source_term": "JS", "standard_term": "JavaScript"}]
        """
        # We need principal info to get the team and permissions
        principal = self._rbac._get_principal(principal_id)
        if not principal:
            return []

        team_id = principal.get('team_id')

        # Cache check? Mappings are basically global state combined with owner/team
        # For simplicity and correctness with scopes, we fetch active rules
        # where scope=global or scope=social or (scope=tribal and team_id) or (scope=personal and owner)
        
        # Here we do not fully cache by principal ID as it can explode, we could fetch from DB
        # or load all into memory and resolve. Given this is fast, let's fetch directly.
        # But for high load we can cache the all-active query.
        
        now = time.time()
        
        try:
            from app import cache_hits, cache_misses
        except ImportError:
            cache_hits = cache_misses = None
            
        if now - self._cache['timestamp'] > self._cache_ttl:
            if cache_misses:
                cache_misses.labels(entity_type='terminology').inc()
            with self._driver.session() as session:
                records = session.run("""
                    MATCH (t:TermMapping)
                    WHERE t.is_active = true
                    RETURN t.scope AS scope,
                           t.source_term AS source_term,
                           t.standard_term AS standard_term,
                           t.owner_id AS owner_id,
                           t.team_id AS team_id
                    ORDER BY 
                        CASE t.scope
                            WHEN 'global' THEN 1
                            WHEN 'social' THEN 2
                            WHEN 'tribal' THEN 3
                            WHEN 'personal' THEN 4
                        END ASC
                """).data()
                self._cache['active_mappings'] = records
                self._cache['timestamp'] = now
        else:
            if cache_hits:
                cache_hits.labels(entity_type='terminology').inc()

        all_mappings = self._cache['active_mappings']
        
        # Filter and resolve
        resolved = {}
        for m in all_mappings:
            scope = m['scope']
            source = m['source_term'].lower()
            
            # Check applicability
            if scope == 'personal' and m['owner_id'] != principal_id:
                continue
            if scope == 'tribal' and m['team_id'] != team_id:
                continue
                
            # Due to the order (ASC: global=1, personal=4), dictionary will override 
            # lower scopes with higher scopes automatically
            resolved[source] = m['standard_term']

        return [{"source_term": k, "standard_term": v} for k, v in resolved.items()]

    # ──────────────────────────────────────────
    # Permission Checks
    # ──────────────────────────────────────────

    def _check_term_permission(self, principal_id: str, action: str, scope: str, requested_team_id: str = None) -> bool:
        """Helper to enforce detailed RBAC specifically for terminology management."""
        principal = self._rbac._get_principal(principal_id)
        if not principal:
            return False
            
        roles = principal.get("roles", [])
        team_id = principal.get("team_id")
        
        from ..security.memory_rbac import ROLE_PERMISSIONS
        allowed_actions = set()
        for role in roles:
            allowed_actions.update(ROLE_PERMISSIONS.get(role, set()))
            
        if action not in allowed_actions:
            return False
            
        if "admin" in roles:
            return True
            
        # Write / Delete rules
        if action in ("term_write", "term_delete"):
            if scope in ("global", "social"):
                return False # Only admin can mod global/social
            if scope == "tribal":
                if "sharer" not in roles:
                    return False
                if requested_team_id and requested_team_id != team_id:
                    return False
            if scope == "personal":
                if "writer" not in roles and "sharer" not in roles:
                    return False

        if action == "term_migrate":
            if "admin" not in roles:
                return False

        return True

    # ──────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────

    def create_or_update_mapping(
        self,
        principal_id: str,
        scope: str,
        source_term: str,
        standard_term: str,
        entity_type: Optional[str] = None,
        description: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new mapping or creates a new version if one exists."""
        if not source_term or not standard_term:
            return {"error": "Missing source or standard term"}

        # Validate permission
        target_team = team_id if scope == 'tribal' else None
        if not self._check_term_permission(principal_id, "term_write", scope, target_team):
            return {"error": "Permission denied"}

        # Cycle detection: A -> B, check if there's any active B -> A
        if self._detect_cycle(source_term, standard_term, scope, principal_id, target_team):
            return {"error": "Cyclic mapping detected"}

        now = datetime.now(timezone.utc).isoformat()
        owner_id = principal_id if scope == 'personal' else None

        with self._driver.session() as session:
            # Check existing active
            existing = session.run("""
                MATCH (t:TermMapping {scope: $scope, is_active: true})
                WHERE toLower(t.source_term) = toLower($source_term)
                  AND (t.owner_id = $owner_id OR $owner_id IS NULL)
                  AND (t.team_id = $team_id OR $team_id IS NULL)
                RETURN t.uuid AS uuid, t.version AS version
            """, scope=scope, source_term=source_term, owner_id=owner_id, team_id=target_team).single()

            new_uuid = str(uuid.uuid4())

            if existing: # Update (Create new version + Supersede)
                old_uuid = existing["uuid"]
                new_version = existing["version"] + 1

                session.run("""
                    MATCH (old:TermMapping {uuid: $old_uuid})
                    SET old.is_active = false
                    CREATE (new:TermMapping {
                        uuid: $new_uuid,
                        scope: $scope,
                        source_term: $source_term,
                        standard_term: $standard_term,
                        entity_type: $entity_type,
                        description: $description,
                        is_active: true,
                        version: $version,
                        owner_id: $owner_id,
                        team_id: $team_id,
                        created_by: $created_by,
                        created_at: $now,
                        updated_at: $now
                    })
                    CREATE (new)-[:SUPERSEDES]->(old)
                """, old_uuid=old_uuid, new_uuid=new_uuid, scope=scope,
                     source_term=source_term, standard_term=standard_term,
                     entity_type=entity_type, description=description,
                     version=new_version, owner_id=owner_id, team_id=target_team,
                     created_by=principal_id, now=now)

                action = "term_update"
                reason = f"Updated V{existing['version']}->V{new_version}: {source_term} -> {standard_term} ({scope})"
                
            else: # Create
                session.run("""
                    CREATE (new:TermMapping {
                        uuid: $new_uuid,
                        scope: $scope,
                        source_term: $source_term,
                        standard_term: $standard_term,
                        entity_type: $entity_type,
                        description: $description,
                        is_active: true,
                        version: 1,
                        owner_id: $owner_id,
                        team_id: $team_id,
                        created_by: $created_by,
                        created_at: $now,
                        updated_at: $now
                    })
                """, new_uuid=new_uuid, scope=scope,
                     source_term=source_term, standard_term=standard_term,
                     entity_type=entity_type, description=description,
                     owner_id=owner_id, team_id=target_team,
                     created_by=principal_id, now=now)

                action = "term_create"
                reason = f"Created mapping: {source_term} -> {standard_term} ({scope})"
                new_version = 1

        self._invalidate_cache()
        self._audit.record(
            memory_uuid=new_uuid,
            field='term_mapping',
            old_value='',
            new_value=json.dumps({"source": source_term, "target": standard_term}),
            change_type=action,
            changed_by=principal_id,
            reason=reason
        )

        return {"status": "success", "uuid": new_uuid, "version": new_version}


    def delete_mapping(self, principal_id: str, mapping_uuid: str) -> Dict[str, Any]:
        """Soft-deletes a mapping by setting is_active=false."""
        with self._driver.session() as session:
            mapping = session.run(
                "MATCH (t:TermMapping {uuid: $uuid}) RETURN t", uuid=mapping_uuid
            ).single()
            
            if not mapping:
                return {"error": "Mapping not found"}
                
            m = mapping[0]
            if not self._check_term_permission(principal_id, "term_delete", m["scope"], m.get("team_id")):
                return {"error": "Permission denied"}

            session.run("""
                MATCH (t:TermMapping {uuid: $uuid})
                SET t.is_active = false, t.updated_at = $now
            """, uuid=mapping_uuid, now=datetime.now(timezone.utc).isoformat())

        self._invalidate_cache()
        self._audit.record(
            memory_uuid=mapping_uuid,
            field='term_mapping',
            old_value=m['source_term'],
            new_value='<deleted>',
            change_type='term_delete',
            changed_by=principal_id,
            reason=f"Deleted mapping: {m['source_term']} ({m['scope']})"
        )

        return {"status": "deleted", "uuid": mapping_uuid}


    def list_mappings(self, principal_id: str, scope_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List active mappings. Admins see all, others see according to scope."""
        principal = self._rbac._get_principal(principal_id)
        if not principal:
            return []
            
        is_admin = "admin" in principal.get("roles", [])
        team_id = principal.get("team_id")

        q = """
            MATCH (t:TermMapping)
            WHERE t.is_active = true
        """
        params = {}
        
        if scope_filter:
            q += " AND t.scope = $scope"
            params["scope"] = scope_filter
            
        if not is_admin:
            # Apply strict visibility rules
            q += """
                 AND (
                    t.scope IN ['global', 'social']
                    OR (t.scope = 'tribal' AND t.team_id = $team_id)
                    OR (t.scope = 'personal' AND t.owner_id = $owner_id)
                 )
            """
            params["team_id"] = team_id
            params["owner_id"] = principal_id

        q += " RETURN t ORDER BY t.created_at DESC"

        results = []
        with self._driver.session() as session:
            records = session.run(q, **params).data()
            for r in records:
                node = r['t']
                results.append({
                    "uuid": node.get("uuid"),
                    "scope": node.get("scope"),
                    "source_term": node.get("source_term"),
                    "standard_term": node.get("standard_term"),
                    "entity_type": node.get("entity_type"),
                    "description": node.get("description"),
                    "version": node.get("version"),
                    "created_at": node.get("created_at"),
                    "updated_at": node.get("updated_at") or node.get("created_at")
                })
        return results



    def _detect_cycle(self, source_term: str, target_term: str, scope: str, principal_id: str, team_id: str = None) -> bool:
        """
        Check if making source -> target creates a cycle.
        If target standardizes back to source eventually through active rules.
        """
        mappings = self.get_active_mappings_for_principal(principal_id)
        # build an override graph
        G = {}
        for m in mappings:
            # don't include the exact edge we are replacing if it is the same source
            if m["source_term"].lower() == source_term.lower():
                continue
            G[m["source_term"].lower()] = m["standard_term"].lower()
            
        # Add the new proposed edge
        G[source_term.lower()] = target_term.lower()

        # Follow path from source_term
        visited = set()
        current = source_term.lower()
        while current in G:
            if current in visited:
                return True # cycle
            visited.add(current)
            current = G[current]
            
        return False


    # ──────────────────────────────────────────
    # Migration
    # ──────────────────────────────────────────

    def preview_migration(self, principal_id: str, mapping_uuid: str) -> Dict[str, Any]:
        """Dry run migration to see how many entities would be affected."""
        # Any user with term_read can preview; scope is checked against the mapping's scope
        principal = self._rbac._get_principal(principal_id)
        if not principal:
            return {"error": "Principal not found"}

        with self._driver.session() as session:
            mapping = session.run("MATCH (t:TermMapping {uuid: $uuid}) RETURN t", uuid=mapping_uuid).single()
            if not mapping:
                return {"error": "Mapping not found"}
                
            m = mapping[0]
            source_term = m["source_term"]
            scope_filter = m["scope"]
            
            q = """
                MATCH (e:Entity)
                WHERE toLower(e.name) = toLower($source_term)
            """
            params = {"source_term": source_term}
            
            if scope_filter == "personal":
                q += " AND e.scope = 'personal' AND e.owner_id = $owner"
                params["owner"] = m.get("owner_id")
            elif scope_filter == "tribal":
                q += " AND e.scope = 'tribal' AND e.team_id = $team"
                params["team"] = m.get("team_id")
                
            cnt_result = session.run(q + " RETURN count(e) AS cnt", **params).single()
            cnt = cnt_result["cnt"] if cnt_result else 0

            # Fetch sample names for preview display
            sample_records = session.run(q + " RETURN e.name AS name LIMIT 10", **params).data()
            sample_affected = [r["name"] for r in sample_records]
            
            return {
                "mapping_uuid": mapping_uuid,
                "source_term": source_term,
                "standard_term": m["standard_term"],
                "affected_nodes": cnt,
                "affected_count": cnt,  # backward-compat alias
                "affected_scope": scope_filter,
                "sample_affected": sample_affected
            }


    def execute_migration(self, principal_id: str, mapping_uuid: str) -> Dict[str, Any]:
        """Execute migration batch."""
        if not self._check_term_permission(principal_id, "term_migrate", "global"):
             return {"error": "Permission denied for migration"}

        with self._driver.session() as session:
            mapping = session.run("MATCH (t:TermMapping {uuid: $uuid}) RETURN t", uuid=mapping_uuid).single()
            if not mapping:
                return {"error": "Mapping not found"}
                
            m = mapping[0]
            source_term = m["source_term"]
            standard_term = m["standard_term"]
            scope_filter = m["scope"]
            version = m["version"]

            q = """
                MATCH (e:Entity)
                WHERE toLower(e.name) = toLower($source_term)
            """
            params = {"source_term": source_term, "standard_term": standard_term, "new_version": version}
            
            if scope_filter == "personal":
                q += " AND e.scope = 'personal' AND e.owner_id = $owner"
                params["owner"] = m["owner_id"]
            if scope_filter == "tribal":
                q += " AND e.scope = 'tribal' AND e.team_id = $team"
                params["team"] = m["team_id"]

            # Batch processing
            q += """
                WITH e LIMIT 50
                SET e.name = $standard_term,
                    e.name_lower = toLower($standard_term),
                    e.term_migrated_at = datetime(),
                    e.term_migration_version = $new_version
                RETURN e.uuid AS euuid, e.name AS ename
            """
            
            total_migrated = 0
            while True:
                records = session.run(q, **params).data()
                if not records:
                    break
                    
                total_migrated += len(records)
                
                # Record in audit
                for r in records:
                    self._audit.record(
                        memory_uuid=r["euuid"],
                        field='name',
                        old_value=source_term,
                        new_value=standard_term,
                        change_type='term_migrate',
                        changed_by=principal_id,
                        reason=f"Migration V{version}: {source_term} -> {standard_term}"
                    )
                    
                time.sleep(0.5) # Prevent overloading Neo4j if massive table

        return {
            "status": "migrated",
            "mapping_uuid": mapping_uuid,
            "total_entities_migrated": total_migrated,
            "affected_nodes": total_migrated  # UI-compatible alias
        }
