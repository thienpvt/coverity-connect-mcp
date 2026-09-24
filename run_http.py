"""Run coverity-connect-mcp over HTTP (streamable-http transport) instead of stdio."""
import os
from coverity_mcp_server.main import create_server

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8000"))

if __name__ == "__main__":
    mcp = create_server()
    # mcp 1.x: host/port are FastMCP settings, not run() kwargs.
    mcp.settings.host = HOST
    mcp.settings.port = PORT
    mcp.run(transport="streamable-http")
