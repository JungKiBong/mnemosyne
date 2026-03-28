"""
ASMR Search Agent — Contextual memory retrieval for agent decision-making.

Three parallel search agents:
  1. Fact Agent:     Direct facts & explicit statements
  2. Context Agent:  Social cues, implications, related context
  3. Timeline Agent: Temporal reconstruction & relationship map

Usage:
    search = SearchAgent(storage, graph_id)
    context = search.retrieve("agent_42", "How does Alice feel about Bob?")
    # → merged SearchResult with facts, social context, and timeline
"""
import logging
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

from ..storage.hybrid_storage import HybridStorage
from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SearchMode(Enum):
    FACT = "fact"
    CONTEXT = "context"
    TIMELINE = "timeline"


@dataclass
class SearchResult:
    """Merged result from all 3 search agents."""
    facts: List[str] = field(default_factory=list)
    context: List[str] = field(default_factory=list)
    timeline: List[str] = field(default_factory=list)
    profile_summary: Optional[str] = None
    search_time_ms: float = 0.0

    def to_prompt_injection(self) -> str:
        """Format for insertion into an agent's LLM system prompt."""
        sections = []
        if self.profile_summary:
            sections.append(f"[Agent Profile]\n{self.profile_summary}")
        if self.facts:
            sections.append("[Known Facts]\n" + "\n".join(f"- {f}" for f in self.facts))
        if self.context:
            sections.append("[Social Context]\n" + "\n".join(f"- {c}" for c in self.context))
        if self.timeline:
            sections.append("[Timeline]\n" + "\n".join(f"- {t}" for t in self.timeline))
        return "\n\n".join(sections)


class SearchAgent:
    """
    Orchestrates 3 parallel ASMR search agents to provide rich context
    when an agent makes a decision during simulation.
    """

    def __init__(
        self,
        storage: HybridStorage,
        graph_id: str,
        llm_client: Optional[LLMClient] = None,
        max_workers: int = 3,
        profile_cache_rounds: int = 1,
    ):
        self.storage = storage
        self.graph_id = graph_id
        self.llm_client = llm_client
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="SearchAgent")

        # Profile caching: agent_name → (round_num, profile_data)
        self._profile_cache: Dict[str, tuple] = {}
        self._profile_cache_rounds = profile_cache_rounds

        logger.info("SearchAgent initialized for graph_id=%s", graph_id)

    def retrieve(
        self,
        agent_name: str,
        query: str,
        current_round: int = 0,
        search_limit: int = 10,
    ) -> SearchResult:
        """
        Retrieve context for an agent's decision-making.
        Runs 3 search agents in parallel and merges results.

        Args:
            agent_name: The agent requesting context
            query:       What the agent needs to know
            current_round: Current simulation round (for cache)
            search_limit:  Max results per search agent

        Returns:
            Merged SearchResult with facts, context, timeline.
        """
        start_time = time.time()
        container_tag = f"{self.graph_id}_{agent_name}"

        result = SearchResult()

        # 1. Profile retrieval (cached)
        result.profile_summary = self._get_cached_profile(agent_name, current_round)

        # 2. Parallel search across 3 modes
        futures = {}
        for mode in SearchMode:
            future = self._executor.submit(
                self._search_by_mode, mode, container_tag, query, search_limit
            )
            futures[future] = mode

        for future in as_completed(futures):
            mode = futures[future]
            try:
                items = future.result(timeout=10)
                if mode == SearchMode.FACT:
                    result.facts = items
                elif mode == SearchMode.CONTEXT:
                    result.context = items
                elif mode == SearchMode.TIMELINE:
                    result.timeline = items
            except Exception as e:
                logger.warning("Search agent (%s) failed: %s", mode.value, e)

        elapsed_ms = (time.time() - start_time) * 1000
        result.search_time_ms = round(elapsed_ms, 2)
        logger.debug(
            "SearchAgent retrieved for %s in %.1fms: facts=%d, context=%d, timeline=%d",
            agent_name, elapsed_ms, len(result.facts), len(result.context), len(result.timeline),
        )
        return result

    def _get_cached_profile(self, agent_name: str, current_round: int) -> Optional[str]:
        """Retrieve agent profile from Supermemory, with round-based caching."""
        cached = self._profile_cache.get(agent_name)
        if cached:
            cached_round, cached_profile = cached
            if current_round - cached_round < self._profile_cache_rounds:
                return cached_profile

        container_tag = f"{self.graph_id}_{agent_name}"
        try:
            if hasattr(self.storage, 'sm') and self.storage.sm:
                profile_data = self.storage.sm.profile(containerTag=container_tag)
                # Profile typically returns static/dynamic traits
                if isinstance(profile_data, dict):
                    static = profile_data.get('static', [])
                    dynamic = profile_data.get('dynamic', [])
                    summary_parts = []
                    if static:
                        summary_parts.append("Traits: " + ", ".join(static))
                    if dynamic:
                        summary_parts.append("Current state: " + ", ".join(dynamic))
                    summary = ". ".join(summary_parts) if summary_parts else None
                else:
                    summary = str(profile_data) if profile_data else None

                self._profile_cache[agent_name] = (current_round, summary)
                return summary
        except Exception as e:
            logger.warning("Profile retrieval failed for %s: %s", agent_name, e)
        return None

    def _search_by_mode(
        self,
        mode: SearchMode,
        container_tag: str,
        query: str,
        limit: int,
    ) -> List[str]:
        """Execute a single search agent query."""
        if not hasattr(self.storage, 'sm') or not self.storage.sm:
            return []

        # Prefix query based on search mode to bias results
        mode_prefixes = {
            SearchMode.FACT: "Direct facts and explicit statements about: ",
            SearchMode.CONTEXT: "Social implications and related context about: ",
            SearchMode.TIMELINE: "Temporal sequence and timeline regarding: ",
        }
        enriched_query = mode_prefixes.get(mode, "") + query

        try:
            results = self.storage.sm.search_memories(
                q=enriched_query,
                containerTag=container_tag,
                limit=limit,
            )

            # Extract text from search results
            items = []
            if isinstance(results, list):
                for r in results:
                    if isinstance(r, dict):
                        text = r.get('content', r.get('text', str(r)))
                    else:
                        text = str(r)
                    items.append(text)
            elif isinstance(results, dict):
                memories = results.get('memories', results.get('results', []))
                for m in memories:
                    if isinstance(m, dict):
                        items.append(m.get('content', m.get('text', str(m))))
                    else:
                        items.append(str(m))

            return items[:limit]

        except Exception as e:
            logger.warning("Search failed (mode=%s): %s", mode.value, e)
            return []

    def shutdown(self):
        """Clean up thread pool."""
        self._executor.shutdown(wait=False)
        logger.info("SearchAgent shutdown")
