#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "🔴 Stopping Mories API Server..."
if [ -f run/api.pid ]; then
  kill $(cat run/api.pid) 2>/dev/null
  rm run/api.pid 2>/dev/null
  echo "Stopped via PID file."
fi
# Ultimate fallback: Kill anything taking port 5001
lsof -ti :5001 | xargs kill -9 2>/dev/null
echo "Port 5001 cleared."

echo "🔴 Stopping Mories MCP Server..."
if [ -f run/mcp.pid ]; then
  kill $(cat run/mcp.pid) 2>/dev/null
  rm run/mcp.pid 2>/dev/null
  echo "Stopped via PID file."
fi
# Ultimate fallback: Kill anything taking port 3100
lsof -ti :3100 | xargs kill -9 2>/dev/null
echo "Port 3100 cleared."

# 주석 해제 시 도커 컴포즈(디비)도 같이 끔
# echo "🔴 Stopping Docker (Neo4j)..."
# docker-compose stop

echo "=================================================="
echo "💤 All Mories services successfully stopped and ports freed."
echo "=================================================="
