#!/bin/bash
set -e

BASE_URL="http://100.4.213.68:3344"
SESSION_KEY="1234321"

echo "=== Testing MCP Build Service ==="
echo "Base URL: $BASE_URL"
echo "Session Key: $SESSION_KEY"
echo

# Step 1: Connect to SSE endpoint and get session ID
echo "Step 1: Connecting to SSE endpoint..."
SSE_RESPONSE=$(curl -s --max-time 3 "${BASE_URL}/sse?key=${SESSION_KEY}" 2>&1 | head -n 10)
echo "$SSE_RESPONSE"
echo

SESSION_ID=$(echo "$SSE_RESPONSE" | grep "data:" | cut -d'=' -f2)
if [ -z "$SESSION_ID" ]; then
    echo "ERROR: Failed to get session ID"
    exit 1
fi

echo "Got session ID: $SESSION_ID"
echo

MESSAGES_URL="${BASE_URL}/messages?session_id=${SESSION_ID}"

# Step 2: Initialize
echo "Step 2: Initializing session..."
INIT_RESPONSE=$(curl -s -X POST "$MESSAGES_URL" \
    -H "Authorization: Bearer ${SESSION_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": true},
                "sampling": {}
            },
            "clientInfo": {
                "name": "mcp-test-bash-client",
                "version": "1.0.0"
            }
        }
    }')

echo "$INIT_RESPONSE" | jq '.'
echo

# Step 3: Send initialized notification
echo "Step 3: Sending initialized notification..."
curl -s -X POST "$MESSAGES_URL" \
    -H "Authorization: Bearer ${SESSION_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    }' > /dev/null
echo "Notification sent"
echo

# Step 4: List tools
echo "Step 4: Listing available tools..."
TOOLS_RESPONSE=$(curl -s -X POST "$MESSAGES_URL" \
    -H "Authorization: Bearer ${SESSION_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }')

echo "$TOOLS_RESPONSE" | jq '.result.tools[] | {name: .name, description: .description}'
echo

# Step 5: Call list tool
echo "Step 5: Calling 'list' tool to list repositories..."
LIST_RESPONSE=$(curl -s -X POST "$MESSAGES_URL" \
    -H "Authorization: Bearer ${SESSION_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "list",
            "arguments": {}
        }
    }')

echo "$LIST_RESPONSE" | jq '.result.content[] | select(.type == "text") | .text' -r
echo

# Step 6: Call env tool
echo "Step 6: Calling 'env' tool to check environment..."
ENV_RESPONSE=$(curl -s -X POST "$MESSAGES_URL" \
    -H "Authorization: Bearer ${SESSION_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "env",
            "arguments": {}
        }
    }')

echo "$ENV_RESPONSE" | jq '.result.content[] | select(.type == "text") | .text' -r
echo

# Step 7: Test git status
echo "Step 7: Testing 'git' tool with status command..."
GIT_RESPONSE=$(curl -s -X POST "$MESSAGES_URL" \
    -H "Authorization: Bearer ${SESSION_KEY}" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "git",
            "arguments": {
                "args": "status"
            }
        }
    }')

echo "$GIT_RESPONSE" | jq '.result.content[] | select(.type == "text") | .text' -r
echo

echo "=== All tests completed successfully! ==="
