# Dockerfile for Telnyx MCP Server
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN pip install uv

# Set environment variables
ENV API_NAME=telnyx
ENV API_BASE_URL=https://api.telnyx.com/v2
ENV LOG_LEVEL=INFO
ENV ENABLE_OPERATION_PROMPTS=true
ENV PORT=8080

# Copy the OpenAPI specification
COPY telnyx.yml /app/telnyx.yml
ENV API_SPEC_PATH=/app/telnyx.yml

# Install the OpenAPI MCP server
RUN uv tool install awslabs.openapi-mcp-server@latest

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Start the MCP server
CMD ["uvx", "awslabs.openapi-mcp-server@latest"]