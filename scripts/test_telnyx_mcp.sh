#!/bin/bash

# Test script for the Telnyx MCP Server
# This script validates that the MCP server is working correctly

# Set up environment for testing
export API_NAME="telnyx"
export API_BASE_URL="https://api.telnyx.com/v2"
export API_SPEC_PATH="/Users/timhunter/ronreal/telnyx.yml"
export LOG_LEVEL="INFO"
export ENABLE_OPERATION_PROMPTS="true"

# Test 1: Check if API key is set
echo "=== Test 1: API Key Configuration ==="
if [ -z "$TELNYX_API_KEY" ]; then
    echo "❌ TELNYX_API_KEY is not set in environment"
    echo "   Please set it with: export TELNYX_API_KEY=your_api_key_here"
    exit 1
else
    echo "✅ TELNYX_API_KEY is configured"
    # Mask the key for security
    masked_key="${TELNYX_API_KEY:0:8}...${TELNYX_API_KEY: -4}"
    echo "   Key: $masked_key"
fi

# Test 2: Check if OpenAPI spec file exists
echo ""
echo "=== Test 2: OpenAPI Specification File ==="
if [ ! -f "$API_SPEC_PATH" ]; then
    echo "❌ OpenAPI spec file not found at: $API_SPEC_PATH"
    exit 1
else
    echo "✅ OpenAPI spec file exists"
    file_size=$(ls -lh "$API_SPEC_PATH" | awk '{print $5}')
    echo "   File size: $file_size"
fi

# Test 3: Check if the MCP server can start
echo ""
echo "=== Test 3: MCP Server Startup Test ==="
echo "Starting MCP server with 5 second timeout..."

# Start the server in background and capture PID
timeout 5 uvx awslabs.openapi-mcp-server@latest &
server_pid=$!

# Wait a moment for server to initialize
sleep 2

# Check if server is still running
if ps -p $server_pid > /dev/null 2>&1; then
    echo "✅ MCP server started successfully"
    echo "   Server PID: $server_pid"
    
    # Clean up
    kill $server_pid 2>/dev/null
    wait $server_pid 2>/dev/null
    echo "   Server stopped cleanly"
else
    echo "❌ MCP server failed to start or crashed"
    exit 1
fi

# Test 4: Validate OpenAPI spec format
echo ""
echo "=== Test 4: OpenAPI Spec Validation ==="
if command -v python3 &> /dev/null; then
    python3 -c "
import yaml
import sys
try:
    with open('$API_SPEC_PATH', 'r') as f:
        spec = yaml.safe_load(f)
    
    # Check for required fields
    if 'openapi' not in spec:
        print('❌ Missing openapi version field')
        sys.exit(1)
    
    if 'info' not in spec:
        print('❌ Missing info section')
        sys.exit(1)
        
    if 'paths' not in spec:
        print('❌ Missing paths section')
        sys.exit(1)
    
    print('✅ OpenAPI spec format is valid')
    print(f'   OpenAPI version: {spec[\"openapi\"]}')
    print(f'   API title: {spec[\"info\"].get(\"title\", \"Unknown\")}')
    print(f'   API version: {spec[\"info\"].get(\"version\", \"Unknown\")}')
    print(f'   Number of paths: {len(spec[\"paths\"])}')
    
except yaml.YAMLError as e:
    print(f'❌ YAML parsing error: {e}')
    sys.exit(1)
except Exception as e:
    print(f'❌ Validation error: {e}')
    sys.exit(1)
"
else
    echo "⚠️ Python3 not found, skipping YAML validation"
fi

echo ""
echo "=== All Tests Completed ==="
echo "✅ Telnyx MCP Server is ready for use!"
echo ""
echo "To start the server manually, run:"
echo "  cd /Users/timhunter/ron-ai"
echo "  ./scripts/start_telnyx_mcp.sh"
echo ""
echo "Or to add to Claude Code, use the configuration in:"
echo "  /Users/timhunter/ron-ai/mcp_servers/telnyx-server.json"