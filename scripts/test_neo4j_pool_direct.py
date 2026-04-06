"""
Neo4j Direct Connection Pool Load Test
Flask 백엔드 API를 우회하여 Neo4j 스토리지 레이어에 직접 부하를 가하는 스크립트입니다.
"""

import sys
import os
import time
import concurrent.futures

# Set up path so we can import app modules directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from app.storage.neo4j_storage import Neo4jStorage

# Override DB settings if running in local docker environment
os.environ['NEO4J_URI'] = "bolt://localhost:7687"
os.environ['NEO4J_USER'] = "neo4j"
os.environ['NEO4J_PASSWORD'] = "mirofish"

def initialize_storage():
    return Neo4jStorage(
        uri=os.environ['NEO4J_URI'],
        user=os.environ['NEO4J_USER'],
        password=os.environ['NEO4J_PASSWORD']
    )

def worker(storage: Neo4jStorage, worker_id: int, num_requests: int):
    """단일 워커가 설정된 수만큼 연속해서 Cypher 쿼리를 실행합니다."""
    latencies = []
    
    # 더미 데이터 생성 또는 단순 읽기 쿼리를 수행하여 풀 점유
    cypher_query = "RETURN $worker_id AS w, $req_id AS r"
    
    for i in range(num_requests):
        start = time.perf_counter()
        try:
            with storage._driver.session() as session:
                res = session.run(cypher_query, worker_id=worker_id, req_id=i)
                list(res)  # fetch
        except Exception as e:
            print(f"[Worker {worker_id}] Req {i} Failed: {e}")
            break
        end = time.perf_counter()
        latencies.append(end - start)
        
    return latencies

def run_direct_load_test(concurrency: int = 150, requests_per_worker: int = 10):
    print(f"🚀 Starting Neo4j Direct Load Test - Concurrency: {concurrency}, Requests/Worker: {requests_per_worker}")
    
    storage = initialize_storage()
    if not storage._driver:
         print("Failed to initialize Neo4j driver.")
         return
         
    start_time = time.time()
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker, storage, i, requests_per_worker) for i in range(concurrency)]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                print(f"Task failed: {e}")
                
    end_time = time.time()
    
    all_latencies = []
    for l in results:
         all_latencies.extend(l)
         
    total_time = end_time - start_time
    total_requests = len(all_latencies)
    tps = total_requests / total_time if total_time > 0 else 0
    avg_lat = (sum(all_latencies) / total_requests) if total_requests else 0
    
    print("\n--- Neo4j Pool Direct Test Results ---")
    print(f"Successful Requests: {total_requests}")
    print(f"Total Time: {total_time:.2f} s")
    print(f"TPS: {tps:.2f} queries/sec")
    print(f"Average Latency: {avg_lat*1000:.2f} ms")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--concurrency", type=int, default=150, help="Number of concurrent connections")
    parser.add_argument("-n", "--requests", type=int, default=10, help="Requests per thread")
    args = parser.parse_args()
    
    run_direct_load_test(args.concurrency, args.requests)
