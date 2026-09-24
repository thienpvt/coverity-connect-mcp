"""Run coverity-connect-mcp over HTTP (streamable-http transport) instead of stdio."""
import os
from mcp.server.transport_security import TransportSecuritySettings
from coverity_mcp_server.main import create_server

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8000"))

if __name__ == "__main__":
    mcp = create_server()
    # mcp 1.x: host/port are FastMCP settings, not run() kwargs.
    mcp.settings.host = HOST
    mcp.settings.port = PORT
    # FastMCP() pre-injects a default TransportSecuritySettings (because host
    # defaults to 127.0.0.1), so the FASTMCP_TRANSPORT_SECURITY__* env vars are
    # silently ignored. Ingress/NodePort rewrite Host to the external address,
    # which the DNS-rebinding check would reject with 421. Override it here.
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    )
    mcp.run(transport="streamable-http")
