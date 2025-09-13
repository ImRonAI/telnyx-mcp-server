import { spawn } from 'child_process';
import { createServer } from 'http';

export default function createMcpServer() {
  // This is a wrapper that proxies to the actual OpenAPI MCP server
  const server = createServer(async (req, res) => {
    if (req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        status: 'ok',
        service: 'telnyx-mcp-server',
        version: '1.0.0'
      }));
      return;
    }

    if (req.url === '/mcp' && req.method === 'POST') {
      // Proxy to the actual OpenAPI MCP server
      const mcpProcess = spawn('uvx', ['awslabs.openapi-mcp-server@latest'], {
        env: {
          ...process.env,
          API_NAME: 'telnyx',
          API_BASE_URL: 'https://api.telnyx.com/v2',
          API_SPEC_PATH: './telnyx.yml',
          LOG_LEVEL: 'INFO',
          ENABLE_OPERATION_PROMPTS: 'true',
          TELNYX_API_KEY: process.env.TELNYX_API_KEY || process.env.telnyxApiKey
        }
      });

      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        mcpProcess.stdin.write(body);
        mcpProcess.stdin.end();
      });

      mcpProcess.stdout.on('data', (data) => {
        res.write(data);
      });

      mcpProcess.on('close', () => {
        res.end();
      });

      mcpProcess.on('error', (error) => {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
      });
      return;
    }

    res.writeHead(404);
    res.end('Not Found');
  });

  const port = process.env.PORT || 8080;
  server.listen(port, () => {
    console.log(`Telnyx MCP Server running on port ${port}`);
  });

  return server;
}