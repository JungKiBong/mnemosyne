import asyncio
import time
import uuid
import os
from neo4j import AsyncGraphDatabase

async def worker(driver, worker_id: int, num_requests: int):
    # Depending on how the backend is structured, let's just do simple direct Neo4j async queries
    latencies = []
    for i in range(num_requests):
        start = time.perf_counter()
        try:
            async with driver.session() as session:
                await session.run("MATCH (n) RETURN COUNT(n)")
        except Exception as e:
            print(f"[Worker {worker_id}] failure: {e}")
            break
        end = time.perf_counter()
        latencies.append(end - start)
    return latencies

async def main():
    concurrency = 150
    requests_per_worker = 20
    
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "mirofish")
    
    print(f"Connecting to {uri} with max connection pool size = {concurrency}")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd), max_connection_pool_size=concurrency)
    
    start_time = time.time()
    
    tasks = [
        asyncio.create_task(worker(driver, i, requests_per_worker))
        for i in range(concurrency)
    ]
    
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    
    all_latencies = []
    for l in results:
        all_latencies.extend(l)
        
    total_time = end_time - start_time
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
    max_latency = max(all_latencies) if all_latencies else 0
    tps = len(all_latencies) / total_time if total_time > 0 else 0
    
    print(f"\n--- Direct Neo4j Async Pool Load Test Results ---")
    print(f"Total Time: {total_time:.2f} seconds")
    print(f"Successful Requests: {len(all_latencies)}")
    print(f"TPS: {tps:.2f}")
    print(f"Average Latency: {avg_latency*1000:.2f} ms")
    print(f"Max Latency: {max_latency*1000:.2f} ms")
    
    await driver.close()

if __name__ == "__main__":
    asyncio.run(main())
