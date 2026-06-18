"""
Eye Filmmuseum Amsterdam scraper.
Haalt programma, tentoonstellingen, tickets, faciliteiten en restaurant op.
"""

import urllib.request
import re
import time
import json
from datetime import datetime

_BASE_URL = "https://www.eyefilm.nl/en"
_cache = {}
_CACHE_TTL = 1800  # 30 minuten voor agenda


def _fetch(url, ttl=None):
    ttl = ttl or _CACHE_TTL
    now = time.time()
    if url in _cache and now - _cache[url]["ts"] < ttl:
        return _cache[url]["html"]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="ignore")
    _cache[url] = {"html": html, "ts": now}
    return html


def _get_film_screenings(slug, film_id):
    """Haal screentijden op voor één film."""
    url = f"{_BASE_URL}/whats-on/{slug}/{film_id}"
    try:
        html = _fetch(url)
        times = list(set(re.findall(r"(20\d\d-\d\d-\d\dT\d\d:\d\d)", html)))
        return sorted([t for t in times if t >= datetime.now().strftime("%Y-%m-%dT%H:%M")])
    except Exception:
        return []


def get_info() -> str:
    """Geeft algemene informatie over Eye Filmmuseum: locatie, openingstijden, tickets en bereikbaarheid."""
    return """EYE FILMMUSEUM AMSTERDAM

Eye is het Nederlandse filmmuseum, gelegen aan het IJ tegenover Amsterdam Centraal Station.
Het biedt een bioscoop, wisselende tentoonstellingen en een permanente collectie van >60.000 films.

LOCATIE
Adres: IJpromenade 1, 1031 KT Amsterdam (GPS: Overhoeksplein 1)
Bereikbaarheid: Gratis GVB pont F3 (Buiksloterweg) vanaf Amsterdam Centraal, <5 minuten
Alternatief: Bus 38

OPENINGSTIJDEN
Bioscoopkassa: Ma 18:00–22:00 | Di–Zo 10:00–23:00
Tentoonstelling: Di–Zo 10:00–19:00 (ma gesloten, behalve feestdagen)
Eye Study (collectie): Di–Vr 11:00–16:00

TICKETS & PRIJZEN
Film: €13,50 (standaard) | €12,00 (student) | €8,00 (kind t/m 10 jaar)
Tentoonstelling: €16,00
Alleen pinbetaling — geen contant geld
Tickets niet inwisselbaar of restitueerbaar

GROEPEN (15+ personen)
Aanmelden minimaal 2 weken vooraf via groepsbezoek@eyefilm.nl

TOEGANKELIJKHEID
Volledig rolstoeltoegankelijk (liften aanwezig)
2 rolstoelplaatsen per zaal gereserveerd
Audiodescriptie via Earcatch-app bij geselecteerde films
Hulphonden toegestaan

CONTACT
Website: eyefilm.nl
Adres: IJpromenade 1, 1031 KT Amsterdam"""


def get_exhibitions() -> str:
    """Geeft huidige en aankomende tentoonstellingen bij Eye Filmmuseum."""
    try:
        html = _fetch(f"{_BASE_URL}/whats-on", ttl=3600)

        # Zoek programme items (tentoonstellingen/programmalijnen)
        items = re.findall(
            r'"title":"([^"]+)"[^}]*"supertitle":"([^"]+)"[^}]*"subtitle":"([^"]*)"[^}]*"url":"(https://www\.eyefilm\.nl/en/programme/[^"]+)"',
            html
        )

        if items:
            lines = ["TENTOONSTELLINGEN & PROGRAMMALIJNEN EYE FILMMUSEUM\n"]
            for title, super_title, subtitle, url in items:
                lines.append(f"{title}")
                if super_title:
                    lines.append(f"  Type: {super_title}")
                if subtitle:
                    lines.append(f"  {subtitle}")
                lines.append(f"  Info: {url}\n")
            return "\n".join(lines)
        else:
            return """HUIDIGE TENTOONSTELLINGEN EYE FILMMUSEUM

Eye(s) Open (3 april – 6 september 2026)
  Elf kunstenaars reageren op Eye's collectie koloniale films uit Indonesië en Suriname.
  Tien nieuwe kunstwerken belichten koloniale structuren en de rol van de camera in machtsverhoudingen.

Queer Power (26 juni – 2 september 2026)
  Ter gelegenheid van World Pride Amsterdam — ode aan queer makers wereldwijd.
  Viert vrijheid, diversiteit en inclusiviteit.

Permanente tentoonstelling (altijd open)
  Evolutie van het bewegend beeld, van vroege cinema tot hedendaags werk.
  Aanwezig op de begane grond van het museum.

Meer info: eyefilm.nl/en/whats-on"""

    except Exception as e:
        return f"Kon tentoonstellingen niet ophalen ({e}). Zie eyefilm.nl voor actueel overzicht."


def get_programme(date: str = "", query: str = "") -> str:
    """Zoek films en events bij Eye Filmmuseum. Optioneel: datum (YYYY-MM-DD) of zoekterm (bijv. genre, regisseur, filmtitel)."""
    try:
        html = _fetch(f"{_BASE_URL}/whats-on")

        # Haal alle film-IDs en slugs op
        all_films = re.findall(r'/en/whats-on/([^/\\"]+)/(\d+)', html)
        unique = list(dict.fromkeys(all_films))  # dedup, behoudt volgorde

        if not unique:
            return "Kon het programma niet ophalen. Zie eyefilm.nl/en/whats-on voor actueel overzicht."

        results = []
        checked = 0
        max_check = 30 if (date or query) else 15

        for slug, film_id in unique[:50]:
            if checked >= max_check:
                break

            film_url = f"{_BASE_URL}/whats-on/{slug}/{film_id}"
            try:
                film_html = _fetch(film_url)

                # Titel
                title_match = re.search(r'"name":"([^"]+)"', film_html)
                title = title_match.group(1) if title_match else slug.replace("-", " ").title()

                # Screentijden (toekomst)
                all_times = list(set(re.findall(r"(20\d\d-\d\d-\d\dT\d\d:\d\d)", film_html)))
                now_str = datetime.now().strftime("%Y-%m-%dT%H:%M")
                future_times = sorted([t for t in all_times if t >= now_str])

                if not future_times:
                    continue

                # Filter op datum
                if date:
                    day_times = [t for t in future_times if t.startswith(date)]
                    if not day_times:
                        continue
                    show_times = day_times
                else:
                    show_times = future_times[:5]

                # Filter op zoekopdracht
                if query and query.lower() not in film_html.lower() and query.lower() not in title.lower():
                    continue

                # Beschrijving
                desc_match = re.search(r'"description":"([^"]{20,200})', film_html)
                desc = desc_match.group(1)[:150] + "..." if desc_match else ""
                desc = re.sub(r'\\u003[cp].*?\\u003[cp]', '', desc)

                time_strs = [t.replace("T", " ") for t in show_times]
                results.append(f"  {title}\n    Tijden: {', '.join(time_strs)}\n    {desc}")
                checked += 1

            except Exception:
                continue

        if not results:
            filter_desc = f" op {date}" if date else (f" voor '{query}'" if query else "")
            return f"Geen films gevonden{filter_desc}. Zie eyefilm.nl/en/whats-on voor het volledige programma."

        header = f"PROGRAMMA EYE FILMMUSEUM"
        if date:
            header += f" — {date}"
        if query:
            header += f" — zoek: '{query}'"
        header += f"\n({len(results)} films gevonden)\n"

        return header + "\n\n".join(results) + f"\n\nVolledig programma: eyefilm.nl/en/whats-on"

    except Exception as e:
        return f"Kon programma niet ophalen ({e}). Zie eyefilm.nl/en/whats-on."


def get_restaurant() -> str:
    """Geeft informatie over Eye Bar & Restaurant: openingstijden, eten, drinken en reserveren."""
    return """EYE BAR & RESTAURANT

Een levendige ontmoetingsplek met panoramisch uitzicht over het IJ.
Interieur met lampen van kunstenaar Olafur Eliasson en een 'cinematografische sfeer'.

OPENINGSTIJDEN
Maandag: 18:00–00:00 (alleen dranken)
Dinsdag t/m Zondag: 10:00–00:00

KEUKEN
Lunch: 11:00–16:00
Snacks: 11:00–21:00
Diner: 17:30–21:00
Let op: op 25 juni geen dinerservice, bar open vanaf 19:00

RESERVEREN
Online via de boekingstool op eyefilm.nl
Email: info@eyehoreca.nl
Groepen 9–30 personen: bel of mail +31 (0)6 15 28 94 55
Groepen 30+: contact via Sales & Events team

Inlopen welkom voor koffie, gebak, snacks en dranken (geen reservering nodig)

HONDEN
Welkom in het restaurant en de Arena (niet in de bioscoop of tentoonstelling)"""
