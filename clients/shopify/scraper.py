#!/usr/bin/env python3
"""
Lokale MCP-server die Shopify productdata beschikbaar stelt via twee tools:
  - list_products()        → overzicht van alle producten
  - check_product(query)   → prijs, varianten en voorraad van één product
"""

import json
import http.cookiejar
import time
import urllib.parse
import urllib.request
from mcp.server.fastmcp import FastMCP

SHOP_URL = "https://test-ufkwyvbr.myshopify.com"
SHOP_PASSWORD = "tiraws"
CACHE_SECONDS = 300  # data blijft 5 minuten geldig

mcp = FastMCP("shopify-store")

import re

def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# Cache: bewaar de producten en het tijdstip van de laatste fetch
_cache: dict = {"products": None, "fetched_at": 0.0}


# --- data ophalen (zelfde logica als fetch_products.py) ---

def _make_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "shopify-mcp-agent/1.0")]
    payload = urllib.parse.urlencode({"password": SHOP_PASSWORD}).encode()
    req = urllib.request.Request(f"{SHOP_URL}/password", data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener.open(req, timeout=10)
    return opener


def _fetch_products() -> list[dict]:
    now = time.time()

    # Geef gecachede data terug als die nog vers genoeg is
    if _cache["products"] is not None and now - _cache["fetched_at"] < CACHE_SECONDS:
        return _cache["products"]

    # Cache verlopen of leeg: haal verse data op
    opener = _make_opener()
    url = f"{SHOP_URL}/products.json?limit=250"
    with opener.open(url, timeout=10) as response:
        raw = json.loads(response.read())

    products = []
    for p in raw.get("products", []):
        # Haal optienamen op (bijv. ["Kleur", "Maat"])
        option_names = [o["name"] for o in p.get("options", [])]

        variants = []
        for v in p.get("variants", []):
            # Koppel optiewaarden aan optienamen: {"Kleur": "Ice", "Maat": "L"}
            options = {}
            for i, name in enumerate(option_names, start=1):
                val = v.get(f"option{i}")
                if val and val != "Default Title":
                    options[name] = val

            compare_at = v.get("compare_at_price")
            variants.append({
                "id": v["id"],
                "sku": v.get("sku") or "",
                "options": options,
                "price": v.get("price", "0.00"),
                "compare_at_price": compare_at,  # originele prijs bij korting
                "currency": "EUR",
                "available": v.get("available", False),
                "requires_shipping": v.get("requires_shipping", True),
                "taxable": v.get("taxable", True),
            })

        # StripHTML uit de beschrijving
        body_html = p.get("body_html") or ""
        description = _strip_html(body_html)

        images = [img["src"] for img in p.get("images", [])]

        products.append({
            "id": p["id"],
            "name": p["title"],
            "handle": p.get("handle", ""),  # URL-slug, bijv. 'the-complete-snowboard'
            "url": f"{SHOP_URL}/products/{p.get('handle', '')}",
            "vendor": p.get("vendor", ""),
            "product_type": p.get("product_type", ""),
            "tags": p.get("tags", []),
            "description": description,
            "images": images,
            "variants": variants,
            "published_at": p.get("published_at", ""),
            "updated_at": p.get("updated_at", ""),
        })

    _cache["products"] = products
    _cache["fetched_at"] = now
    return products


# --- MCP tools ---

def _format_variant(v: dict) -> str:
    opties = ", ".join(f"{k}: {val}" for k, val in v["options"].items()) or "standaard"
    prijs = f"€{v['price']} {v['currency']}"
    if v["compare_at_price"]:
        prijs += f" (was €{v['compare_at_price']})"
    status = "✓ op voorraad" if v["available"] else "✗ niet op voorraad"
    sku = f" | SKU: {v['sku']}" if v["sku"] else ""
    shipping = "" if v["requires_shipping"] else " | geen verzending nodig"
    return f"  - {opties}{sku}: {prijs} — {status}{shipping}"


def _format_product(p: dict, full: bool = True) -> str:
    lines = [f"**{p['name']}**"]
    lines.append(f"  URL: {p['url']}")
    if p["vendor"]:
        lines.append(f"  Merk: {p['vendor']}")
    if p["product_type"]:
        lines.append(f"  Type: {p['product_type']}")
    if p["tags"]:
        lines.append(f"  Tags: {', '.join(p['tags'])}")
    if full and p["description"]:
        lines.append(f"  Beschrijving: {p['description'][:300]}{'...' if len(p['description']) > 300 else ''}")
    if full and p["images"]:
        lines.append(f"  Afbeelding: {p['images'][0]}")
    lines.append("  Varianten:")
    for v in p["variants"]:
        lines.append(_format_variant(v))
    return "\n".join(lines)


@mcp.tool()
def list_products() -> str:
    """Geeft een overzicht van alle producten in de winkel met naam, type, prijs en beschikbaarheid."""
    products = _fetch_products()
    lines = []
    for p in products:
        prijzen = sorted({v["price"] for v in p["variants"]})
        beschikbaar = any(v["available"] for v in p["variants"])
        status = "beschikbaar" if beschikbaar else "niet beschikbaar"
        prijs_str = " / ".join(f"€{pr}" for pr in prijzen)
        type_str = f" [{p['product_type']}]" if p["product_type"] else ""
        lines.append(f"- {p['name']}{type_str} | {prijs_str} | {status} | {p['url']}")
    return "\n".join(lines)


@mcp.tool()
def check_product(query: str) -> str:
    """
    Zoekt een product op naam en geeft volledige details terug: beschrijving,
    merk, tags, afbeelding, prijs, varianten en voorraadstatus.
    query: (deel van) de productnaam, hoofdletterongevoelig.
    """
    products = _fetch_products()
    q = query.lower()
    matches = [p for p in products if q in p["name"].lower()]

    if not matches:
        return f"Geen product gevonden dat '{query}' bevat."

    return "\n\n".join(_format_product(p, full=True) for p in matches)


@mcp.tool()
def search_products(
    query: str = "",
    available_only: bool = False,
    min_price: float = 0.0,
    max_price: float = 999999.0,
    sort_by: str = "name",
) -> str:
    """
    Zoek producten met filters en sortering.

    query:          zoekterm op productnaam (leeg = alle producten)
    available_only: True = alleen producten die op voorraad zijn
    min_price:      minimumprijs (bijv. 50.0)
    max_price:      maximumprijs (bijv. 500.0)
    sort_by:        'name', 'price_asc' (goedkoopste eerst), 'price_desc' (duurste eerst)
    """
    products = _fetch_products()
    q = query.lower()

    results = []
    for p in products:
        # Filter op naam
        if q and q not in p["name"].lower():
            continue

        # Filter varianten op prijs en beschikbaarheid
        matching_variants = []
        for v in p["variants"]:
            price = float(v["price"])
            if price < min_price or price > max_price:
                continue
            if available_only and not v["available"]:
                continue
            matching_variants.append(v)

        if not matching_variants:
            continue

        min_variant_price = min(float(v["price"]) for v in matching_variants)
        results.append((p, matching_variants, min_variant_price))

    if not results:
        return "Geen producten gevonden die aan de zoekcriteria voldoen."

    # Sorteren
    if sort_by == "price_asc":
        results.sort(key=lambda x: x[2])
    elif sort_by == "price_desc":
        results.sort(key=lambda x: x[2], reverse=True)
    else:
        results.sort(key=lambda x: x[0]["name"])

    lines = []
    for p, variants, _ in results:
        p_filtered = {**p, "variants": variants}
        lines.append(_format_product(p_filtered, full=False))

    return "\n\n".join(lines)


if __name__ == "__main__":
    mcp.run()
