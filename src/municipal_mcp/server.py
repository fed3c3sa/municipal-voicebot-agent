"""FastMCP server entry point.

Builds the server, registers the tool modules, and serves them over Streamable
HTTP at the configured path (default /mcp). When MCP_AUTH_TOKEN is set, a small
ASGI guard requires `Authorization: Bearer <token>` on every request; when it is
empty, the server is open (fine for a local demo).

Run with:  python -m municipal_mcp.server
"""

from __future__ import annotations

import uvicorn
from fastmcp import FastMCP

from .config import Settings, get_settings
from .tools import appointments, documentation


def build_server() -> FastMCP:
    """Create the FastMCP server with all tools registered."""
    mcp = FastMCP("Comune di Codroipo")
    documentation.register(mcp)
    appointments.register(mcp)
    return mcp


class BearerAuthMiddleware:
    """Minimal ASGI middleware that enforces a static bearer token on HTTP requests."""

    def __init__(self, app, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if headers.get(b"authorization") != self._expected:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await self._app(scope, receive, send)


def build_app(settings: Settings | None = None):
    """Build the ASGI app, optionally wrapped with bearer-token auth."""
    settings = settings or get_settings()
    mcp = build_server()
    app = mcp.http_app(path=settings.mcp_path)
    token = settings.mcp_auth_token.strip()
    if token:
        return BearerAuthMiddleware(app, token)
    return app


def main() -> None:
    settings = get_settings()
    app = build_app(settings)
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
