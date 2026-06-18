#!/usr/bin/env python3
"""
Gecombineerde MCP HTTP-server voor Railway deployment.
Alle tools van de drie sites in één server op /mcp.

Toolnamen zijn geprefixed om ze te onderscheiden:
  shopify_*   → Shopify winkel
  kas_*        → Restaurant de Kas
  kitlv_*      → KITLV
"""

import os
import uvicorn
from mcp.server.fastmcp import FastMCP

# Importeer de data-functies direct (niet de mcp-instanties)
import shopify_mcp as _shopify
import kas_mcp as _kas
import kitlv_mcp as _kitlv
import discovery_mcp as _discovery

PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP("ai-site-layer", host="0.0.0.0", port=PORT)


# --- Shopify tools ---

@mcp.tool()
def shopify_list_products() -> str:
    """Geeft een overzicht van alle producten in de Shopify winkel met prijs en beschikbaarheid."""
    return _shopify.list_products()

@mcp.tool()
def shopify_check_product(query: str) -> str:
    """Zoekt een Shopify product op naam. Geeft prijs, varianten, voorraad, beschrijving en afbeelding terug."""
    return _shopify.check_product(query)

@mcp.tool()
def shopify_search_products(query: str = "", available_only: bool = False,
                             min_price: float = 0.0, max_price: float = 999999.0,
                             sort_by: str = "name") -> str:
    """Zoek Shopify producten met filters op prijs, beschikbaarheid en sortering."""
    return _shopify.search_products(query, available_only, min_price, max_price, sort_by)


# --- Restaurant de Kas tools ---

@mcp.tool()
def kas_get_menu() -> str:
    """Geeft het lunch- en dinermenu van Restaurant de Kas met prijzen en dieetwensen."""
    return _kas.get_menu()

@mcp.tool()
def kas_get_info() -> str:
    """Geeft adres, openingstijden, telefoon en parkeerinformatie van Restaurant de Kas."""
    return _kas.get_info()

@mcp.tool()
def kas_check_availability(party_size: int, meal_type: str = "diner") -> str:
    """Geeft reserveringsinformatie voor Restaurant de Kas inclusief totaalprijs per gezelschap."""
    return _kas.check_availability(party_size, meal_type)


# --- KITLV tools ---

@mcp.tool()
def kitlv_get_events() -> str:
    """Geeft aankomende evenementen van KITLV met datum en locatie."""
    return _kitlv.get_events()

@mcp.tool()
def kitlv_search_events(query: str) -> str:
    """Zoek KITLV evenementen op trefwoord zoals 'Caribbean' of 'klimaat'."""
    return _kitlv.search_events(query)

@mcp.tool()
def kitlv_search_projects(query: str = "") -> str:
    """Zoek KITLV onderzoeksprojecten op trefwoord. Leeg = alle projecten."""
    return _kitlv.search_projects(query)

@mcp.tool()
def kitlv_get_info() -> str:
    """Geeft algemene informatie over KITLV: missie, onderzoeksgebieden en contactinfo."""
    return _kitlv.get_info()

@mcp.tool()
def kitlv_list_staff(role: str = "") -> str:
    """Geeft een lijst van KITLV-medewerkers. Filter op rol: 'senior', 'phd', 'postdoc'."""
    return _kitlv.list_staff(role)

@mcp.tool()
def kitlv_get_researcher(name: str) -> str:
    """Zoek een KITLV-onderzoeker op naam en geef profiel, projecten en publicaties terug."""
    return _kitlv.get_researcher(name)

@mcp.tool()
def kitlv_get_news(query: str = "") -> str:
    """Geeft recent nieuws van KITLV. Optioneel gefilterd op trefwoord."""
    return _kitlv.get_news(query)


# --- Discovery tools ---

@mcp.tool()
def discover(url: str) -> str:
    """Controleer of een website een MCP-server heeft via de meta-tag. Geeft de server-URL en beschikbare tools terug."""
    return _discovery.discover(url)

@mcp.tool()
def discover_and_query(url: str, question: str) -> str:
    """Stel een vraag over een website. Gebruikt automatisch de MCP-server als die beschikbaar is, anders leest hij de pagina direct."""
    return _discovery.discover_and_query(url, question)


if __name__ == "__main__":
    print(f"Server draait op http://0.0.0.0:{PORT}/mcp")
    mcp.run(transport="streamable-http")
