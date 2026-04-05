"""
HITL (Human-In-The-Loop) Gate Executor.

Suspends workflow execution until human input/approval is provided.
"""
import time
from typing import Any, Dict

from . import BaseExecutor, ExecutorResult

class HitlGateExecutor(BaseExecutor):
    """
    Executes a HITL gate.

    If the current context already contains a non-null answer for this step's ID 
    (meaning the human has responded), the gate passes and outputs the answer.
    Otherwise, it marks the execution as suspended, prompting the human.
    """

    def execute(self, step_config: Dict[str, Any], context: Dict[str, Any]) -> ExecutorResult:
        start_time = time.monotonic()
        step_id = step_config.get("id", "hitl_gate")
        
        # Check if the human has already provided an answer in the context
        # e.g., context["hitl_responses"]["human_approval"] = {"action": "approve", "feedback": "Looks good"}
        hitl_responses = context.get("hitl_responses", {})
        answer = hitl_responses.get(step_id)

        if answer is not None:
            # Human has answered, gate is passed.
            feedback = answer.get("feedback")
            if feedback:
                self._record_human_feedback(feedback, context)
            
            return ExecutorResult(
                success=True,
                status="completed",
                output=answer,
                elapsed_ms=int((time.monotonic() - start_time) * 1000),
                metadata={"hitl_answered": True, "feedback_recorded": bool(feedback)}
            )

        # Human has not answered yet. Suspend and request input.
        prompt = step_config.get("prompt", "Human approval required.")
        allowed_actions = step_config.get("allowed_actions", ["approve", "reject"])
        
        return ExecutorResult(
            success=True,  # Technically it's not a failure, just a pause
            status="suspended",
            output={
                "prompt": prompt,
                "allowed_actions": allowed_actions,
            },
            elapsed_ms=int((time.monotonic() - start_time) * 1000),
            metadata={"hitl_answered": False}
        )

    def _record_human_feedback(self, feedback: str, context: Dict[str, Any]) -> None:
        """Record human feedback as a procedural permanent memory into Mories Graph."""
        try:
            from src.app.storage.permanent_memory import PermanentMemoryManager
            mgr = PermanentMemoryManager()
            
            domain_scope = context.get("_meta", {}).get("domain", "global")
            
            mgr.create_imprint(
                content=feedback,
                scope=domain_scope,
                tags=["human_feedback", "hitl_gate"],
                created_by="human_operator",
                reason="HITL workflow feedback",
                memory_category="procedural"
            )
            mgr.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to record HITL human feedback (Neo4j may be offline): {e}")
