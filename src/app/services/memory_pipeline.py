"""
Memory Pipeline — Ingest → STM → Evaluation → LTM Auto-flow

Connects the ingestion service to the cognitive memory system:
  1. Data comes in via ingest API → text extracted
  2. Auto-generates STM items from extracted knowledge
  3. LLM-based salience evaluation (or rule-based fallback)
  4. Auto-promote/discard based on thresholds
  5. Scope assignment based on source type
"""

import logging
import re
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger('mirofish.memory_pipeline')


class MemoryPipeline:
    """
    Bridges ingestion output to cognitive memory system.

    Called after ingestion completes. Transforms raw content
    into STM items and manages auto-promotion flow.
    """

    def __init__(self):
        from ..storage.memory_manager import MemoryManager
        self._manager = MemoryManager()
        self._processed_hashes = set()  # guard against duplicates

    def close(self):
        self._manager.close()

    # ──────────────────────────────────────────
    # Main Pipeline Entry
    # ──────────────────────────────────────────

    def process_ingestion_result(
        self,
        graph_id: str,
        source_ref: str,
        text: str,
        entities: List[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
        auto_promote: bool = True,
        incremental: bool = False,
    ) -> Dict[str, Any]:
        """
        Process ingestion output through memory pipeline.

        1. (Optional) Fingerprint check for incremental mode
        2. Chunk text → STM items
        3. Evaluate salience (rule-based, with node type awareness)
        4. Auto-promote high-salience items

        Args:
            incremental: If True, check fingerprint first and skip unchanged content
        """
        result = {
            "source": source_ref,
            "graph_id": graph_id,
            "stm_created": 0,
            "auto_promoted": 0,
            "discarded": 0,
            "duplicates_skipped": 0,
            "items": [],
            "incremental_status": "disabled",
        }

        # ── Incremental check ──
        if incremental and text:
            fp_manager = None
            try:
                from ..utils.fingerprint import ContentFingerprint
                # Reuse MemoryManager's existing Neo4j driver (DEF-H02 fix)
                fp_manager = ContentFingerprint(neo4j_driver=self._manager._driver)
                content_hash = ContentFingerprint.hash_text(text)
                diff = fp_manager.compare(source_ref, content_hash, {})
                result["incremental_status"] = diff.summary()

                if diff.is_unchanged:
                    logger.info("MemoryPipeline: source unchanged, skipping: %s", source_ref)
                    return result

                # Save new fingerprint
                fp_manager.save(source_ref, content_hash, {})
            except Exception as e:
                logger.warning("Fingerprint check failed (continuing): %s", e)
                result["incremental_status"] = f"error: {e}"

        # Determine scope from source type
        scope = self._infer_scope(source_ref, metadata or {})

        # Process pre-extracted entities
        if entities:
            for ent in entities:
                name = ent.get('name', '')
                etype = ent.get('type', 'Entity')
                content = f"{name} ({etype})"
                summary = ent.get('summary', '')
                if summary:
                    content = f"{name}: {summary}"

                item_result = self._process_single(
                    content=content,
                    source=f"ingest:{source_ref}",
                    salience=self._estimate_salience(content, ent),
                    scope=scope,
                    graph_id=graph_id,
                    auto_promote=auto_promote,
                )
                result["items"].append(item_result)
                result[item_result["action"]] = result.get(item_result["action"], 0) + 1

        # Process text chunks
        if text and len(text.strip()) > 20:
            chunks = self._smart_chunk(text)
            for chunk in chunks:
                item_result = self._process_single(
                    content=chunk,
                    source=f"ingest:{source_ref}",
                    salience=self._estimate_salience(chunk),
                    scope=scope,
                    graph_id=graph_id,
                    auto_promote=auto_promote,
                )
                result["items"].append(item_result)
                result[item_result["action"]] = result.get(item_result["action"], 0) + 1

        logger.info(
            f"Pipeline processed: {source_ref} → "
            f"{result['stm_created']} STM, "
            f"{result['auto_promoted']} promoted, "
            f"{result['discarded']} discarded"
        )
        return result

    # ──────────────────────────────────────────
    # Single Item Processing
    # ──────────────────────────────────────────

    def _process_single(
        self,
        content: str,
        source: str,
        salience: float,
        scope: str,
        graph_id: str,
        auto_promote: bool,
    ) -> dict:
        """Process a single content item through the pipeline."""
        # Dedup check
        content_hash = hashlib.md5(content.encode()).hexdigest()
        if content_hash in self._processed_hashes:
            return {"content": content[:60], "action": "duplicates_skipped"}
        self._processed_hashes.add(content_hash)

        # Add to STM
        item = self._manager.stm_add(
            content=content,
            source=source,
            metadata={"scope": scope, "graph_id": graph_id},
        )

        # Evaluate salience
        self._manager.stm_evaluate(item.id, salience)

        # Auto decision
        if auto_promote and salience >= self._manager.config.auto_promote_threshold:
            promote_result = self._manager.stm_promote(item.id, graph_id=graph_id)
            if promote_result.get("ltm_uuid"):
                self._set_scope(promote_result["ltm_uuid"], scope)
            return {
                "content": content[:60],
                "action": "auto_promoted",
                "salience": salience,
                "ltm_uuid": promote_result.get("ltm_uuid"),
            }
        elif salience <= self._manager.config.auto_discard_threshold:
            self._manager.stm_discard(item.id)
            return {"content": content[:60], "action": "discarded", "salience": salience}
        else:
            return {
                "content": content[:60],
                "action": "stm_created",
                "salience": salience,
                "stm_id": item.id,
                "note": "pending HITL review",
            }

    # ──────────────────────────────────────────
    # Salience Estimation (Rule-Based Fallback)
    # ──────────────────────────────────────────

    def _estimate_salience(self, content: str, entity: dict = None) -> float:
        """
        Estimate salience using heuristic rules.
        Returns 0.0~1.0.
        """
        score = 0.5  # base

        text = content.lower()

        # Length bonus — longer = more informative
        if len(content) > 200:
            score += 0.1
        elif len(content) < 30:
            score -= 0.1

        # Named entities / specific terms boost
        has_numbers = bool(re.search(r'\d+\.?\d*%|\$[\d,]+|\d{4}', content))
        if has_numbers:
            score += 0.1

        # Action/importance keywords
        important_keywords = [
            'important', 'critical', 'key', 'must', 'essential',
            '중요', '핵심', '필수', '주의', '결정', '전략',
            'deadline', 'milestone', 'breakthrough', 'risk',
        ]
        for kw in important_keywords:
            if kw in text:
                score += 0.05
                break

        # Source type boost from entity
        if entity:
            etype = entity.get('type', '').lower()
            if etype in ('person', 'organization', 'event'):
                score += 0.1
            if entity.get('properties'):
                score += 0.05  # structured data = more valuable

        return max(0.0, min(1.0, round(score, 2)))

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    def _infer_scope(self, source_ref: str, metadata: dict) -> str:
        """Infer memory scope from source type."""
        ref = source_ref.lower()
        if any(x in ref for x in ['kafka://', 'webhook://', 'stream']):
            return 'tribal'  # streaming = team-level
        elif any(x in ref for x in ['postgresql://', 'bolt://', 'import']):
            return 'social'  # DB imports = org-level
        elif metadata.get('scope'):
            return metadata['scope']
        return 'personal'

    def _smart_chunk(self, text: str, max_size: int = 400) -> List[str]:
        """Chunk text by paragraphs/sentences intelligently."""
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        chunks = []
        for para in paragraphs:
            if len(para) <= max_size:
                if len(para) > 20:
                    chunks.append(para)
            else:
                # Split by sentences
                sentences = re.split(r'(?<=[.!?。])\s+', para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) > max_size:
                        if current:
                            chunks.append(current.strip())
                        current = sent
                    else:
                        current += " " + sent
                if current.strip():
                    chunks.append(current.strip())
        return chunks[:50]  # cap

    def _set_scope(self, uuid: str, scope: str):
        """Set scope on a promoted LTM entity using the shared driver."""
        with self._manager._driver.session() as session:
            session.run("MATCH (e:Entity {uuid: $uuid}) SET e.scope = $scope",
                       uuid=uuid, scope=scope)

