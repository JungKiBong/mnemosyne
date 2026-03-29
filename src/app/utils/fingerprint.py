"""
Content Fingerprint — Incremental update support for Mories knowledge graph.

Maintains SHA-256 hashes for each data source and its sections,
enabling delta-only updates when sources are re-ingested.

Inspired by Understand-Anything's fingerprint.ts which tracks
per-file hashes to avoid reprocessing unchanged files.

Usage:
    fp = ContentFingerprint(storage)
    diff = fp.compare("report.pdf", new_fingerprint, new_sections)
    # diff.added → sections to process
    # diff.modified → sections to update
    # diff.deleted → sections to remove from graph
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

logger = logging.getLogger("mirofish.fingerprint")


@dataclass
class SectionFingerprint:
    """Hash of a single section within a document."""
    section_name: str
    fingerprint: str
    char_count: int


@dataclass
class SourceFingerprint:
    """Complete fingerprint of a data source."""
    source_ref: str
    global_fingerprint: str         # Hash of entire content
    section_fingerprints: List[SectionFingerprint] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "global_fingerprint": self.global_fingerprint,
            "sections": [
                {"name": s.section_name, "fp": s.fingerprint, "chars": s.char_count}
                for s in self.section_fingerprints
            ],
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class FingerprintDiff:
    """
    Result of comparing old and new fingerprints.

    Tells the pipeline exactly what changed so only
    the delta needs to be processed.
    """
    source_ref: str
    is_new: bool = False            # First time seeing this source
    is_unchanged: bool = False      # Nothing changed
    added: List[str] = field(default_factory=list)      # New sections
    modified: List[str] = field(default_factory=list)    # Changed sections
    deleted: List[str] = field(default_factory=list)     # Removed sections
    unchanged: List[str] = field(default_factory=list)   # Same sections

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    def summary(self) -> str:
        if self.is_new:
            return f"NEW source: {self.source_ref}"
        if self.is_unchanged:
            return f"UNCHANGED: {self.source_ref}"
        parts = []
        if self.added:
            parts.append(f"+{len(self.added)} added")
        if self.modified:
            parts.append(f"~{len(self.modified)} modified")
        if self.deleted:
            parts.append(f"-{len(self.deleted)} deleted")
        if self.unchanged:
            parts.append(f"={len(self.unchanged)} unchanged")
        return f"DELTA [{self.source_ref}]: {', '.join(parts)}"


class ContentFingerprint:
    """
    Manages content fingerprints in Neo4j for incremental updates.

    Stores fingerprint data as properties on a :SourceFingerprint node,
    linked to the graph via [:HAS_FINGERPRINT] edge.
    """

    def __init__(self, neo4j_driver=None):
        """
        Args:
            neo4j_driver: Optional Neo4j driver instance.
                          If None, uses Config to create one.
        """
        self._driver = neo4j_driver

    @property
    def driver(self):
        """Lazy-initialize Neo4j driver."""
        if self._driver is None:
            from neo4j import GraphDatabase
            from ..config import Config
            self._driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
        return self._driver

    @staticmethod
    def hash_text(text: str) -> str:
        """Generate SHA-256 hash for text content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_sections(sections: List[Dict[str, str]]) -> Dict[str, str]:
        """
        Hash each section independently.

        Args:
            sections: List of {"name": str, "content": str}

        Returns:
            Dict mapping section name to its hash
        """
        return {
            s["name"]: hashlib.sha256(s["content"].encode("utf-8")).hexdigest()
            for s in sections
        }

    def compare(
        self,
        source_ref: str,
        new_global_fp: str,
        new_section_fps: Dict[str, str],
    ) -> FingerprintDiff:
        """
        Compare new fingerprints against stored ones.

        Args:
            source_ref: Source identifier (file path, URL, etc.)
            new_global_fp: SHA-256 of entire content
            new_section_fps: {section_name: sha256_hash}

        Returns:
            FingerprintDiff describing what changed
        """
        stored = self._load_fingerprint(source_ref)

        # New source — never seen before
        if stored is None:
            diff = FingerprintDiff(
                source_ref=source_ref,
                is_new=True,
                added=list(new_section_fps.keys()),
            )
            logger.info(diff.summary())
            return diff

        # Quick check: global fingerprint unchanged
        if stored.global_fingerprint == new_global_fp:
            diff = FingerprintDiff(
                source_ref=source_ref,
                is_unchanged=True,
                unchanged=list(new_section_fps.keys()),
            )
            logger.info(diff.summary())
            return diff

        # Detailed section-level comparison
        old_fps = {s.section_name: s.fingerprint for s in stored.section_fingerprints}
        old_names = set(old_fps.keys())
        new_names = set(new_section_fps.keys())

        diff = FingerprintDiff(source_ref=source_ref)
        diff.added = list(new_names - old_names)
        diff.deleted = list(old_names - new_names)

        for name in old_names & new_names:
            if old_fps[name] != new_section_fps[name]:
                diff.modified.append(name)
            else:
                diff.unchanged.append(name)

        logger.info(diff.summary())
        return diff

    def save(
        self,
        source_ref: str,
        global_fp: str,
        section_fps: Dict[str, str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Save fingerprint data to Neo4j.

        Creates or updates a :SourceFingerprint node.
        """
        from datetime import datetime, timezone

        sections_json = json.dumps([
            {"name": name, "fp": fp}
            for name, fp in section_fps.items()
        ])
        ts = datetime.now(timezone.utc).isoformat()

        query = """
        MERGE (sf:SourceFingerprint {source_ref: $source_ref})
        SET sf.global_fingerprint = $global_fp,
            sf.sections = $sections_json,
            sf.metadata = $metadata_json,
            sf.updated_at = $timestamp
        """
        with self.driver.session() as session:
            session.run(
                query,
                source_ref=source_ref,
                global_fp=global_fp,
                sections_json=sections_json,
                metadata_json=json.dumps(metadata or {}),
                timestamp=ts,
            )

        logger.debug("Saved fingerprint: %s (fp=%s)", source_ref, global_fp[:12])

    def _load_fingerprint(self, source_ref: str) -> Optional[SourceFingerprint]:
        """Load stored fingerprint from Neo4j."""
        query = """
        MATCH (sf:SourceFingerprint {source_ref: $source_ref})
        RETURN sf.global_fingerprint AS global_fp,
               sf.sections AS sections_json,
               sf.metadata AS metadata_json,
               sf.updated_at AS timestamp
        """
        with self.driver.session() as session:
            result = session.run(query, source_ref=source_ref)
            record = result.single()

        if record is None:
            return None

        sections = []
        try:
            sections_data = json.loads(record["sections_json"] or "[]")
            for sd in sections_data:
                sections.append(SectionFingerprint(
                    section_name=sd["name"],
                    fingerprint=sd["fp"],
                    char_count=0,
                ))
        except (json.JSONDecodeError, KeyError):
            pass

        metadata = {}
        try:
            metadata = json.loads(record["metadata_json"] or "{}")
        except json.JSONDecodeError:
            pass

        return SourceFingerprint(
            source_ref=source_ref,
            global_fingerprint=record["global_fp"] or "",
            section_fingerprints=sections,
            metadata=metadata,
            timestamp=record["timestamp"] or "",
        )

    def delete(self, source_ref: str) -> None:
        """Remove stored fingerprint for a source."""
        query = """
        MATCH (sf:SourceFingerprint {source_ref: $source_ref})
        DETACH DELETE sf
        """
        with self.driver.session() as session:
            session.run(query, source_ref=source_ref)
        logger.info("Deleted fingerprint: %s", source_ref)

    def list_all(self) -> List[Dict[str, Any]]:
        """List all stored fingerprints (for admin/debug)."""
        query = """
        MATCH (sf:SourceFingerprint)
        RETURN sf.source_ref AS source_ref,
               sf.global_fingerprint AS global_fp,
               sf.updated_at AS timestamp
        ORDER BY sf.updated_at DESC
        """
        results = []
        with self.driver.session() as session:
            for record in session.run(query):
                results.append({
                    "source_ref": record["source_ref"],
                    "fingerprint": record["global_fp"][:12] + "...",
                    "updated_at": record["timestamp"],
                })
        return results

    def close(self):
        """Close Neo4j driver if we own it."""
        if self._driver:
            self._driver.close()
