import logging
import time
from src.app.services.orchestrator_service import OrchestratorService
from src.app.services.observer_agent import ObserverAgent, ObserverType
from src.app.storage.hybrid_storage import HybridStorage
from src.app.services.graph_memory_updater import AgentActivity

# Very dummy implementation for testing
class DummyLLM:
    def generate(self, prompt, system_prompt, json_mode=False):
        import json
        return json.dumps([{"agent_name": "TestBot", "insight": "Likes testing the blackboard.", "confidence": 0.99}])

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test")
    
    # 1. Initialize DB and Orchestration
    orch_svc = OrchestratorService()
    graph_id = "test_simulation_graph"
    session_id = orch_svc.create_session(graph_id, "Test Simulation Session", "Testing the new ObserverAgent integration")
    logger.info(f"Created Session: {session_id}")
    
    # 2. Setup ObserverAgent
    dummy_storage = HybridStorage("test", graph_id)
    llm = DummyLLM()
    observer = ObserverAgent(
        observer_type=ObserverType.PERSONAL,
        llm_client=llm,
        storage=dummy_storage,
        graph_id=graph_id,
        batch_size=1
    )
    
    # Manually assign the session_id that would normally be assigned by ObserverOrchestrator
    observer.session_id = session_id
    
    # 3. Start Observer
    observer.start()
    
    # 4. Feed a dummy activity
    act = AgentActivity(
        agent_id="TestBot",
        action_type="SPEAK",
        target="Alice",
        content="Hello, I am testing the Neo4j blackboard.",
        location="Lab"
    )
    observer.observe(act)
    
    # 5. Wait for processing
    time.sleep(3)
    
    # 6. Stop Observer
    observer.stop()
    
    # 7. Check Blackboard tasks
    tasks = orch_svc.get_pending_tasks(graph_id)
    logger.info(f"Pending Tasks: {len(tasks)}")
    
    # Instead of fetching everything (which might need new endpoints), let's just complete the session
    orch_svc.complete_session(graph_id, session_id)
    logger.info("Session completed")

if __name__ == "__main__":
    main()
