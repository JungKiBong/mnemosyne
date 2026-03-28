#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Mories MCP Server — Setup & Verification Script
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MCP_SERVER="$SCRIPT_DIR/mories_mcp.py"
MORIES_URL="${MORIES_URL:-http://192.168.35.86:5001}"

echo "🧠 Mories MCP Server — Setup & Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Check Python
echo ""
echo "1️⃣  Checking Python..."
python3 --version || { echo "❌ Python3 not found"; exit 1; }

# 2. Check dependencies
echo ""
echo "2️⃣  Checking dependencies..."
python3 -c "import mcp; print(f'  ✅ mcp {mcp.__version__}')" 2>/dev/null || {
    echo "  📦 Installing mcp..."
    pip3 install --break-system-packages mcp httpx 2>/dev/null || pip3 install mcp httpx
}
python3 -c "import httpx; print(f'  ✅ httpx {httpx.__version__}')" 2>/dev/null || {
    echo "  📦 Installing httpx..."
    pip3 install --break-system-packages httpx 2>/dev/null || pip3 install httpx
}

# 3. Check Mories API reachability
echo ""
echo "3️⃣  Checking Mories API ($MORIES_URL)..."
HEALTH=$(curl -s -m 5 "$MORIES_URL/api/health" 2>/dev/null || echo '{"error":"unreachable"}')
echo "  Response: $HEALTH"
if echo "$HEALTH" | grep -q "error"; then
    echo "  ⚠️  Mories API not reachable. Start the server first."
    echo "     cd /path/to/mirofish-supermemory && ./scripts/start.sh"
else
    echo "  ✅ Mories API is running"
fi

# 4. Verify MCP server syntax
echo ""
echo "4️⃣  Validating MCP server..."
python3 -c "
import ast
with open('$MCP_SERVER') as f:
    ast.parse(f.read())
print('  ✅ MCP server syntax is valid')
"

# 5. Show configuration guide
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup complete! Add to your MCP client config:"
echo ""
echo "📁 Antigravity (settings.json):"
echo "   ~/.gemini/settings.json → mcpServers.mories"
echo ""
echo "📁 Claude Desktop (claude_desktop_config.json):"
echo "   ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "📋 Configuration snippet:"
echo '{'
echo '  "mcpServers": {'
echo '    "mories": {'
echo '      "command": "python3",'
echo "      \"args\": [\"$MCP_SERVER\"],"
echo '      "env": {'
echo "        \"MORIES_URL\": \"$MORIES_URL\","
echo '        "MORIES_AGENT_ID": "your-agent-name"'
echo '      }'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
