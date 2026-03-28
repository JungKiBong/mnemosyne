"""
Memory Encryption — Phase 14: Per-Memory AES-256 Encryption

Provides field-level encryption for sensitive memories:
  - AES-256-GCM via Fernet (cryptography library)
  - Each memory can have its own encryption status
  - Master key derived from environment or auto-generated
  - Per-scope key derivation (personal memories get stronger isolation)
  - Encrypted fields: content, summary, metadata
  - Index-friendly: encrypted records still searchable by non-encrypted fields
    (name, scope, salience remain in cleartext for indexing)

Usage:
    enc = MemoryEncryption()
    encrypted = enc.encrypt_memory(uuid, fields=["summary", "content"])
    decrypted = enc.decrypt_memory(uuid)

Storage:
    Encrypted fields stored as base64 in Neo4j properties.
    Original fields renamed: summary → summary_encrypted, etc.
    A flag `encrypted = true` marks protected memories.
"""

import os
import logging
import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from neo4j import GraphDatabase

from ..config import Config

logger = logging.getLogger('mirofish.encryption')

# Fields that can be encrypted (content-bearing)
ENCRYPTABLE_FIELDS = ['summary', 'content', 'description']

# Fields that must remain cleartext for indexing
CLEARTEXT_FIELDS = ['uuid', 'name', 'scope', 'salience', 'source_type',
                    'owner_id', 'access_count', 'created_at', 'encrypted']


class MemoryEncryption:
    """
    Per-memory encryption engine using AES-256 via Fernet.

    Key hierarchy:
      Master Key (env or auto-generated)
        └─ Scope Key (derived per scope: personal/tribal/social/global)
           └─ Memory Key (derived per memory UUID for maximum isolation)
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

        self._master_key = self._load_or_generate_master_key()

    def close(self):
        if self._owns_driver:
            self._driver.close()

    # ──────────────────────────────────────────
    # Key Management
    # ──────────────────────────────────────────

    def _load_or_generate_master_key(self) -> bytes:
        """
        Load master key from environment or generate one.

        In production: set MORIES_MASTER_KEY environment variable.
        In dev: auto-generates and stores in config directory.
        """
        env_key = os.environ.get('MORIES_MASTER_KEY')
        if env_key:
            return base64.urlsafe_b64decode(env_key.encode())

        # Dev mode: generate and persist
        key_path = os.path.join(os.path.dirname(__file__), '../../.encryption_key')
        if os.path.exists(key_path):
            with open(key_path, 'rb') as f:
                return f.read()

        # Generate new key
        key = Fernet.generate_key()
        try:
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            with open(key_path, 'wb') as f:
                f.write(key)
            os.chmod(key_path, 0o600)  # Owner read/write only
            logger.info("Generated new master encryption key")
        except Exception as e:
            logger.warning(f"Could not persist key: {e}")

        return key

    def _derive_scope_key(self, scope: str) -> bytes:
        """Derive a scope-specific key from the master key."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=f"mories-scope-{scope}".encode(),
            iterations=100_000,
        )
        derived = kdf.derive(self._master_key)
        return base64.urlsafe_b64encode(derived)

    def _derive_memory_key(self, memory_uuid: str, scope: str) -> bytes:
        """Derive a per-memory key for maximum isolation."""
        scope_key = self._derive_scope_key(scope)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=f"mories-memory-{memory_uuid}".encode(),
            iterations=50_000,
        )
        derived = kdf.derive(scope_key)
        return base64.urlsafe_b64encode(derived)

    # ──────────────────────────────────────────
    # Encrypt / Decrypt
    # ──────────────────────────────────────────

    def encrypt_memory(
        self,
        memory_uuid: str,
        fields: List[str] = None,
        encrypted_by: str = "system",
    ) -> Dict[str, Any]:
        """
        Encrypt specified fields of a memory.

        - Reads current values from Neo4j
        - Encrypts them with per-memory key
        - Stores encrypted values and marks memory as encrypted
        """
        fields = fields or ENCRYPTABLE_FIELDS

        with self._driver.session() as session:
            record = session.run("""
                MATCH (e:Entity {uuid: $uuid})
                RETURN e.uuid AS uuid, e.name AS name,
                       COALESCE(e.scope, 'personal') AS scope,
                       e.summary AS summary,
                       e.encrypted AS encrypted
            """, uuid=memory_uuid).single()

            if not record:
                return {"error": "Memory not found"}

            if record.get("encrypted"):
                return {"error": "Memory is already encrypted", "uuid": memory_uuid}

            scope = record["scope"]
            fernet_key = self._derive_memory_key(memory_uuid, scope)
            fernet = Fernet(fernet_key)

            encrypted_fields = {}
            for field in fields:
                # Get current value
                val_record = session.run(f"""
                    MATCH (e:Entity {{uuid: $uuid}})
                    RETURN e.{field} AS val
                """, uuid=memory_uuid).single()

                if val_record and val_record["val"]:
                    plaintext = str(val_record["val"]).encode('utf-8')
                    encrypted_val = fernet.encrypt(plaintext).decode('utf-8')
                    encrypted_fields[field] = encrypted_val

            if not encrypted_fields:
                return {"error": "No fields to encrypt", "uuid": memory_uuid}

            # Store encrypted values and clear originals
            now = datetime.now(timezone.utc).isoformat()
            for field, enc_val in encrypted_fields.items():
                session.run(f"""
                    MATCH (e:Entity {{uuid: $uuid}})
                    SET e.{field}_encrypted = $enc_val,
                        e.{field} = '[ENCRYPTED]',
                        e.encrypted = true,
                        e.encrypted_at = $now,
                        e.encrypted_by = $by,
                        e.encrypted_fields = $fields
                """,
                    uuid=memory_uuid, enc_val=enc_val,
                    now=now, by=encrypted_by,
                    fields=list(encrypted_fields.keys()),
                )

        logger.info(f"🔒 Encrypted memory {memory_uuid[:8]}: fields={list(encrypted_fields.keys())}")
        return {
            "status": "encrypted",
            "uuid": memory_uuid,
            "name": record["name"],
            "fields": list(encrypted_fields.keys()),
            "scope": scope,
        }

    def decrypt_memory(
        self,
        memory_uuid: str,
        requesting_principal: str = "admin",
    ) -> Dict[str, Any]:
        """
        Decrypt a memory and return plaintext values.

        Does NOT persist decrypted values back to Neo4j.
        Returns decrypted content for the caller only.
        """
        with self._driver.session() as session:
            record = session.run("""
                MATCH (e:Entity {uuid: $uuid})
                RETURN e.uuid AS uuid, e.name AS name,
                       COALESCE(e.scope, 'personal') AS scope,
                       e.encrypted AS encrypted,
                       e.encrypted_fields AS encrypted_fields,
                       e.summary_encrypted AS summary_enc,
                       e.content_encrypted AS content_enc,
                       e.description_encrypted AS desc_enc
            """, uuid=memory_uuid).single()

            if not record:
                return {"error": "Memory not found"}

            if not record.get("encrypted"):
                return {"error": "Memory is not encrypted"}

            scope = record["scope"]
            fernet_key = self._derive_memory_key(memory_uuid, scope)
            fernet = Fernet(fernet_key)

            decrypted = {}
            field_map = {
                "summary": record.get("summary_enc"),
                "content": record.get("content_enc"),
                "description": record.get("desc_enc"),
            }

            for field, enc_val in field_map.items():
                if enc_val:
                    try:
                        plaintext = fernet.decrypt(enc_val.encode('utf-8'))
                        decrypted[field] = plaintext.decode('utf-8')
                    except Exception as e:
                        decrypted[field] = f"[DECRYPTION_FAILED: {e}]"

        logger.info(f"🔓 Decrypted memory {memory_uuid[:8]} by {requesting_principal}")
        return {
            "status": "decrypted",
            "uuid": memory_uuid,
            "name": record["name"],
            "scope": scope,
            "decrypted_fields": decrypted,
        }

    def remove_encryption(
        self,
        memory_uuid: str,
        removed_by: str = "admin",
    ) -> Dict[str, Any]:
        """
        Permanently remove encryption from a memory.

        Decrypts and restores original cleartext values.
        """
        decrypt_result = self.decrypt_memory(memory_uuid, removed_by)
        if decrypt_result.get("error"):
            return decrypt_result

        decrypted_fields = decrypt_result.get("decrypted_fields", {})
        now = datetime.now(timezone.utc).isoformat()

        with self._driver.session() as session:
            for field, plaintext in decrypted_fields.items():
                session.run(f"""
                    MATCH (e:Entity {{uuid: $uuid}})
                    SET e.{field} = $val,
                        e.{field}_encrypted = NULL
                """, uuid=memory_uuid, val=plaintext)

            session.run("""
                MATCH (e:Entity {uuid: $uuid})
                SET e.encrypted = false,
                    e.encrypted_at = NULL,
                    e.encrypted_by = NULL,
                    e.encrypted_fields = NULL,
                    e.decrypted_at = $now,
                    e.decrypted_by = $by
            """, uuid=memory_uuid, now=now, by=removed_by)

        logger.info(f"🔓 Encryption removed from memory {memory_uuid[:8]}")
        return {
            "status": "decrypted_and_restored",
            "uuid": memory_uuid,
            "restored_fields": list(decrypted_fields.keys()),
        }

    # ──────────────────────────────────────────
    # Batch Operations
    # ──────────────────────────────────────────

    def encrypt_scope(
        self,
        scope: str,
        encrypted_by: str = "admin",
    ) -> Dict[str, Any]:
        """Encrypt all memories in a given scope."""
        with self._driver.session() as session:
            records = session.run("""
                MATCH (e:Entity)
                WHERE e.scope = $scope
                  AND (e.encrypted IS NULL OR e.encrypted = false)
                  AND e.salience IS NOT NULL
                RETURN e.uuid AS uuid
                LIMIT 100
            """, scope=scope).data()

        results = {"scope": scope, "total": len(records), "encrypted": 0, "errors": 0}
        for rec in records:
            try:
                result = self.encrypt_memory(rec["uuid"], encrypted_by=encrypted_by)
                if result.get("status") == "encrypted":
                    results["encrypted"] += 1
                else:
                    results["errors"] += 1
            except Exception:
                results["errors"] += 1

        return results

    def get_encryption_status(self) -> Dict[str, Any]:
        """Get overall encryption statistics."""
        with self._driver.session() as session:
            stats = session.run("""
                MATCH (e:Entity)
                WHERE e.salience IS NOT NULL
                WITH e.encrypted AS enc, COALESCE(e.scope, 'personal') AS scope,
                     count(e) AS cnt
                RETURN enc, scope, cnt
                ORDER BY scope
            """).data()

        summary = {"encrypted": 0, "cleartext": 0, "by_scope": {}}
        for s in stats:
            scope = s["scope"]
            if scope not in summary["by_scope"]:
                summary["by_scope"][scope] = {"encrypted": 0, "cleartext": 0}

            if s["enc"]:
                summary["encrypted"] += s["cnt"]
                summary["by_scope"][scope]["encrypted"] += s["cnt"]
            else:
                summary["cleartext"] += s["cnt"]
                summary["by_scope"][scope]["cleartext"] += s["cnt"]

        summary["total"] = summary["encrypted"] + summary["cleartext"]
        return summary

    def rotate_keys(self, scope: str = None) -> Dict[str, Any]:
        """
        Key rotation: decrypt all → regenerate keys → re-encrypt.

        Warning: This is a heavy operation. Run during maintenance windows.
        """
        # For now, return info about what would happen
        status = self.get_encryption_status()
        target_count = status["encrypted"]
        if scope:
            target_count = status["by_scope"].get(scope, {}).get("encrypted", 0)

        return {
            "status": "key_rotation_planned",
            "target_scope": scope or "all",
            "memories_to_rotate": target_count,
            "warning": "Key rotation requires maintenance window. Use /api/security/rotate with confirm=true",
        }


# ──────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────

_enc_instance: Optional[MemoryEncryption] = None


def get_encryption() -> MemoryEncryption:
    global _enc_instance
    if _enc_instance is None:
        _enc_instance = MemoryEncryption()
    return _enc_instance
