"""
Botel Amsterdam scraper.
Haalt kamerinformatie, faciliteiten, locatie en live prijzen op.
"""

import urllib.request
import urllib.parse
import re
import time
import json
from datetime import datetime, timedelta

_BASE_URL = "https://www.botel.nl/nl"
_BOOKING_URL = "https://engines.hoteliers.com/nl/42/booking/getdata"
_cache = {}
_CACHE_TTL = 3600

def _fetch(url):
    now = time.time()
    if url in _cache and now - _cache[url]["ts"] < _CACHE_TTL:
        return _cache[url]["html"]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        html = r.read().decode("utf-8", errors="ignore")
    _cache[url] = {"html": html, "ts": now}
    return html


def get_info() -> str:
    """Geeft algemene informatie over Botel Amsterdam: wat het is, locatie, bereikbaarheid en contact."""
    return """Botel Amsterdam — 3-sterren hotel op een boot

Botel Amsterdam is een uniek hotel gevestigd op een schip aan de NDSM-pier in Amsterdam Noord.
Het biedt een authentieke bootervaring met alle hotelcomfort.

LOCATIE
Adres: NDSM-Pier 3, 1033 RG Amsterdam
Wijk: Amsterdam Noord, aan het IJ

BEREIKBAARHEID
- Gratis veerboot (GVB pont) 2x per uur, 10 minuten naar Amsterdam Centraal Station
- Schiphol: ~15 minuten met de trein vanaf Centraal Station
- Parkeren: openbaar parkeren nabij voor €8 per dag (geen reservering mogelijk)

CONTACT
Telefoon: +31 20 626 4247
Email: info@botel.nl
Website: www.botel.nl

STERREN: 3 sterren
KVK: 66594545 (Botel B.V.)"""


def get_rooms() -> str:
    """Geeft een overzicht van alle kamertypen bij Botel Amsterdam met beschrijving en capaciteit."""
    return """KAMERTYPEN BOTEL AMSTERDAM

SCHEEPSHUTTEN (Cabins)
1. Scheepshut Tweepersoonsbed — queensize bed, eigen badkamer, 2 personen
2. Scheepshut 2 Aparte Bedden — 2 eenpersoonsbedden, eigen badkamer, 2 personen
3. Deluxe Scheepshut Tweepersoonsbed — queensize bed, uitzicht op het IJ, eigen badkamer, 2 personen
4. Vierpersoons Scheepshut — 2 stapelbedden, eigen badkamer, 4 personen
5. Deluxe Vierpersoons Scheepshut — 2 twinbedden, uitzicht op het IJ, eigen badkamer, 4 personen

LOFT SUITES (Design suites, elk uniek thema)
6. Loft Letter B — halfpipe skater design, tweepersoonsbed, 2 personen
7. Loft Letter O — romantische suite, rond bed, spiegelplafond, 2 personen
8. Loft Letter T — zakelijke suite voor werkende gasten, luxe voorzieningen, 2 personen
9. Loft Letter E — filmthema, kingsize bedden, geschikt voor 4 personen
10. Loft Letter L — Japanse minimalistische stijl, wit thema, 2 personen

ALLE KAMERS HEBBEN
- Eigen badkamer met toilet
- Gratis wifi
- Verwarming
- Niet-roken

BOEK VIA: www.botel.nl → Boek nu, of bel +31 20 626 4247"""


def get_facilities() -> str:
    """Geeft alle faciliteiten van Botel Amsterdam: ontbijt, bar, wifi, parkeren, huisdieren etc."""
    return """FACILITEITEN BOTEL AMSTERDAM

ETEN & DRINKEN
- Dagelijks ontbijtbuffet (optioneel bij boeking)
- Bar met pooltafel en videospellen
- Vending machines voor snacks en dranken
- Terras (weersafhankelijk, uitzicht over het IJ)

PRAKTISCH
- 24-uurs receptie
- Gratis wifi in alle ruimtes
- Bagageopslag
- Tour desk (uitjes en activiteiten boeken)
- Privé in- en uitcheck mogelijkheid
- Lift aanwezig
- Kluisjes op de kamers

VERVOER & PARKEREN
- Gratis GVB veerboot naar Amsterdam Centraal (2x per uur, 10 min)
- Openbaar parkeren nabij: €8 per dag, geen reservering
- Fiets- en autoverhuur beschikbaar

OVERIG
- Niet-roken hotel
- Huisdieren NIET toegestaan
- Beveiliging: camerabewaking, rookmelders, brandblussers

CHECK-IN / CHECK-OUT
- Inchecken: vanaf 15:00
- Uitchecken: voor 11:00"""


def _parse_rooms_from_html(html):
    """Extraheert beschikbare en niet-beschikbare kamers uit de Hoteliers.com JSON in de HTML."""
    available, unavailable = [], []

    def extract_list(key):
        match = re.search(rf'"{key}":\s*(\[)', html)
        if not match:
            return []
        start = match.start(1)
        depth, end = 0, start
        for i, c in enumerate(html[start:]):
            if c == '[': depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    end = start + i + 1
                    break
        try:
            return json.loads(html[start:end])
        except Exception:
            return []

    for room in extract_list("available"):
        available.append({"name": room.get("room_name", ""), "price": room.get("room_price", 0)})
    for room in extract_list("unavailable"):
        unavailable.append({"name": room.get("room_name", "")})

    return available, unavailable


def get_prices(checkin: str = "", checkout: str = "") -> str:
    """Geeft live kamerprijzen van Botel Amsterdam. Optioneel: checkin en checkout datum (formaat: DD-MM-YYYY). Standaard: vandaag voor morgen."""
    try:
        if not checkin or not checkout:
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            checkin = today.strftime("%d-%m-%Y")
            checkout = tomorrow.strftime("%d-%m-%Y")

        url = f"{_BOOKING_URL}/arrival/{checkin}/departure/{checkout}"
        html = _fetch(url)
        available, unavailable = _parse_rooms_from_html(html)

        lines = [f"LIVE PRIJZEN BOTEL AMSTERDAM\n{checkin} → {checkout} (1 nacht)\n"]

        if available:
            lines.append("BESCHIKBAAR:")
            for r in available:
                lines.append(f"  ✓ {r['name']}: €{r['price']:.0f} per nacht (incl. belastingen)")
        else:
            lines.append("  Geen kamers beschikbaar voor deze periode.")

        if unavailable:
            lines.append("\nNIET BESCHIKBAAR:")
            for r in unavailable:
                lines.append(f"  ✗ {r['name']}")

        lines.append(f"\nBoek direct: https://www.botel.nl | +31 20 626 4247 | info@botel.nl")
        return "\n".join(lines)

    except Exception as e:
        return f"Kon prijzen niet ophalen ({e}). Bel +31 20 626 4247 of check www.botel.nl."


def check_availability(checkin: str, checkout: str, guests: int = 2) -> str:
    """Controleer beschikbaarheid bij Botel Amsterdam. Geef checkin en checkout in formaat DD-MM-YYYY en het aantal gasten."""
    try:
        url = f"{_BOOKING_URL}/arrival/{checkin}/departure/{checkout}"
        html = _fetch(url)
        available, unavailable = _parse_rooms_from_html(html)

        lines = [f"BESCHIKBAARHEID BOTEL AMSTERDAM\n{checkin} → {checkout} | {guests} gast(en)\n"]

        if available:
            lines.append("BESCHIKBAAR:")
            for r in available:
                lines.append(f"  ✓ {r['name']} — €{r['price']:.0f}/nacht")
        else:
            lines.append("  Geen kamers beschikbaar voor deze periode.")

        if unavailable:
            lines.append("\nNIET BESCHIKBAAR:")
            for r in unavailable:
                lines.append(f"  ✗ {r['name']}")

        lines.append(f"\nBoek direct: +31 20 626 4247 | info@botel.nl | www.botel.nl")
        return "\n".join(lines)

    except Exception as e:
        return f"Kon beschikbaarheid niet ophalen ({e}). Bel +31 20 626 4247."
