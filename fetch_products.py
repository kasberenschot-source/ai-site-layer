#!/usr/bin/env python3
"""
Haalt productdata op van een Shopify /products.json endpoint en zet het om
naar een schone, vaste structuur per product.
"""

import http.cookiejar
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict

SHOP_URL = "https://test-ufkwyvbr.myshopify.com"
SHOP_PASSWORD = "tiraws"


@dataclass
class Variant:
    sku: str
    option1: str | None  # bijv. maat
    option2: str | None  # bijv. kleur
    price: str
    currency: str
    available: bool


@dataclass
class Product:
    id: int
    name: str
    variants: list[Variant] = field(default_factory=list)


def make_opener() -> urllib.request.OpenerDirector:
    """Bouwt een opener met cookie-opslag en logt in op de wachtwoordpagina."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "shopify-mcp-agent/1.0")]

    # POST naar /password om sessie-cookie te verkrijgen
    payload = urllib.parse.urlencode({"password": SHOP_PASSWORD}).encode()
    req = urllib.request.Request(f"{SHOP_URL}/password", data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener.open(req, timeout=10)  # cookie wordt automatisch opgeslagen in jar
    return opener


def fetch_raw(url: str, opener: urllib.request.OpenerDirector) -> dict:
    with opener.open(url, timeout=10) as response:
        return json.loads(response.read())


def parse_products(raw: dict) -> list[Product]:
    products = []
    for p in raw.get("products", []):
        variants = [
            Variant(
                sku=v.get("sku") or "",
                option1=v.get("option1"),
                option2=v.get("option2"),
                price=v.get("price", "0.00"),
                currency="EUR",  # Shopify /products.json bevat geen valuta; stel in op jouw winkelvaluta
                available=v.get("available", False),
            )
            for v in p.get("variants", [])
        ]
        products.append(Product(id=p["id"], name=p["title"], variants=variants))
    return products


def main():
    url = f"{SHOP_URL}/products.json?limit=250"
    print(f"Ophalen van {url} ...")
    opener = make_opener()
    raw = fetch_raw(url, opener)
    products = parse_products(raw)

    print(f"\n{len(products)} product(en) gevonden:\n")
    for product in products:
        print(f"  [{product.id}] {product.name}")
        for v in product.variants:
            status = "✓ beschikbaar" if v.available else "✗ niet beschikbaar"
            opties = " / ".join(filter(None, [v.option1, v.option2]))
            print(f"      SKU={v.sku or '(geen)'} | {opties or '(geen opties)'} | {v.price} {v.currency} | {status}")

    print("\nRuwe JSON (eerste product):")
    if products:
        print(json.dumps(asdict(products[0]), indent=2))


if __name__ == "__main__":
    main()
