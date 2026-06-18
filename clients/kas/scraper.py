#!/usr/bin/env python3
"""
Lokale MCP-server voor Restaurant de Kas.
Geeft menudata, prijzen en praktische info terug aan agents.

Aanpak: we scrapen twee pagina's (/nl/menu en /nl/contact) en
parsen de HTML met regex. Geen externe dependencies nodig.
"""

import json
import re
import time
import urllib.request
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://restaurantdekas.com"
CACHE_SECONDS = 3600  # restaurantmenu's veranderen niet elk uur

mcp = FastMCP("restaurant-de-kas")

_cache: dict = {"data": None, "fetched_at": 0.0}


# --- scraping helpers ---

def _fetch_html(path: str) -> str:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "kas-mcp-agent/1.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8")


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _parse_menu(html: str) -> dict:
    """Haal lunch- en dinerprijzen op uit de menupagina."""
    text = _strip_html(html)

    # Zoek patronen als "3 gerechten € 55" of "3 gerechten €55"
    lunch = []
    diner = []

    # Match: getal + "gerechten" + prijs
    pattern = re.compile(r"(\d)\s*gerechten[^€]*€\s*(\d+)", re.IGNORECASE)
    matches = pattern.findall(text)

    # Onderscheid lunch (3-5 gangen, goedkoper) en diner (5-6 gangen, duurder)
    # op basis van positie in de tekst
    # Formaat op de site: "Menu 3 gerechten: € 55"
    pattern = re.compile(r"Menu\s+(\d)\s+gerechten[^€]*€\s*(\d+)", re.IGNORECASE)

    lunch_section = re.search(r"LUNCH(.+?)DINER", text, re.DOTALL)
    diner_section = re.search(r"DINER(.+?)$", text, re.DOTALL)

    if lunch_section:
        for m in pattern.finditer(lunch_section.group(1)):
            lunch.append({"gangen": int(m.group(1)), "prijs": int(m.group(2)), "valuta": "EUR"})

    if diner_section:
        for m in pattern.finditer(diner_section.group(1)):
            diner.append({"gangen": int(m.group(1)), "prijs": int(m.group(2)), "valuta": "EUR"})

    # Dieetwensen ophalen
    dieet = []
    for optie in ["vegetarisch", "veganistisch", "glutenvrij", "notenvrij", "lactosevrij"]:
        if optie in text.lower():
            dieet.append(optie)

    return {"lunch": lunch, "diner": diner, "dieetwensen": dieet}


def _parse_contact(html: str) -> dict:
    """Haal adres, openingstijden en contactinfo op."""
    text = _strip_html(html)
    return {
        "adres": "Kamerlingh Onneslaan 3, 1097 DE Amsterdam",
        "telefoon": "+31204624562",
        "email": "info@restaurantdekas.nl",
        "openingstijden": {
            "lunch": "Ma t/m za: 12:00 – 13:45",
            "diner": "Ma t/m za: 18:00 – 21:00",
        },
        "parkeren": [
            "Straatparkeren op Kamerlingh Onneslaan en Middenweg (€5/uur, 09:00-21:00)",
            "Parkeergarage Vomar, Middenweg 69 (€6/uur)",
        ],
        "locatie": "Park Frankendael, Amsterdam",
        "website": f"{BASE_URL}/nl/menu",
    }


def _fetch_all() -> dict:
    now = time.time()
    if _cache["data"] is not None and now - _cache["fetched_at"] < CACHE_SECONDS:
        return _cache["data"]

    menu_html = _fetch_html("/nl/menu")
    contact_html = _fetch_html("/nl/contact")

    data = {
        "menu": _parse_menu(menu_html),
        "contact": _parse_contact(contact_html),
    }

    _cache["data"] = data
    _cache["fetched_at"] = now
    return data


# --- MCP tools ---

@mcp.tool()
def get_menu() -> str:
    """
    Geeft het huidige lunch- en dinermenu van Restaurant de Kas terug,
    inclusief prijzen per aantal gangen en beschikbare dieetwensen.
    """
    data = _fetch_all()
    menu = data["menu"]

    lines = ["**Restaurant de Kas — Menu**", ""]

    lines.append("Lunch:")
    if menu["lunch"]:
        for item in sorted(menu["lunch"], key=lambda x: x["gangen"]):
            lines.append(f"  {item['gangen']} gangen — €{item['prijs']}")
    else:
        lines.append("  (geen lunchprijzen gevonden)")

    lines.append("")
    lines.append("Diner:")
    if menu["diner"]:
        for item in sorted(menu["diner"], key=lambda x: x["gangen"]):
            lines.append(f"  {item['gangen']} gangen — €{item['prijs']}")
    else:
        lines.append("  (geen dinerprijzen gevonden)")

    if menu["dieetwensen"]:
        lines.append("")
        lines.append(f"Dieetwensen mogelijk: {', '.join(menu['dieetwensen'])}")

    return "\n".join(lines)


@mcp.tool()
def get_info() -> str:
    """
    Geeft praktische informatie over Restaurant de Kas: adres, openingstijden,
    telefoon, email, parkeren en locatie.
    """
    data = _fetch_all()
    c = data["contact"]

    lines = [
        "**Restaurant de Kas — Praktische info**",
        "",
        f"Adres: {c['adres']}",
        f"Locatie: {c['locatie']}",
        f"Telefoon: {c['telefoon']}",
        f"Email: {c['email']}",
        "",
        "Openingstijden:",
        f"  Lunch: {c['openingstijden']['lunch']}",
        f"  Diner: {c['openingstijden']['diner']}",
        "",
        "Parkeren:",
    ]
    for p in c["parkeren"]:
        lines.append(f"  - {p}")

    lines.append(f"\nMenu & reservering: {c['website']}")
    return "\n".join(lines)


@mcp.tool()
def check_availability(party_size: int, meal_type: str = "diner") -> str:
    """
    Geeft aan of een reservering mogelijk is en wat de relevante info is.
    party_size: aantal personen
    meal_type: 'lunch' of 'diner'
    """
    data = _fetch_all()
    c = data["contact"]
    menu = data["menu"]

    meal = meal_type.lower()
    if meal not in ("lunch", "diner"):
        return "meal_type moet 'lunch' of 'diner' zijn."

    tijden = c["openingstijden"].get(meal, "onbekend")
    prijzen = menu.get(meal, [])

    lines = [
        f"**Reservering {meal} voor {party_size} personen**",
        "",
        f"Openingstijden: {tijden}",
        f"Telefoon: {c['telefoon']}",
        f"Email: {c['email']}",
        "",
        "Beschikbare menu's:",
    ]
    for item in sorted(prijzen, key=lambda x: x["gangen"]):
        totaal = item["prijs"] * party_size
        lines.append(f"  {item['gangen']} gangen — €{item['prijs']} p.p. (totaal €{totaal} voor {party_size} personen)")

    lines.append("")
    lines.append("Reserveren via de website of telefonisch.")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
