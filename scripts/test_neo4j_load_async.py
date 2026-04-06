"""
Neo4j / API Backend Async Load Test Script
이 스크립트는 AsyncMoriesClient를 활용하여 비동기 환경에서 백엔드 API에 다량의 요청을 동시에 발생시킵니다.
목적: Flask 백엔드의 Neo4j 커넥션 풀링(Size=100)이 정상적으로 동작하며 응답 누수나 병목이 없는지 테스트.
"""

import asyncio
import time
import argparse
from typing import List

from mories import AsyncMoriesClient

async def worker(client: AsyncMoriesClient, worker_id: int, num_requests: int) -> List[float]:
    """단일 워커가 설정된 수만큼 연속해서 검색 API를 호출하며 응답 시간을 측정합니다."""
    latencies = []
    for i in range(num_requests):
        start = time.perf_counter()
        try:
            # search API는 내부적으로 Neo4j와 통신
            res = await client.search(query=f"test query from worker {worker_id} req {i}", limit=1)
            assert res is not None
        except Exception as e:
            print(f"[Worker {worker_id}] Request {i} failed: {e}")
        end = time.perf_counter()
        latencies.append(end - start)
    return latencies

async def run_load_test(concurrency: int, requests_per_worker: int):
    print(f"🚀 Starting Load Test - Concurrency: {concurrency}, Setup calls: {requests_per_worker} per worker")
    print(f"Total Requests: {concurrency * requests_per_worker}")
    
    # httpx.AsyncClient가 자체적으로 커넥션 풀을 관리하므로 클라이언트를 공유
    import os
    token = os.getenv("MORIES_API_KEY", "mories-dev-key")
    async with AsyncMoriesClient(base_url="http://localhost:5001", token=token) as client:
        # 먼저 서버 연결 확인
        try:
            info = await client.info()
            print(f"Server Info: {info}")
        except Exception as e:
            print(f"Failed to connect to server: {e}")
            return

        start_time = time.time()
        
        # 동시에 여러 Task(워커) 생성 및 실행
        tasks = [
            asyncio.create_task(worker(client, i, requests_per_worker))
            for i in range(concurrency)
        ]
        
        # 모든 태스크 완료 대기
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        
    # 결과 취합
    all_latencies = []
    for l in results:
        all_latencies.extend(l)
        
    total_time = end_time - start_time
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
    max_latency = max(all_latencies) if all_latencies else 0
    min_latency = min(all_latencies) if all_latencies else 0
    tps = len(all_latencies) / total_time if total_time > 0 else 0
    
    print("\n--- Load Test Results ---")
    print(f"Total Time: {total_time:.2f} seconds")
    print(f"Successful Requests: {len(all_latencies)}")
    print(f"TPS (Transactions per Second): {tps:.2f}")
    print(f"Average Latency: {avg_latency*1000:.2f} ms")
    print(f"Min Latency: {min_latency*1000:.2f} ms")
    print(f"Max Latency: {max_latency*1000:.2f} ms")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Async Load Testing Tool for Mories API")
    parser.add_argument("-c", "--concurrency", type=int, default=50, help="Number of concurrent workers")
    parser.add_argument("-n", "--requests", type=int, default=10, help="Number of requests per worker")
    
    args = parser.parse_args()
    
    asyncio.run(run_load_test(args.concurrency, args.requests))
