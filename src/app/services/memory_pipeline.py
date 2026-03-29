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

# ── Semantic Compression: Type Icons ──────────────
# Mories uses type-prefixed summaries for search accuracy.
# Format: "{icon} {actionable_summary}"
# Example: "🔴 Neo4j driver leak: use singleton, don't create inside functions"
_MEMORY_TYPE_ICONS = {
    "gotcha":         "🔴",
    "fix":            "🟡",
    "how-it-works":   "🔵",
    "decision":       "🟤",
    "rule":           "📏",
    "fact":           "📝",
    "event":          "📅",
    "person":         "👤",
    "organization":   "🏢",
    "concept":        "💡",
    "task":           "🎯",
    "project":        "📦",
    "default":        "📌",
}


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
    ) -> Dict[str, Any]:
        """
        Process ingestion output through memory pipeline.

        1. Chunk text → STM items
        2. Evaluate salience (rule-based)
        3. Auto-promote high-salience items
        """
        result = {
            "source": source_ref,
            "graph_id": graph_id,
            "stm_created": 0,
            "auto_promoted": 0,
            "discarded": 0,
            "duplicates_skipped": 0,
            "task_aligned": 0,
            "items": [],
        }

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
            f"{result['task_aligned']} task-aligned, "
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
            ltm_uuid = promote_result.get("ltm_uuid")
            aligned_tasks = []
            if ltm_uuid:
                self._set_scope(ltm_uuid, scope)
                self._tag_with_graph_id(ltm_uuid, graph_id)
                # Task-Memory Alignment: auto-link to related active tasks
                aligned_tasks = self._align_to_tasks(ltm_uuid, content, graph_id)
            return {
                "content": content[:60],
                "action": "auto_promoted",
                "salience": salience,
                "ltm_uuid": ltm_uuid,
                "task_aligned": len(aligned_tasks),
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
    # Semantic Compression
    # ──────────────────────────────────────────

    def compress_summary(self, content: str, entity_type: str = "default") -> str:
        """
        Apply Semantic Compression to a memory summary.

        Format: "{icon} {actionable_one_liner}"
        - Bad:  "Neo4j 관련 작업을 수행함"
        - Good: "🔴 Neo4j driver leak: 함수 내 GraphDatabase.driver() 생성 금지 → 싱글턴 재사용"
        """
        icon = _MEMORY_TYPE_ICONS.get(entity_type.lower(), _MEMORY_TYPE_ICONS["default"])

        # Strip leading/trailing whitespace and normalize
        summary = content.strip()

        # If already icon-prefixed, return as-is
        if summary and summary[0] in '🔴🟡🔵🟤📌📏📝📅👤🏢💡🎯📦':
            return summary

        # Truncate to one actionable line
        first_line = summary.split('\n')[0][:120]
        return f"{icon} {first_line}"

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
        """Set scope on a promoted LTM node. Uses manager\'s existing driver."""
        try:
            storage = self._manager._storage
            if hasattr(storage, 'driver') and storage.driver:
                with storage.driver.session() as session:
                    session.run(
                        "MATCH (e:Entity {uuid: $uuid}) SET e.scope = $scope",
                        uuid=uuid, scope=scope,
                    )
            else:
                logger.warning("No driver available for _set_scope, skipping scope=%s for uuid=%s", scope, uuid)
        except Exception as e:
            logger.warning("Failed to set scope for %s: %s", uuid, e)

    def _tag_with_graph_id(self, uuid: str, graph_id: str):
        """Tag a promoted LTM node with its origin graph_id."""
        if not graph_id:
            return
        try:
            storage = self._manager._storage
            if hasattr(storage, 'driver') and storage.driver:
                with storage.driver.session() as session:
                    session.run(
                        "MATCH (e:Entity {uuid: $uuid}) SET e.graph_id = $graph_id",
                        uuid=uuid, graph_id=graph_id,
                    )
        except Exception as e:
            logger.warning("Failed to tag graph_id for %s: %s", uuid, e)

    # ──────────────────────────────────────────
    # Phase 4-2: Task-Memory Alignment
    # ──────────────────────────────────────────

    def _align_to_tasks(self, memory_uuid: str, content: str, graph_id: str) -> list:
        """
        Auto-create RELATES_TO_TASK relationships from a new memory to
        active task nodes whose keywords overlap with the memory content.

        Strategy:
          1. Find active task nodes in the same graph (status = in_progress/pending)
          2. Score keyword overlap against memory content
          3. Create RELATES_TO_TASK edge if similarity > threshold

        Returns list of linked task UUIDs.
        """
        linked = []
        try:
            storage = self._manager._storage
            if not (hasattr(storage, 'driver') and storage.driver):
                return linked

            # 1. Fetch candidate active tasks
            candidate_cypher = """
            MATCH (t:Entity)
            WHERE t.entity_type IN ['task', 'project']
              AND t.status IN ['pending', 'in_progress']
              AND (t.graph_id = $graph_id OR $graph_id = '')
            RETURN t.uuid AS uuid, t.name AS name,
                   COALESCE(t.summary, t.description, t.name) AS body
            LIMIT 20
            """
            with storage.driver.session() as session:
                tasks = list(session.run(candidate_cypher, graph_id=graph_id))

            # 2. Score keyword overlap
            content_words = set(re.findall(r'[\w가-힣]{3,}', content.lower()))
            for task in tasks:
                task_words = set(re.findall(r'[\w가-힣]{3,}', (task['body'] or '').lower()))
                if not task_words:
                    continue
                overlap = len(content_words & task_words) / max(len(task_words), 1)
                if overlap >= 0.15:  # 15% word overlap threshold
                    # 3. Create relationship
                    rel_cypher = """
                    MATCH (m:Entity {uuid: $mem_uuid})
                    MATCH (t:Entity {uuid: $task_uuid})
                    MERGE (m)-[r:RELATES_TO_TASK]->(t)
                    ON CREATE SET r.created_at = datetime(),
                                  r.overlap_score = $score
                    ON MATCH SET  r.updated_at = datetime()
                    RETURN r
                    """
                    with storage.driver.session() as session:
                        session.run(
                            rel_cypher,
                            mem_uuid=memory_uuid,
                            task_uuid=task['uuid'],
                            score=round(overlap, 3),
                        )
                    linked.append(task['uuid'])
                    logger.debug(
                        "Task-Memory aligned: %s → %s (overlap=%.2f)",
                        memory_uuid[:8], task['uuid'][:8], overlap,
                    )
        except Exception as e:
            logger.warning("Task-Memory alignment failed: %s", e)
        return linked
