#!/usr/bin/env python3
"""
AI Site Layer — MCP server die automatisch alle clients laadt vanuit de clients/ map.

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

PORT = int(os.environ.get("PORT", 8000))
mcp = FastMCP("ai-site-layer", host="0.0.0.0", port=PORT)

CLIENTS_DIR = Path(__file__).parent / "clients"

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

        # Laad de scraper module dynamisch
        spec = importlib.util.spec_from_file_location(f"clients.{slug}", scraper_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"clients.{slug}"] = module
        spec.loader.exec_module(module)

        # Registreer alle publieke functies als MCP tools met prefix
        registered = []
        for func_name in dir(module):
            if func_name.startswith("_"):
                continue
            func = getattr(module, func_name)
            if not callable(func) or not getattr(func, "__doc__", None):
                continue
            # Sla imports en klassen over
            if not hasattr(func, "__module__") or func.__module__ != f"clients.{slug}":
                continue

            tool_name = f"{slug}_{func_name}"
            mcp.tool(name=tool_name)(func)
            registered.append(tool_name)

        loaded.append({"client": config["name"], "tools": registered})

    return loaded

if __name__ == "__main__":
    clients = load_clients()
    for c in clients:
        print(f"✓ {c['client']}: {', '.join(c['tools'])}")
    print(f"\nServer draait op http://0.0.0.0:{PORT}/mcp")
    mcp.run(transport="streamable-http")
