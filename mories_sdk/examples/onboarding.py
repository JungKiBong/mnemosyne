"""
Mories Cognitive Engine - Pilot Team Onboarding Example
"""

import os
from mories import MoriesClient, MoriesRetriever

def run_onboarding():
    print("🚀 Welcome to the Mories Pilot Onboarding!")
    print("------------------------------------------")
    
    # 1. Initialize the Mories Client
    # Tokens can be obtained from Keycloak (if connected) or configured API Keys.
    print("[1] Initializing Mories Client...")
    token = os.environ.get("MORIES_API_TOKEN", "demo-token")
    client = MoriesClient(base_url="http://localhost:5001", token=token)
    
    # 2. Check cluster health
    print("\n[2] Checking Mories Cluster Health...")
    try:
        health_info = client.health()
        print(f"    Status: {health_info.get('status')}")
        print(f"    Neo4j Connection: {health_info.get('neo4j', {}).get('status')}")
    except Exception as e:
        print(f"    [!] Warning: Could not connect to the cluster: {e}")
        print("    Ensure the backend is running at http://localhost:5001.")
        return

    # 3. Example: Direct Search
    print("\n[3] Searching the Knowledge Graph directly...")
    query = "Harness and Agents"
    search_results = client.search(query=query, limit=3)
    results = search_results.get("results", [])
    print(f"    Found {len(results)} structured memories for '{query}'.")
    
    # 4. Example: LangChain Integration
    try:
        import langchain_core
        print("\n[4] Initializing LangChain Integration (MoriesRetriever)...")
        retriever = MoriesRetriever(client=client, limit=5)
        
        docs = retriever.invoke(query)
        print(f"    Retrieved {len(docs)} LangChain Documents.")
        if docs:
            print(f"    Example Document snippet: {docs[0].page_content[:50]}...")
            print(f"    Metadata Keys: {list(docs[0].metadata.keys())}")
    except ImportError:
        print("\n[4] LangChain not installed, skipping retriever test.")
        print("    To test the LangChain integration, run: pip install langchain-core")

    print("\n✅ Onboarding complete! The Mories SDK is ready for integration.")

if __name__ == "__main__":
    run_onboarding()
