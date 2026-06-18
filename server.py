#!/usr/bin/env python3
"""
Gecombineerde MCP HTTP-server voor Railway deployment.
Elke site heeft een eigen endpoint:
  /shopify/mcp  → Shopify winkel tools
  /kas/mcp      → Restaurant de Kas tools
  /kitlv/mcp    → KITLV tools

Start lokaal met: python server.py
Railway gebruikt de PORT omgevingsvariabele automatisch.
"""

import os
import shopify_mcp
import kas_mcp
import kitlv_mcp

PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0"

# Haal de Starlette ASGI-apps op uit elke MCP-server
shopify_asgi = shopify_mcp.mcp.streamable_http_app()
kas_asgi = kas_mcp.mcp.streamable_http_app()
kitlv_asgi = kitlv_mcp.mcp.streamable_http_app()

from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.responses import JSONResponse
from starlette.requests import Request


async def index(request: Request) -> JSONResponse:
    return JSONResponse({
        "service": "AI-readable site layer",
        "endpoints": {
            "/shopify/mcp": "Shopify winkel — producten, voorraad, prijzen",
            "/kas/mcp": "Restaurant de Kas — menu, openingstijden, reservering",
            "/kitlv/mcp": "KITLV — evenementen, onderzoekers, projecten, nieuws",
        }
    })


app = Starlette(routes=[
    Mount("/shopify", app=shopify_asgi),
    Mount("/kas", app=kas_asgi),
    Mount("/kitlv", app=kitlv_asgi),
])

# Voeg index-route toe
from starlette.routing import Route
app.routes.insert(0, Route("/", index))


if __name__ == "__main__":
    import uvicorn
    print(f"Server draait op http://{HOST}:{PORT}")
    print(f"  Shopify: http://localhost:{PORT}/shopify/mcp")
    print(f"  Kas:     http://localhost:{PORT}/kas/mcp")
    print(f"  KITLV:   http://localhost:{PORT}/kitlv/mcp")
    uvicorn.run(app, host=HOST, port=PORT)
