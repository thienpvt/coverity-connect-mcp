"""Run coverity-connect-mcp over HTTP (streamable-http transport) instead of stdio."""
import os
from coverity_mcp_server.main import create_server

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8000"))

if __name__ == "__main__":
    create_server().run(transport="streamable-http", host=HOST, port=PORT)
