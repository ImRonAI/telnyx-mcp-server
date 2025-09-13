#!/bin/bash

# Telnyx MCP Server Startup Script for Ron AI
# This script starts the Telnyx OpenAPI MCP server with proper configuration

# Set default environment variables if not provided
export API_NAME="${API_NAME:-telnyx}"
export API_BASE_URL="${API_BASE_URL:-https://api.telnyx.com/v2}"
export API_SPEC_PATH="${API_SPEC_PATH:-/Users/timhunter/ronreal/telnyx.yml}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export ENABLE_OPERATION_PROMPTS="${ENABLE_OPERATION_PROMPTS:-true}"

# Check if TELNYX_API_KEY is set
if [ -z "$TELNYX_API_KEY" ]; then
    echo "Error: TELNYX_API_KEY environment variable is not set"
    echo "Please set your Telnyx API key: export TELNYX_API_KEY=your_api_key_here"
    exit 1
fi

echo "Starting Telnyx MCP Server..."
echo "API Name: $API_NAME"
echo "API Base URL: $API_BASE_URL"
echo "API Spec Path: $API_SPEC_PATH"
echo "Log Level: $LOG_LEVEL"
echo ""

# Start the MCP server with the OpenAPI converter
uvx awslabs.openapi-mcp-server@latest