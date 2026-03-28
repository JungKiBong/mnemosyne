"""
Memory RBAC — Phase 13: Role-Based Access Control

Controls who can read, write, share, and admin memories:

  Principals:
    - user:<id>     — individual users
    - agent:<id>    — AI agents
    - team:<id>     — team groups
    - apikey:<key>  — external API keys

  Roles:
    - reader    — search, recall (read-only)
    - writer    — store, boost, modify
    - sharer    — share across scopes
    - admin     — full access (decay, config, rollback, encryption keys)

  Scope Permissions:
    - personal  — only owner
    - tribal    — team members
    - social    — organization-wide
    - global    — everyone (read), admin (write)

  API Keys:
    - Managed via /api/security/keys
    - Each key has: owner, roles, allowed_scopes, rate_limit
"""

import logging
import hashlib
import secrets
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.rbac')

class SecurityError(Exception): pass
class RateLimitExceeded(SecurityError): pass
class ApiKeyExpired(SecurityError): pass

# ──────────────────────────────────────────
# Permission Matrix
# ──────────────────────────────────────────

ROLE_PERMISSIONS = {
    "reader": {"search", "recall", "status", "history", "export"},
    "writer": {"search", "recall", "status", "history", "export",
               "store", "boost", "pipeline"},
    "sharer": {"search", "recall", "status", "history", "export",
               "store", "boost", "pipeline", "share", "empathy"},
    "admin":  {"search", "recall", "status", "history", "export",
               "store", "boost", "pipeline", "share", "empathy",
               "decay", "config", "rollback", "encrypt", "keys", "gateway"},
}

SCOPE_VISIBILITY = {
    "personal": ["owner"],            # Only the owner
    "tribal":   ["owner", "team"],    # Owner + team members
    "social":   ["owner", "team", "org"],  # Org-wide
    "global":   ["*"],                # Everyone
}


class MemoryRBAC:
    """
    Role-Based Access Control engine for memories.

    Manages principals, roles, API keys, and scope-based permissions.
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

        self._api_keys: Dict[str, Dict[str, Any]] = {}  # hash → principal
        self._rate_limit_cache: Dict[str, List[float]] = {}  # hash → list of sliding window timestamps
        self._ensure_schema()
        self._load_api_keys()

    def close(self):
        if self._owns_driver:
            self._driver.close()

    def _ensure_schema(self):
        queries = [
            "CREATE CONSTRAINT principal_id IF NOT EXISTS FOR (p:Principal) REQUIRE p.principal_id IS UNIQUE",
            "CREATE INDEX apikey_hash IF NOT EXISTS FOR (k:ApiKey) ON (k.key_hash)",
            "CREATE INDEX security_event_time IF NOT EXISTS FOR (e:SecurityEvent) ON (e.timestamp)",
        ]
        with self._driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.debug(f"RBAC schema: {e}")

    def _log_security_event(self, event_type: str, severity: str, details: dict):
        """Log a security event into the Audit Trail (Neo4j)."""
        try:
            with self._driver.session() as session:
                session.run("""
                    CREATE (e:SecurityEvent {
                        event_id: randomUUID(),
                        event_type: $event_type,
                        severity: $severity,
                        timestamp: datetime(),
                        details: $details
                    })
                """, event_type=event_type, severity=severity, details=json.dumps(details, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")

    # ──────────────────────────────────────────
    # Principal Management
    # ──────────────────────────────────────────

    def register_principal(
        self,
        principal_id: str,
        name: str,
        principal_type: str = "user",  # user, agent, team
        roles: List[str] = None,
        team_id: str = "",
    ) -> Dict[str, Any]:
        """Register a principal (user/agent/team)."""
        roles = roles or ["reader"]
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            session.run("""
                MERGE (p:Principal {principal_id: $pid})
                SET p.name = $name,
                    p.type = $ptype,
                    p.roles = $roles,
                    p.team_id = $team_id,
                    p.created_at = COALESCE(p.created_at, $now),
                    p.last_active = $now,
                    p.active = true
            """,
                pid=principal_id, name=name, ptype=principal_type,
                roles=roles, team_id=team_id, now=now,
            )

        logger.info(f"Principal registered: {name} ({principal_id}) roles={roles}")
        return {"principal_id": principal_id, "name": name, "roles": roles, "type": principal_type}

    def list_principals(self, principal_type: str = None) -> List[Dict[str, Any]]:
        """List all principals."""
        type_filter = "AND p.type = $ptype" if principal_type else ""
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (p:Principal)
                WHERE p.active = true {type_filter}
                RETURN p.principal_id AS principal_id, p.name AS name,
                       p.type AS type, p.roles AS roles,
                       p.team_id AS team_id,
                       p.created_at AS created_at,
                       p.last_active AS last_active
                ORDER BY p.last_active DESC
            """, ptype=principal_type or "").data()
        return records

    # ──────────────────────────────────────────
    # Permission Checks
    # ──────────────────────────────────────────

    def check_permission(
        self,
        principal_id: str,
        action: str,
        memory_scope: str = "personal",
        memory_owner: str = "",
    ) -> Dict[str, Any]:
        """
        Check if a principal has permission for an action on a memory.

        Returns: {"allowed": bool, "reason": str}
        """
        # Get principal
        principal = self._get_principal(principal_id)
        if not principal:
            return {"allowed": False, "reason": "Principal not found"}

        roles = principal.get("roles", [])
        team_id = principal.get("team_id", "")

        # Check role permissions
        allowed_actions = set()
        for role in roles:
            allowed_actions.update(ROLE_PERMISSIONS.get(role, set()))

        if action not in allowed_actions:
            return {"allowed": False, "reason": f"Role(s) {roles} don't have '{action}' permission"}

        # Check scope visibility
        if memory_scope == "personal" and memory_owner and memory_owner != principal_id:
            if "admin" not in roles:
                return {"allowed": False, "reason": "Cannot access others' personal memories"}

        if memory_scope == "tribal":
            # Must be in same team or admin
            if memory_owner and memory_owner != principal_id:
                if "admin" not in roles:
                    owner_principal = self._get_principal(memory_owner)
                    if owner_principal and owner_principal.get("team_id") != team_id:
                        return {"allowed": False, "reason": "Not in same team for tribal memory"}

        return {"allowed": True, "reason": "OK"}

    def _get_principal(self, principal_id: str) -> Optional[dict]:
        with self._driver.session() as session:
            record = session.run("""
                MATCH (p:Principal {principal_id: $pid})
                RETURN p.principal_id AS principal_id, p.name AS name,
                       p.type AS type, p.roles AS roles,
                       p.team_id AS team_id
            """, pid=principal_id).single()
        return dict(record) if record else None

    # ──────────────────────────────────────────
    # API Key Management
    # ──────────────────────────────────────────

    def generate_api_key(
        self,
        owner_id: str,
        name: str,
        roles: List[str] = None,
        allowed_scopes: List[str] = None,
        rate_limit: int = 100,  # requests per minute
        expires_in_days: int = 30,  # Default to 30 days. 0 = never
    ) -> Dict[str, Any]:
        """Generate a new API key.
        
        Args:
            expires_in_days: 0 = never expires, 1-3650 = days until expiration.
                             Negative values are rejected.
        """
        from datetime import timedelta

        # Input validation — governance: reject invalid expiration values
        if expires_in_days < 0:
            raise ValueError("expires_in_days must be >= 0 (0 = never expires)")
        if expires_in_days > 3650:  # 10 years max
            raise ValueError("expires_in_days must be <= 3650 (10 years)")

        raw_key = f"mnem_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        
        expires_at = None
        if expires_in_days > 0:
            expires_at = (now + timedelta(days=expires_in_days)).isoformat()

        roles = roles or ["writer"]
        allowed_scopes = allowed_scopes or ["personal", "tribal"]

        with self._driver.session() as session:
            session.run("""
                CREATE (k:ApiKey {
                    key_hash: $hash,
                    owner_id: $owner,
                    name: $name,
                    roles: $roles,
                    allowed_scopes: $scopes,
                    rate_limit: $rate_limit,
                    created_at: $now,
                    expires_at: $expires_at,
                    active: true,
                    usage_count: 0
                })
            """,
                hash=key_hash, owner=owner_id, name=name,
                roles=roles, scopes=allowed_scopes,
                rate_limit=rate_limit, now=now.isoformat(),
                expires_at=expires_at
            )

        # Update in-memory cache
        self._api_keys[key_hash] = {
            "owner_id": owner_id,
            "name": name,
            "roles": roles,
            "allowed_scopes": allowed_scopes,
            "rate_limit": rate_limit,
            "expires_at": expires_at,
        }

        logger.info(f"API key generated: {name} for {owner_id} (Expires: {expires_at or 'Never'})")
        return {
            "api_key": raw_key,  # Only returned once!
            "name": name,
            "owner_id": owner_id,
            "roles": roles,
            "allowed_scopes": allowed_scopes,
            "expires_at": expires_at,
            "warning": "Save this key — it won't be shown again",
        }

    def validate_api_key(self, raw_key: str) -> Optional[Dict[str, Any]]:
        """Validate an API key and return principal info."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        principal = self._api_keys.get(key_hash)

        if principal:
            # Check expiration — governance: expired keys MUST be rejected
            expires_at_str = principal.get("expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                # Ensure timezone-aware comparison
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)

                if now > expires_at:
                    logger.warning(
                        f"🚨 ACCESS DENIED: API key '{principal.get('name')}' "
                        f"expired at {expires_at_str}. Key hash: {key_hash[:12]}..."
                    )
                    self._log_security_event(
                        "API_KEY_EXPIRED_DENIAL", 
                        "CRITICAL", 
                        {"key_hash": key_hash[:16], "name": principal.get("name"), "owner_id": principal.get("owner_id"), "expires_at": expires_at_str}
                    )
                    raise ApiKeyExpired(f"API key expired at {expires_at_str}")
                    
                # Expiration warnings (logged per-request for ops visibility)
                days_left = (expires_at - now).days
                if days_left <= 0:
                    logger.warning(
                        f"⚠️ [URGENT] API key '{principal.get('name')}' "
                        f"expires TODAY or within 24 hours!"
                    )
                elif days_left <= 1:
                    logger.warning(
                        f"⚠️ [CRITICAL] API key '{principal.get('name')}' "
                        f"expires in {days_left} day(s)."
                    )
                elif days_left <= 5:
                    logger.info(
                        f"⚠️ [WARNING] API key '{principal.get('name')}' "
                        f"expires in {days_left} days."
                    )
                elif days_left <= 10:
                    logger.info(
                        f"ℹ️ [NOTICE] API key '{principal.get('name')}' "
                        f"expires in {days_left} days."
                    )
                    
            # Rate limiting check (sliding window)
            rate_limit = principal.get("rate_limit", 100)
            current_time = time.time()
            if key_hash not in self._rate_limit_cache:
                self._rate_limit_cache[key_hash] = []
                
            requests = self._rate_limit_cache[key_hash]
            # Prune requests older than 60 seconds
            requests = [req for req in requests if current_time - req < 60]
            
            if len(requests) >= rate_limit:
                logger.warning(f"🚨 RATE LIMIT EXCEEDED: API key '{principal.get('name')}' exceeded {rate_limit} req/min.")
                self._log_security_event(
                    "RATE_LIMIT_EXCEEDED", 
                    "WARNING", 
                    {"key_hash": key_hash[:16], "name": principal.get("name"), "owner_id": principal.get("owner_id"), "limit": rate_limit}
                )
                self._rate_limit_cache[key_hash] = requests  # Save pruned list
                raise RateLimitExceeded(f"Rate limit exceeded: {rate_limit} req/min")
                
            requests.append(current_time)
            self._rate_limit_cache[key_hash] = requests

            # Update usage count — only for valid (non-expired) keys
            try:
                with self._driver.session() as session:
                    session.run("""
                        MATCH (k:ApiKey {key_hash: $hash})
                        SET k.usage_count = COALESCE(k.usage_count, 0) + 1,
                            k.last_used = $now
                    """, hash=key_hash, now=datetime.now(timezone.utc).isoformat())
            except Exception:
                pass

        return principal

    def revoke_api_key(self, key_hash: str) -> dict:
        """Revoke an API key by its hash."""
        with self._driver.session() as session:
            session.run("""
                MATCH (k:ApiKey {key_hash: $hash})
                SET k.active = false
            """, hash=key_hash)

        self._api_keys.pop(key_hash, None)
        return {"status": "revoked", "key_hash": key_hash[:16] + "..."}

    def extend_api_key(self, key_hash: str, additional_days: int = 30) -> dict:
        """Extend an API key's expiration by a given number of days."""
        from datetime import timedelta
        
        principal = self._api_keys.get(key_hash)
        if not principal:
            return {"status": "error", "error": "API Key not found or inactive"}
            
        expires_at_str = principal.get("expires_at")
        now = datetime.now(timezone.utc)
        
        # If the key never expires, we don't need to extend it
        if not expires_at_str:
            return {"status": "skipped", "message": "Key does not expire"}
            
        current_exp = datetime.fromisoformat(expires_at_str)
        if current_exp.tzinfo is None:
            current_exp = current_exp.replace(tzinfo=timezone.utc)
            
        # If expired, extend from 'now', otherwise extend from current expiration
        base_time = now if current_exp < now else current_exp
        new_exp = base_time + timedelta(days=additional_days)
        new_exp_str = new_exp.isoformat()
        
        with self._driver.session() as session:
            session.run("""
                MATCH (k:ApiKey {key_hash: $hash})
                SET k.expires_at = $new_exp
            """, hash=key_hash, new_exp=new_exp_str)
            
        # Update cache
        self._api_keys[key_hash]["expires_at"] = new_exp_str
        
        logger.info(f"API key extended: {principal.get('name')} (New Expiry: {new_exp_str})")
        return {"status": "extended", "key_hash": key_hash[:16] + "...", "new_expires_at": new_exp_str}

    def list_api_keys(self, owner_id: str = None) -> List[Dict[str, Any]]:
        """List API keys (without showing the actual key)."""
        owner_filter = "AND k.owner_id = $owner" if owner_id else ""
        with self._driver.session() as session:
            records = session.run(f"""
                MATCH (k:ApiKey)
                WHERE k.active = true {owner_filter}
                RETURN k.key_hash AS key_hash, k.name AS name,
                       k.owner_id AS owner_id, k.roles AS roles,
                       k.allowed_scopes AS allowed_scopes,
                       k.rate_limit AS rate_limit,
                       k.expires_at AS expires_at,
                       k.usage_count AS usage_count,
                       k.created_at AS created_at,
                       k.last_used AS last_used
                ORDER BY k.created_at DESC
            """, owner=owner_id or "").data()
        return records

    def _load_api_keys(self):
        """Load active API keys into memory cache."""
        try:
            with self._driver.session() as session:
                records = session.run("""
                    MATCH (k:ApiKey)
                    WHERE k.active = true
                    RETURN k.key_hash AS hash, k.owner_id AS owner_id,
                           k.name AS name, k.roles AS roles,
                           k.allowed_scopes AS allowed_scopes,
                           k.expires_at AS expires_at,
                           k.rate_limit AS rate_limit
                """).data()

            for rec in records:
                self._api_keys[rec["hash"]] = {
                    "owner_id": rec["owner_id"],
                    "name": rec["name"],
                    "roles": rec["roles"],
                    "allowed_scopes": rec["allowed_scopes"],
                    "expires_at": rec["expires_at"],
                    "rate_limit": rec["rate_limit"],
                }

            logger.info(f"Loaded {len(records)} API keys into RBAC cache")
        except Exception as e:
            logger.debug(f"API key load: {e}")

    # ──────────────────────────────────────────
    # Security Audit & Admin
    # ──────────────────────────────────────────

    def get_security_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve the most recent security events for the Audit Trail."""
        try:
            with self._driver.session() as session:
                records = session.run("""
                    MATCH (e:SecurityEvent)
                    RETURN e.event_id AS event_id, e.event_type AS event_type,
                           e.severity AS severity, e.timestamp AS timestamp,
                           e.details AS details
                    ORDER BY e.timestamp DESC
                    LIMIT $limit
                """, limit=limit).data()
            
            # Details are stored as JSON strings, so parse them back.
            for rec in records:
                if isinstance(rec.get("details"), str):
                    try:
                        rec["details"] = json.loads(rec["details"])
                    except json.JSONDecodeError:
                        pass
                if rec.get("timestamp"):
                    if hasattr(rec["timestamp"], "isoformat"):
                        rec["timestamp"] = rec["timestamp"].isoformat()
            return records
        except Exception as e:
            logger.error(f"Failed to get security events: {e}")
            return []

    def update_api_key_rate_limit(self, key_hash: str, new_limit: int) -> Dict[str, Any]:
        """Dynamically update the rate limit for an API key."""
        try:
            with self._driver.session() as session:
                rec = session.run("""
                    MATCH (k:ApiKey {key_hash: $key_hash})
                    SET k.rate_limit = $new_limit, k.updated_at = datetime()
                    RETURN k.rate_limit AS rate_limit, k.name AS name
                """, key_hash=key_hash, new_limit=new_limit).single()
                
                if not rec:
                    return {"status": "error", "error": "API key not found"}
                
                # Update in-memory cache if present
                if key_hash in self._api_keys:
                    self._api_keys[key_hash]["rate_limit"] = new_limit
                
                logger.info(f"Updated rate limit for key '{rec['name']}' to {new_limit}")
                return {
                    "status": "success",
                    "key_hash": key_hash,
                    "new_rate_limit": new_limit
                }
        except Exception as e:
            logger.error(f"Failed to update API key rate limit: {e}")
            return {"status": "error", "error": str(e)}

    # ──────────────────────────────────────────
    # Role Info
    # ──────────────────────────────────────────

    def get_role_matrix(self) -> dict:
        """Get the full role-permission matrix."""
        return {role: sorted(perms) for role, perms in ROLE_PERMISSIONS.items()}


# ──────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────

_rbac_instance: Optional[MemoryRBAC] = None


def get_rbac() -> MemoryRBAC:
    global _rbac_instance
    if _rbac_instance is None:
        _rbac_instance = MemoryRBAC()
    return _rbac_instance
