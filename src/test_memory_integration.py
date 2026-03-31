import os
import sys
import json
import asyncio
from datetime import datetime

# Setup path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()

from app.storage.neo4j_storage import Neo4jStorage
from app.storage.hybrid_storage import HybridStorage
from app.services.search_agent import SearchAgent
from app.utils.llm_client import LLMClient

def test_integration():
    print("Testing Mories Cognitive Memory Integration...")
    try:
        neo4j = Neo4jStorage()
        print("[OK] Neo4jStorage initialized")
        
        hybrid = HybridStorage(neo4j)
        print("[OK] HybridStorage initialized")
        print("  Health:", hybrid.health_check())
        
        graph_id = "test_graph_123"
        print(f"\nInitializing SearchAgent for graph {graph_id}...")
        search = SearchAgent(graph_id=graph_id, storage=hybrid)
        
        agent_name = "Alice"
        query = "What did Bob say about the project?"
        print(f"Retrieving memory for {agent_name} with query: '{query}'")
        res = search.retrieve(agent_name=agent_name, query=query)
        
        print("\n[OK] SearchAgent context retrieval succeeded:")
        print(f"  Facts: {len(res.facts)}")
        print(f"  Contexts: {len(res.context)}")
        print(f"  Timeline: {len(res.timeline)}")
        
        # Test prompt injection format
        print("\nPrompt Injection Format:")
        print(res.to_prompt_injection())
        
        search.shutdown()
        hybrid.close()
        print("\n[SUCCESS] Memory Engine & Search Integration works.")
    except Exception as e:
        print(f"[ERROR] Testing failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_integration()
