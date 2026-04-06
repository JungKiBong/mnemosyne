"""
Workflow Recall Engine — Experience-driven planning advisor.

Queries Neo4j for past execution experiences similar to the current
workflow, providing:
  - Prior failure warnings (what went wrong before)
  - Successful pattern hints (what tool chains worked)
  - OODA planner integration (inject recall into orient phase)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkflowRecallEngine:
    """
    Recall past experiences from the memory backend to guide
    new workflow executions.

    Integrates with the OODA Planner's orient() phase.
    """

    def __init__(self, memory_backend=None):
        """
        Args:
            memory_backend: Any backend implementing find_patterns()
                            and find_reflections() (e.g., Neo4jMemoryBackend).
        """
        self._backend = memory_backend

    def recall_similar(
        self,
        domain: str,
        trigger: str = "",
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Recall past patterns and reflections relevant to the given domain.

        Returns:
            {
                "patterns": [...],       # Successful tool chains
                "reflections": [...],    # Past failure lessons
                "recommendations": str,  # Human-readable summary
            }
        """
        if not self._backend:
            return {
                "patterns": [],
                "reflections": [],
                "recommendations": "(No memory backend connected)",
            }

        patterns = []
        reflections = []

        try:
            if hasattr(self._backend, "find_patterns"):
                patterns = self._backend.find_patterns(
                    domain=domain, limit=limit
                )
        except Exception as e:
            logger.warning(f"[Recall] Failed to fetch patterns: {e}")

        try:
            if hasattr(self._backend, "find_reflections"):
                reflections = self._backend.find_reflections(
                    domain=domain, limit=limit
                )
        except Exception as e:
            logger.warning(f"[Recall] Failed to fetch reflections: {e}")

        recommendations = self._synthesize(patterns, reflections, trigger)

        return {
            "patterns": patterns,
            "reflections": reflections,
            "recommendations": recommendations,
        }

    def format_for_ooda(self, recall_result: Dict[str, Any]) -> str:
        """
        Format recall results as a context string for OODA planner.

        This string gets injected into the orient() prompt.
        """
        lines = []

        patterns = recall_result.get("patterns", [])
        if patterns:
            lines.append("=== Past Successful Patterns ===")
            for p in patterns:
                tc = p.get("tool_chain", [])
                if isinstance(tc, str):
                    tc = [tc]
                lines.append(
                    f"  - Domain: {p.get('domain', '?')} | "
                    f"Chain: {' → '.join(tc)}"
                )

        reflections = recall_result.get("reflections", [])
        if reflections:
            lines.append("\n=== Past Failure Lessons ===")
            for r in reflections:
                lines.append(
                    f"  ⚠ [{r.get('severity', 'medium')}] "
                    f"{r.get('lesson', r.get('event', '?'))}"
                )

        recs = recall_result.get("recommendations", "")
        if recs:
            lines.append(f"\n=== Recommendations ===\n{recs}")

        return "\n".join(lines) if lines else ""

    def _synthesize(
        self,
        patterns: List[dict],
        reflections: List[dict],
        trigger: str,
    ) -> str:
        """Synthesize human-readable recommendations from recalled data."""
        parts = []

        if reflections:
            high_sev = [
                r for r in reflections
                if r.get("severity") in ("high", "critical")
            ]
            if high_sev:
                parts.append(
                    f"⚠ {len(high_sev)} high-severity past failure(s) "
                    f"found for this domain. Review lessons before proceeding."
                )

        if patterns:
            # Find most common tool chain length
            chain_lengths = [
                len(p.get("tool_chain", []))
                for p in patterns
            ]
            avg_len = sum(chain_lengths) / len(chain_lengths) if chain_lengths else 0
            parts.append(
                f"✓ {len(patterns)} successful patterns found. "
                f"Average chain length: {avg_len:.0f} steps."
            )

        if not parts:
            return "No prior experiences found for this domain."

        return " ".join(parts)
