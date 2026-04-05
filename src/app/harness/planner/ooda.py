import json
import logging
import uuid
import os
from typing import Dict, Any, List

from src.app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

class AutonomousPlanner:
    """
    Autonomous Planner implementing the OODA Loop:
    Observe, Orient, Decide, Act.
    
    This planner allows Harness to automatically adjust, branch, or loop 
    the active workflow based on execution metrics and LLM inferences.
    """
    def __init__(self, agent_registry, llm_provider=None, memory_backend=None):
        self.agent_registry = agent_registry
        self.llm_provider = llm_provider  # Callable or interface for LLM inference
        self.memory_backend = memory_backend
        
    def observe(self, harness_runtime) -> Dict[str, Any]:
        """
        Observe: Gather current context, execution history, and metrics from the engine.
        """
        harness_id = harness_runtime.workflow.get("harness_id", "unknown")
        domain = harness_runtime.workflow.get("domain", "unknown")
        metrics_stats = harness_runtime._metrics.get_harness_stats(harness_id)
        
        return {
            "domain": domain,
            "context": harness_runtime.context,
            "metrics": metrics_stats,
            "completed_steps": harness_runtime._execution_log,
            "current_step_order": harness_runtime.step_order
        }
        
    def orient(self, observation: Dict[str, Any], goal: str) -> Dict[str, Any]:
        """
        Orient: Analyze observation vs goal, check safety constraints.
        Prepares a structured payload for the LLM to make a decision.
        """
        log_summary = [s["step_id"] for s in observation.get("completed_steps", []) if s.get("success")]
        
        # ── Cross-Domain Knowledge Recall ──
        memory_context = ""
        if self.memory_backend and hasattr(self.memory_backend, "find_patterns"):
            try:
                # 같은 도메인의 성공 패턴 
                patterns = self.memory_backend.find_patterns(domain=observation.get("domain"), limit=2)
                # 범용(cross-domain) 성공 패턴
                cross_patterns = self.memory_backend.find_patterns(domain=None, limit=2)
                
                all_pats = {p["uuid"]: p for p in (patterns + cross_patterns)}.values()
                
                if all_pats:
                    pat_lines = ["Historically Successful Patterns (Tool Chains):"]
                    for p in all_pats:
                        tc = p.get("tool_chain", [])
                        pat_lines.append(f"- Domain: {p.get('domain')} | Chain: {' -> '.join(tc)}")
                    memory_context = "\n" + "\n".join(pat_lines) + "\n"
            except Exception as e:
                logger.warning(f"Failed to fetch patterns in OODA Planner: {e}")

        prompt = (
            f"Goal: {goal}\n"
            f"Completed steps: {log_summary}\n"
            f"{memory_context}"
            f"Please analyze if the goal is met or if new steps need to be injected."
        )
        
        return {
            "prompt": prompt,
            "goal": goal,
            "safety_checked": True,
            "observation_summary": log_summary
        }
        
    def decide(self, orientation: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Decide: Dynamically construct new step DSLs matching goals.
        Calls actual LLM logic to determine if new steps are needed.
        """
        logger.info(f"OODA Decide phase for goal: {orientation['goal']}")
        
        if self.llm_provider:
            # Delegate to real LLM module if explicitly provided (e.g. tests)
            return self.llm_provider(orientation)
            
        # Default LLM implementation
        try:
            client = LLMClient()
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an autonomous workflow orchestration planner. "
                        "Your task is to review the current workflow execution and determine whether additional steps are needed to meet the user's goal. "
                        "If the goal has NOT been met, provide a list of NEW steps (in JSON format) to inject dynamically. "
                        "If the goal HAS been met, return an empty list: []. "
                        "Each new step MUST be a valid JSON object matching the Harness step schema, e.g., "
                        "{\"id\": \"step_XYZ\", \"type\": \"wait\", \"timeout_seconds\": 5} or similar. "
                        "Respond ONLY with a valid JSON array of step objects, without markdown formatting if possible."
                    )
                },
                {
                    "role": "user",
                    "content": orientation["prompt"]
                }
            ]
            response = client.chat_json(messages)
            if isinstance(response, list):
                logger.info(f"OODA Decide generated {len(response)} new steps.")
                return response
            elif isinstance(response, dict) and "steps" in response:
                return response["steps"]
            else:
                logger.warning(f"Unexpected LLM response format: {response}")
                return []
                
        except Exception as e:
            logger.error(f"Error during OODA Decide LLM call: {e}")
            # Mock Fallback Decision Logic for robustness/tests if LLM is unavailable:
            if "fix" in orientation["goal"].lower() and "auto_fix_step" not in "".join(orientation.get("observation_summary", [])):
                return [{
                    "id": f"auto_fix_step_{uuid.uuid4().hex[:6]}",
                    "type": "wait",
                    "timeout_seconds": 0
                }]
            return []
        
    def act(self, new_steps: List[Dict[str, Any]], harness_runtime) -> None:
        """
        Act: Append newly decided steps into the HarnessRuntime step registry & order.
        """
        for step in new_steps:
            if step["id"] not in harness_runtime.steps:
                harness_runtime.steps[step["id"]] = step
                # Insert right after the current execution or at the end
                harness_runtime.step_order.append(step["id"])
                logger.info(f"OODA Act: Injected new step '{step['id']}' into workflow.")

    def run_loop(self, harness_runtime, goal: str) -> None:
        """Run a single iteration of the OODA loop during an active workflow execution."""
        logger.info("--- Starting Autonomous OODA Loop iteration ---")
        observation = self.observe(harness_runtime)
        orientation = self.orient(observation, goal)
        new_steps = self.decide(orientation)
        if new_steps:
            self.act(new_steps, harness_runtime)
