FROM python:3.12-slim

WORKDIR /app

# Install the MCP server from the repo root. Pin mcp<2: the app uses the
# v1 FastMCP API, broken by the 2.x FastMCP->MCPServer rename.
COPY . .
RUN pip install --no-cache-dir . "mcp<2"

EXPOSE 8000

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    FASTMCP_TRANSPORT_SECURITY__ENABLE_DNS_REBINDING_PROTECTION=false

CMD ["python", "/app/run_http.py"]
