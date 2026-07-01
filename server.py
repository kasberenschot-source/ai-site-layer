#!/usr/bin/env python3
"""
AI Site Layer — MCP server + HTTP API voor de SiteLayer landingspagina.

Om een nieuwe klant toe te voegen:
  1. Maak een map aan: clients/<slug>/
  2. Voeg config.json toe met name, slug, url, type, description
  3. Voeg scraper.py toe met de tool-functies
  4. Deploy — de server laadt hem automatisch
"""

import os
import sys
import json
import importlib.util
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.middleware.cors import CORSMiddleware

PORT = int(os.environ.get("PORT", 8000))
mcp = FastMCP("ai-site-layer", host="0.0.0.0", port=PORT)

CLIENTS_DIR = Path(__file__).parent / "clients"
_client_modules = {}
_client_configs = {}


def load_clients():
    loaded = []
    for client_dir in sorted(CLIENTS_DIR.iterdir()):
        if not client_dir.is_dir():
            continue
        config_path = client_dir / "config.json"
        scraper_path = client_dir / "scraper.py"
        if not config_path.exists() or not scraper_path.exists():
            continue

        with open(config_path) as f:
            config = json.load(f)
        slug = config["slug"]

        spec = importlib.util.spec_from_file_location(f"clients.{slug}", scraper_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"clients.{slug}"] = module
        spec.loader.exec_module(module)

        _client_modules[slug] = module
        _client_configs[slug] = config

        registered = []
        for func_name in dir(module):
            if func_name.startswith("_"):
                continue
            func = getattr(module, func_name)
            if not callable(func) or not getattr(func, "__doc__", None):
                continue
            if not hasattr(func, "__module__") or func.__module__ != f"clients.{slug}":
                continue
            mcp.tool(name=f"{slug}_{func_name}")(func)
            registered.append(func_name)

        loaded.append({"client": config["name"], "slug": slug, "tools": registered})
    return loaded


async def ask_endpoint(request: Request):
    """POST /ask — directe HTTP API voor de SiteLayer demo."""
    try:
        body = await request.json()
        slug = body.get("site", "")
        question = body.get("question", "").lower()

        if slug not in _client_modules:
            return JSONResponse({"error": f"Site '{slug}' niet gevonden."}, status_code=404)

        module = _client_modules[slug]
        funcs = {
            name: getattr(module, name)
            for name in dir(module)
            if not name.startswith("_")
            and callable(getattr(module, name))
            and getattr(getattr(module, name), "__doc__", None)
            and getattr(getattr(module, name), "__module__", None) == f"clients.{slug}"
        }

        # Kies beste functie op basis van keyword overlap
        scores = {}
        for name, func in funcs.items():
            doc = (func.__doc__ or "").lower()
            score = sum(1 for w in question.split() if w in doc or w in name)
            scores[name] = score

        best = max(scores, key=scores.get) if scores else list(funcs.keys())[0]
        result = funcs[best]()

        return JSONResponse({
            "site": _client_configs[slug]["name"],
            "tool": f"{slug}_{best}",
            "result": result
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def clients_endpoint(request: Request):
    """GET /clients — lijst van beschikbare sites."""
    return JSONResponse([
        {"slug": slug, "name": config["name"], "url": config["url"], "description": config.get("description", "")}
        for slug, config in _client_configs.items()
    ])


if __name__ == "__main__":
    clients = load_clients()
    for c in clients:
        print(f"✓ {c['client']}: {', '.join(c['tools'])}")
    print(f"\nServer draait op http://0.0.0.0:{PORT}/mcp")

    mcp_app = mcp.streamable_http_app()

    app = Starlette(routes=[
        Route("/ask", ask_endpoint, methods=["POST"]),
        Route("/clients", clients_endpoint, methods=["GET"]),
        Mount("/", app=mcp_app),
    ])

    app = CORSMiddleware(app, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    uvicorn.run(app, host="0.0.0.0", port=PORT)
