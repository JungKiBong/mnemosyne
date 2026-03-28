#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "🟢 Starting Docker Services (Neo4j, etc)..."
docker-compose up -d

echo "🟢 Starting Mories API Server (Port 5001)..."
mkdir -p logs run
nohup .venv/bin/python src/run.py > logs/api.log 2>&1 &
echo $! > run/api.pid

echo "🟢 Starting Mories MCP Server (SSE Sharing mode - Port 3100)..."
nohup .venv/bin/python -m mcp_server.server --transport sse --host 0.0.0.0 --port 3100 > logs/mcp.log 2>&1 &
echo $! > run/mcp.pid

# 获取 IP
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I | awk '{print $1}')

echo "=================================================="
echo "⚡ Mories Hub is now ONLINE!"
echo "📍 Dashboard URL : http://${LOCAL_IP:-localhost}:5001"
echo "🌐 MCP Remote URL: http://${LOCAL_IP:-localhost}:3100/mcp"
echo "=================================================="
echo "Use 'bin/stop_mories.sh' to gracefully stop all services."
