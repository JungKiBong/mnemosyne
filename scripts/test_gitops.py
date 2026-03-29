import requests
from neo4j import GraphDatabase
import uuid
import time
import json

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "mirofish"
API_BASE = "http://localhost:5001/api/gateway"

def run_tests():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    print("--- SCENARIO 1: Create Staging Entities ---")
    node_id_1 = str(uuid.uuid4())
    node_id_2 = str(uuid.uuid4())
    with driver.session() as session:
        session.run(
            "CREATE (s1:StagingEntity {id: $id1, name: 'Staging Concept A', pr_ref: 'PR-42'}), "
            "(s2:StagingEntity {id: $id2, name: 'Staging Concept B', pr_ref: 'PR-42'})",
            id1=node_id_1, id2=node_id_2
        )
    print(f"Created StagingEntities: {node_id_1}, {node_id_2} (PR-42)")
    
    print("\n--- SCENARIO 2: GitOps Webhook Promotion ---")
    payload = {
        "action": "closed",
        "pull_request": {
            "merged": True,
            "number": 42,
            "merged_by": {"login": "QA_Bot"}
        }
    }
    resp = requests.post(f"{API_BASE}/github-merge", json=payload)
    print(f"Webhook Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    print("\n--- SCENARIO 3: Create More Staging For Fallback ---")
    node_id_fallback = str(uuid.uuid4())
    with driver.session() as session:
        session.run(
            "CREATE (s:StagingEntity {id: $id, name: 'Emergency Fallback Update'})",
            id=node_id_fallback
        )
    print(f"Created Fallback StagingEntity: {node_id_fallback}")
    
    print("\n--- SCENARIO 4: Manual Fallback Promotion ---")
    # For this to work, we need an admin key. I'll just check if it returns 401 or 403, and then we skip testing the full body
    # if we don't know an existing API key. Or better, we can inject a test key into the DB.
    with driver.session() as session:
        session.run("MERGE (k:ApiKey {key_hash: 'test-admin-key'}) SET k.active=true, k.roles=['admin'], k.owner_id='system'")
        
    headers = {"X-API-Key": "test-admin-key"}
    fb_payload = {"node_ids": [node_id_fallback]}
    
    resp_fallback = requests.post(f"{API_BASE}/staging/approve", json=fb_payload, headers=headers)
    print(f"Fallback Status: {resp_fallback.status_code}")
    print(f"Response: {resp_fallback.json()}")
    
    print("\n--- SCENARIO 5: Verify Audit Trail (MemoryRevision) ---")
    with driver.session() as session:
        res = session.run("MATCH (n:MemoryRevision) WHERE n.entity_id IN [$id1, $id2, $idf] RETURN n", 
                          id1=node_id_1, id2=node_id_2, idf=node_id_fallback).data()
    for record in res:
        print("Found Revision:", record['n'])
        
    driver.close()

if __name__ == "__main__":
    run_tests()
