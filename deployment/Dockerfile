# Multi-stage Dockerfile for Telnyx MCP Server - Production Ready
FROM python:3.12-slim AS base

# Install system dependencies and security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r mcpuser && useradd -r -g mcpuser -d /app -s /bin/bash mcpuser

# Install uv package manager
RUN pip install --no-cache-dir uv==0.4.27

# Production stage
FROM base AS production

# Set working directory and ownership
WORKDIR /app
RUN chown -R mcpuser:mcpuser /app

# Copy OpenAPI specification with proper ownership
COPY --chown=mcpuser:mcpuser telnyx.yml /app/telnyx.yml

# Set production environment variables
ENV NODE_ENV=production
ENV API_NAME=telnyx
ENV API_BASE_URL=https://api.telnyx.com/v2
ENV API_SPEC_PATH=/app/telnyx.yml
ENV LOG_LEVEL=INFO
ENV ENABLE_OPERATION_PROMPTS=true
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Security: Set resource limits
ENV MAX_REQUEST_SIZE=10485760
ENV REQUEST_TIMEOUT=30
ENV MAX_CONCURRENT_REQUESTS=100

# Switch to non-root user
USER mcpuser

# Install the OpenAPI MCP server globally for the user
RUN uv tool install awslabs.openapi-mcp-server@latest

# Create production-ready startup script with proper error handling
RUN echo '#!/bin/bash\n\
set -euo pipefail\n\
\n\
# Validate required environment variables\n\
if [ -z "${TELNYX_API_KEY:-}" ]; then\n\
    echo "ERROR: TELNYX_API_KEY environment variable is required" >&2\n\
    exit 1\n\
fi\n\
\n\
if [[ ! "$TELNYX_API_KEY" =~ ^KEY[a-zA-Z0-9_-]+ ]]; then\n\
    echo "ERROR: TELNYX_API_KEY must start with '\''KEY'\'' and contain valid characters" >&2\n\
    exit 1\n\
fi\n\
\n\
# Validate OpenAPI spec exists\n\
if [ ! -f "$API_SPEC_PATH" ]; then\n\
    echo "ERROR: OpenAPI specification not found at $API_SPEC_PATH" >&2\n\
    exit 1\n\
fi\n\
\n\
# Log startup information (without sensitive data)\n\
echo "Starting Telnyx MCP Server..."\n\
echo "API Base URL: $API_BASE_URL"\n\
echo "Log Level: $LOG_LEVEL"\n\
echo "Port: ${PORT:-8080}"\n\
echo "Operation Prompts: $ENABLE_OPERATION_PROMPTS"\n\
\n\
# Start the MCP server with proper signal handling\n\
exec uvx awslabs.openapi-mcp-server@latest \\\n\
    --host 0.0.0.0 \\\n\
    --port "${PORT:-8080}" \\\n\
    --api-spec-path "$API_SPEC_PATH" \\\n\
    --api-name "$API_NAME" \\\n\
    --api-base-url "$API_BASE_URL" \\\n\
    --log-level "$LOG_LEVEL" \\\n\
    ${ENABLE_OPERATION_PROMPTS:+--enable-operation-prompts}\n\
' > /app/start.sh && chmod +x /app/start.sh

# Create health check script
RUN echo '#!/bin/bash\n\
set -euo pipefail\n\
\n\
# Check if server is responding\n\
if curl -f -s --max-time 5 http://localhost:${PORT:-8080}/health >/dev/null 2>&1; then\n\
    exit 0\n\
else\n\
    echo "Health check failed - server not responding" >&2\n\
    exit 1\n\
fi\n\
' > /app/health-check.sh && chmod +x /app/health-check.sh

# Expose port
EXPOSE 8080

# Add labels for better container management
LABEL org.opencontainers.image.title="Telnyx MCP Server" \
      org.opencontainers.image.description="Production-ready MCP server for Telnyx telecommunications APIs" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="Telnyx" \
      org.opencontainers.image.source="https://github.com/your-org/telnyx-mcp" \
      org.opencontainers.image.documentation="https://developers.telnyx.com" \
      maintainer="support@telnyx.com"

# Production health check with proper configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["/app/health-check.sh"]

# Set proper security context
USER mcpuser

# Use exec form for proper signal handling
CMD ["/app/start.sh"]