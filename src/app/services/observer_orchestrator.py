"""
ObserverOrchestrator — Manages 3 parallel Observer Agents + bridges with GraphMemoryUpdater.

Usage:
    orchestrator = ObserverOrchestrator(storage, graph_id, llm_client)
    orchestrator.start()
    # ... feed activities ...
    orchestrator.observe(activity)
    # ... later ...
    orchestrator.stop()
"""
import logging
from typing import Optional, Dict, Any, List

from ..utils.llm_client import LLMClient
from ..storage.hybrid_storage import HybridStorage
from .observer_agent import ObserverAgent, ObserverType
from .graph_memory_updater import AgentActivity

logger = logging.getLogger(__name__)


class ObserverOrchestrator:
    """
    Creates and manages the 3 cognitive Observer Agents:
    - Personal Observer: personality, preferences, habits
    - Event Observer: key events, behavioral patterns
    - Social Observer: relationships, emotions, social context

    Activities are fanned out to all 3 observers in parallel.
    Each observer processes its batch independently and stores
    cognitive insights in Supermemory via HybridStorage.
    """

    def __init__(
        self,
        storage: HybridStorage,
        graph_id: str,
        llm_client: LLMClient,
        batch_size: int = 5,
    ):
        self.storage = storage
        self.graph_id = graph_id
        self.llm_client = llm_client
        self._running = False

        # Create the 3 parallel observers
        self.observers: Dict[ObserverType, ObserverAgent] = {
            ObserverType.PERSONAL: ObserverAgent(
                observer_type=ObserverType.PERSONAL,
                llm_client=llm_client,
                storage=storage,
                graph_id=graph_id,
                batch_size=batch_size,
            ),
            ObserverType.EVENT: ObserverAgent(
                observer_type=ObserverType.EVENT,
                llm_client=llm_client,
                storage=storage,
                graph_id=graph_id,
                batch_size=batch_size,
            ),
            ObserverType.SOCIAL: ObserverAgent(
                observer_type=ObserverType.SOCIAL,
                llm_client=llm_client,
                storage=storage,
                graph_id=graph_id,
                batch_size=batch_size,
            ),
        }

        self._total_observed = 0
        logger.info(
            "ObserverOrchestrator initialized with 3 observers for graph %s",
            graph_id,
        )

    def start(self):
        """Start all 3 observer agents."""
        if self._running:
            return
        self._running = True
        for obs_type, agent in self.observers.items():
            agent.start()
            logger.info("Started %s observer", obs_type.value)

    def stop(self):
        """Stop all 3 observer agents."""
        self._running = False
        for obs_type, agent in self.observers.items():
            agent.stop()
            logger.info("Stopped %s observer", obs_type.value)
        logger.info(
            "ObserverOrchestrator stopped. Total activities observed: %d",
            self._total_observed,
        )

    def observe(self, activity: AgentActivity):
        """Fan-out a single activity to all 3 observers."""
        if not self._running:
            return
        for agent in self.observers.values():
            agent.observe(activity)
        self._total_observed += 1

    def observe_batch(self, activities: List[AgentActivity]):
        """Fan-out a batch of activities."""
        for activity in activities:
            self.observe(activity)

    def get_stats(self) -> Dict[str, Any]:
        """Return basic stats."""
        return {
            "graph_id": self.graph_id,
            "running": self._running,
            "total_observed": self._total_observed,
            "observers": {
                obs_type.value: {
                    "queue_size": agent._queue.qsize(),
                }
                for obs_type, agent in self.observers.items()
            },
        }
