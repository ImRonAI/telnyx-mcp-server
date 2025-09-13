# Telnyx MCP Server

A Model Context Protocol (MCP) server for the Telnyx API, providing comprehensive access to Telnyx's telephony, messaging, and communication services.

## Features

- **822 API endpoints** from Telnyx API v2.0.0
- **Comprehensive telephony services**: Call control, conferencing, recording
- **Messaging capabilities**: SMS, MMS, group messaging, short codes
- **Fax functionality**: Send, receive, and manage fax communications
- **Number management**: Phone number search, purchase, porting
- **SIM card management**: IoT and cellular connectivity
- **Infrastructure services**: IP management, storage, authentication

## Quick Start

### Prerequisites
- Python 3.12+
- Telnyx API key

### Local Development
```bash
# Set your API key
export TELNYX_API_KEY="your_api_key_here"

# Start the MCP server
./scripts/start_telnyx_mcp.sh

# Test the server
./scripts/test_telnyx_mcp.sh
```

### Claude Code Integration
Use the configuration in `config/telnyx-server.json` to add this server to Claude Code.

## API Coverage

The server provides MCP tools for:
- **Call Control**: `mcp__telnyx__DialCall`, `mcp__telnyx__AnswerCall`, `mcp__telnyx__BridgeCall`
- **Messaging**: `mcp__telnyx__SendMessage`, `mcp__telnyx__ListMessages`
- **Fax Services**: `mcp__telnyx__SendFax`, `mcp__telnyx__ListFaxes`, `mcp__telnyx__ViewFax`
- **Number Management**: `mcp__telnyx__ListPhoneNumbers`, `mcp__telnyx__RetrievePhoneNumber`
- **SIM Management**: `mcp__telnyx__GetSimCards`, `mcp__telnyx__UpdateSimCard`

## Deployment

### Smithery Platform
Coming soon - Smithery deployment configuration for hosted MCP server.

### Docker
```bash
docker build -t telnyx-mcp-server .
docker run -e TELNYX_API_KEY=your_key -p 8080:8080 telnyx-mcp-server
```

## Environment Variables

- `TELNYX_API_KEY` - Your Telnyx API key (required)
- `API_NAME` - API name (default: "telnyx")
- `API_BASE_URL` - Telnyx API base URL (default: "https://api.telnyx.com/v2")
- `LOG_LEVEL` - Logging level (default: "INFO")

## Support

For issues with the Telnyx API, see [Telnyx Documentation](https://developers.telnyx.com).
For MCP server issues, check the logs or create an issue in this repository.