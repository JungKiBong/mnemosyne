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
from .orchestrator_service import OrchestratorService

logger = logging.getLogger(__name__)


class ObserverOrchestrator:
    """
    Creates and manages the 3 cognitive Observer Agents.

    A single OrchestratorService instance is shared across all agents
    to avoid creating multiple Neo4j driver connections.
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

        # Single shared service instance (one Neo4j driver for all agents)
        self.orchestrator_svc = OrchestratorService()
        self.session_id: Optional[str] = None

        # Create the 3 parallel observers, sharing the service
        self.observers: Dict[ObserverType, ObserverAgent] = {
            obs_type: ObserverAgent(
                observer_type=obs_type,
                llm_client=llm_client,
                storage=storage,
                graph_id=graph_id,
                batch_size=batch_size,
                orchestrator_svc=self.orchestrator_svc,
            )
            for obs_type in ObserverType
        }

        self._total_observed = 0
        logger.info(
            "ObserverOrchestrator initialized with %d observers for graph %s",
            len(self.observers), graph_id,
        )

    def start(self):
        """Start all observer agents and create an Orchestration Session."""
        if self._running:
            return

        # Register a Blackboard Session
        try:
            self.session_id = self.orchestrator_svc.start_session(
                graph_id=self.graph_id,
                name="Cognitive Observation Loop",
                goal="Continuously monitor and extract insights from agent activities.",
            )
        except Exception as e:
            logger.warning("Failed to create blackboard session: %s", e)
            self.session_id = None

        self._running = True
        for obs_type, agent in self.observers.items():
            agent.session_id = self.session_id
            agent.start()
            logger.info("Started %s observer (session=%s)", obs_type.value, self.session_id)

    def stop(self):
        """Stop all observer agents and finalize the session."""
        self._running = False
        for obs_type, agent in self.observers.items():
            agent.stop()
            logger.info("Stopped %s observer", obs_type.value)

        # End the blackboard session (#11 fix: prevent zombie sessions)
        if self.session_id:
            try:
                self.orchestrator_svc.complete_session(self.graph_id, self.session_id)
                logger.info("Blackboard session %s completed", self.session_id)
            except Exception as e:
                logger.warning("Failed to complete blackboard session: %s", e)

        # Close the shared service (which closes its storage driver)
        self.orchestrator_svc.close()

        logger.info(
            "ObserverOrchestrator stopped. Total activities observed: %d",
            self._total_observed,
        )

    def observe(self, activity: AgentActivity):
        """Fan-out a single activity to all observers."""
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
            "session_id": self.session_id,
            "running": self._running,
            "total_observed": self._total_observed,
            "observers": {
                obs_type.value: {"queue_size": agent._queue.qsize()}
                for obs_type, agent in self.observers.items()
            },
        }
