"""
Observer Agent - Extract cognitive memory from agent activity logs.
"""
import logging
import threading
import json
import traceback
from enum import Enum
from typing import Dict, Any, List, Optional
from queue import Queue, Empty

from ..utils.llm_client import LLMClient
from ..storage.hybrid_storage import HybridStorage
from .graph_memory_updater import AgentActivity
from .orchestrator_service import OrchestratorService

logger = logging.getLogger(__name__)


class ObserverType(Enum):
    PERSONAL = "personal"    # Extract personal info, preferences, habits
    EVENT = "event"          # Extract events, behaviors, actions
    SOCIAL = "social"        # Extract relationships, social context, emotions


class ObserverAgent:
    """
    Sub-agent that monitors simulation activities and extracts cognitive memories.
    Results are saved to Supermemory via HybridStorage.
    Uses OrchestratorService to formally log operations on the Neo4j Blackboard.
    """

    def __init__(self,
                 observer_type: ObserverType,
                 llm_client: LLMClient,
                 storage: HybridStorage,
                 graph_id: str,
                 batch_size: int = 5,
                 orchestrator_svc: Optional['OrchestratorService'] = None):
        self.observer_type = observer_type
        self.llm_client = llm_client
        self.storage = storage
        self.graph_id = graph_id
        self.batch_size = batch_size

        self._queue: Queue = Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Shared with ObserverOrchestrator (no extra driver created)
        self.session_id: Optional[str] = None
        self.orchestrator_svc = orchestrator_svc

        logger.info("Initialized ObserverAgent: %s for %s", self.observer_type.value, graph_id)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"ObserverAgent-{self.observer_type.value}"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def observe(self, activity: AgentActivity):
        """Enqueue an activity to be observed."""
        if activity.action_type == "DO_NOTHING":
            return
        self._queue.put(activity)

    def _run_loop(self):
        batch = []
        while self._running or not self._queue.empty():
            try:
                try:
                    activity = self._queue.get(timeout=1.0)
                    batch.append(activity)

                    if len(batch) >= self.batch_size:
                        self._process_batch(batch)
                        batch.clear()
                except Empty:
                    if batch:
                        self._process_batch(batch)
                        batch.clear()
            except Exception as e:
                logger.error(f"Observer loop error ({self.observer_type.value}): {e}")

    def _process_batch(self, batch: List[AgentActivity]):
        if not batch:
            return

        # Prepare the log context
        log_lines = []
        for i, act in enumerate(batch):
            text_desc = act.to_episode_text()
            log_lines.append(f"[{i+1}] {text_desc}")
            
        logs_text = "\n".join(log_lines)
        
        task_assigned = False
        task_id = None
        
        # 1. Blackboard Register Task
        try:
            if self.session_id and self.orchestrator_svc:
                task_id = self.orchestrator_svc.queue_task(
                    graph_id=self.graph_id,
                    session_id=self.session_id,
                    name=f"Extract Insights ({self.observer_type.value.capitalize()})",
                    description=logs_text,
                    context_uuids=[]
                )
                self.orchestrator_svc.mark_task_in_progress(
                    graph_id=self.graph_id,
                    task_id=task_id,
                    agent_id=f"Observer_{self.observer_type.value}"
                )
                task_assigned = True
        except Exception as e:
            logger.warning("Failed to queue task on blackboard: %s", e)
        
        # 2. Execution logic
        system_prompt = self._get_system_prompt()
        user_prompt = f"Activity Logs:\n{logs_text}\n\nExtract insights based on your role. Return a JSON array."
        
        try:
            # We expect a JSON array from LLM
            # e.g. [{"agent_name": "Alice", "insight": "Alice prefers tech news", "confidence": 0.9}]
            response_text = self.llm_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                json_mode=True
            )
            
            insights = json.loads(response_text)
            if not isinstance(insights, list):
                insights = [insights]
                
            # Log extracted insights to Supermemory
            for insight in insights:
                agent_name = insight.get("agent_name")
                text_insight = insight.get("insight")
                
                if agent_name and text_insight:
                    # Tag it specifically to the agent's memory
                    container_tag = f"{self.graph_id}_{agent_name}"
                    
                    # Store via supermemory client in HybridStorage
                    if hasattr(self.storage, 'sm'):
                        self.storage.sm.add(
                            content=f"[{self.observer_type.value.upper()}] {text_insight}",
                            containerTag=container_tag,
                            metadata={"role": self.observer_type.value, "source": "observer"}
                        )
                        logger.debug(f"Observer ({self.observer_type.value}) extracted for {agent_name}: {text_insight}")

            # 3. Blackboard Mark Complete
            if task_assigned and task_id:
                self.orchestrator_svc.complete_task(
                    graph_id=self.graph_id,
                    task_id=task_id,
                    message=f"Extracted {len(insights)} insights."
                )

        except Exception as e:
            logger.error(f"Failed to process batch in Observer ({self.observer_type.value}): {e}")
            tb = traceback.format_exc()
            
            # 3b. Blackboard Mark Error
            if task_assigned and task_id:
                self.orchestrator_svc.block_task_with_error(
                    graph_id=self.graph_id,
                    task_id=task_id,
                    error_msg=str(e),
                    traceback_text=tb
                )

    def _get_system_prompt(self) -> str:
        base = (
            "You are an analytical Observer Agent. Read the provided action logs of simulated agents. "
            "Output MUST be a JSON array of objects. Each object should have 'agent_name' and 'insight'.\n\n"
        )
        
        if self.observer_type == ObserverType.PERSONAL:
            return base + (
                "Role: Personal Observer\n"
                "Focus on extracting personal characteristics, preferences, habits, and static personality traits. "
                "Only extract if there is meaningful evidence. Example insight: 'Shows a strong preference for reading scientific articles.'"
            )
        elif self.observer_type == ObserverType.EVENT:
            return base + (
                "Role: Event Observer\n"
                "Focus on summarizing key events, behavioral patterns, and actions taken by agents. "
                "Example insight: 'Frequently retweets breaking news without adding personal commentary.'"
            )
        elif self.observer_type == ObserverType.SOCIAL:
            return base + (
                "Role: Social Observer\n"
                "Focus on extracting relationships between agents, social context, and emotional states towards others. "
                "Example insight: 'Expresses frustration and disagreement consistently when interacting with Bob.'"
            )
        
        return base

