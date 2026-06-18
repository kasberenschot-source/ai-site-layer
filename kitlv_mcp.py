#!/usr/bin/env python3
"""
Lokale MCP-server voor KITLV (Koninklijk Nederlands Instituut voor
Taal-, Land- en Volkenkunde). Geeft evenementen, projecten en
contactinfo terug aan agents.
"""

import re
import time
import urllib.request
from html.parser import HTMLParser
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://www.kitlv.nl"
CACHE_SECONDS = 1800  # 30 minuten

mcp = FastMCP("kitlv")

_cache: dict = {"data": None, "fetched_at": 0.0}
_staff_cache: dict = {}       # {url_path: {naam, functie, ...}}
_staff_list_cache: dict = {"data": None, "fetched_at": 0.0}
_news_cache: dict = {"data": None, "fetched_at": 0.0}


# --- scraping helpers ---

def _fetch_html(path: str) -> str:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "kitlv-mcp-agent/1.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read().decode("utf-8")


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&ndash;", "–").replace("&mdash;", "—")
    text = text.replace("&rsquo;", "'").replace("&lsquo;", "'")
    text = text.replace("&rdquo;", '"').replace("&ldquo;", '"')
    text = re.sub(r"&#\d+;", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_staff_list(html: str) -> list[dict]:
    """Haal alle medewerkers op uit de people-pagina.
    Structuur: <article> met daarin een <a href="/people/...">, <h3> (naam) en <span> (functie).
    """
    staff = []
    for article in re.finditer(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE):
        block = article.group(1)

        # Profiel-URL
        url_match = re.search(r'href="(/people/[^"]+)"', block)
        if not url_match:
            continue
        path = url_match.group(1)

        # Naam uit h3
        naam_match = re.search(r'<h[23][^>]*>(.*?)</h[23]>', block, re.DOTALL)
        if not naam_match:
            continue
        naam = _strip_html(naam_match.group(1))
        if len(naam) < 3 or len(naam) > 100:
            continue

        # Functie uit span
        functie = ""
        span_match = re.search(r'<span[^>]*>(.*?)</span>', block, re.DOTALL)
        if span_match:
            functie = _strip_html(span_match.group(1))

        staff.append({"naam": naam, "functie": functie, "profiel_url": path})

    return staff


def _parse_profile(html: str, naam: str) -> dict:
    """Haal profieldata op uit een individuele medewerker-pagina."""
    text = _strip_html(html)

    # Zoek onderzoeksgebieden / bio-sectie
    # De pagina heeft blokken tekst na de naam
    bio = ""
    bio_match = re.search(r'(?:research|onderzoek|biography|bio)[^.]{0,50}[.:]\s*(.{100,800})', text, re.IGNORECASE)
    if bio_match:
        bio = bio_match.group(1)[:500]

    # Zoek projecten (links naar /projects/)
    projecten = re.findall(r'href="/projects/([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE)
    projecten_clean = [_strip_html(p[1]) for p in projecten if len(_strip_html(p[1])) > 5]

    # Zoek publicaties (h2/h3 na "publications")
    publicaties = []
    pub_section = re.search(r'[Pp]ublications?(.*?)(?:<h[12]|$)', html, re.DOTALL)
    if pub_section:
        for m in re.finditer(r'<(?:li|p)[^>]*>(.*?)</(?:li|p)>', pub_section.group(1), re.DOTALL):
            pub = _strip_html(m.group(1))
            if len(pub) > 20:
                publicaties.append(pub[:200])

    # Zoek email
    email_match = re.search(r'[\w.+-]+@kitlv\.nl', text)
    email = email_match.group(0) if email_match else ""

    # Pak de eerste alinea als bio-fallback
    if not bio:
        alineas = [p for p in re.split(r'\s{3,}', text) if len(p) > 100]
        if alineas:
            bio = alineas[0][:500]

    return {
        "naam": naam,
        "bio": bio.strip(),
        "projecten": projecten_clean[:10],
        "publicaties": publicaties[:5],
        "email": email,
        "url": "",
    }


def _parse_news(html: str) -> list[dict]:
    """Haal nieuws op."""
    items = []
    for block in re.split(r'<h[23][^>]*>', html)[1:]:
        title_match = re.match(r'(.*?)</h[23]>', block, re.DOTALL)
        if not title_match:
            continue
        titel = _strip_html(title_match.group(1))
        if len(titel) < 5 or len(titel) > 200:
            continue
        context = _strip_html(block[:400])

        # Datum zoeken
        date_match = re.search(
            r'\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|'
            r'January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}',
            context, re.IGNORECASE
        )
        items.append({
            "titel": titel,
            "datum": date_match.group(0) if date_match else "",
            "samenvatting": context[:200],
        })
    return items[:15]


def _parse_events(html: str) -> list[dict]:
    """Haal evenementen op uit de events-pagina."""
    events = []

    # Elk evenement staat in een article of div met datum en titel
    # Patroon: zoek blokken met een datum (dag maand jaar) en een titel
    blocks = re.findall(
        r'<(?:article|div)[^>]*class="[^"]*(?:event|post|entry)[^"]*"[^>]*>(.*?)</(?:article|div)>',
        html, re.DOTALL | re.IGNORECASE
    )

    # Fallback: zoek op datum-patroon gevolgd door een titel
    date_pattern = re.compile(
        r'(\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|'
        r'January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+\d{4})',
        re.IGNORECASE
    )

    # Zoek alle H2/H3 titels met omliggende context
    title_blocks = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', html, re.DOTALL | re.IGNORECASE)

    # Zoek datums in de buurt van titels
    for i, block in enumerate(re.split(r'<h[23][^>]*>', html)[1:]):
        title_match = re.match(r'(.*?)</h[23]>', block, re.DOTALL)
        if not title_match:
            continue
        title = _strip_html(title_match.group(1))
        if len(title) < 5 or len(title) > 200:
            continue

        # Zoek datum in de 500 tekens na de titel
        context = _strip_html(block[:500])
        date_match = date_pattern.search(context)
        date = date_match.group(1) if date_match else "datum onbekend"

        # Zoek locatie
        locatie = "KITLV, Leiden"
        if "amsterdam" in context.lower():
            locatie = "Amsterdam"
        elif "online" in context.lower():
            locatie = "Online"

        events.append({
            "titel": title,
            "datum": date,
            "locatie": locatie,
            "beschrijving": context[:200].strip(),
        })

    return events[:20]  # max 20 evenementen


def _parse_projects(html: str) -> list[dict]:
    """Haal onderzoeksprojecten op."""
    projects = []

    for block in re.split(r'<h[23][^>]*>', html)[1:]:
        title_match = re.match(r'(.*?)</h[23]>', block, re.DOTALL)
        if not title_match:
            continue
        title = _strip_html(title_match.group(1))
        if len(title) < 5 or len(title) > 300:
            continue

        context = _strip_html(block[:600])
        projects.append({
            "titel": title,
            "beschrijving": context[:300].strip(),
        })

    return projects[:43]


def _fetch_all() -> dict:
    now = time.time()
    if _cache["data"] is not None and now - _cache["fetched_at"] < CACHE_SECONDS:
        return _cache["data"]

    events_html = _fetch_html("/events/")
    projects_html = _fetch_html("/projects/")

    data = {
        "evenementen": _parse_events(events_html),
        "projecten": _parse_projects(projects_html),
        "contact": {
            "naam": "KITLV — Koninklijk Nederlands Instituut voor Taal-, Land- en Volkenkunde",
            "adres": "Witte Singel 27A, 2311 BG Leiden",
            "telefoon": "+31 (0)71 527 2372",
            "email": "kitlv@kitlv.nl",
            "website": BASE_URL,
            "opgericht": 1851,
            "onderdeel_van": "KNAW (Koninklijke Nederlandse Akademie van Wetenschappen)",
            "onderzoeksgebieden": ["Caribisch gebied", "Zuidoost-Azië", "Nederland"],
            "onderzoekslijnen": [
                "Staat, geweld en burgerschap",
                "Klimaatgovernance",
                "Mobiliteit en belonging",
            ],
        },
    }

    _cache["data"] = data
    _cache["fetched_at"] = now
    return data


# --- MCP tools ---

@mcp.tool()
def get_events() -> str:
    """
    Geeft aankomende evenementen van KITLV terug: titel, datum en locatie.
    Geschikt voor vragen als 'wat zijn de komende events bij KITLV?'
    """
    data = _fetch_all()
    events = data["evenementen"]

    if not events:
        return "Geen evenementen gevonden."

    lines = ["**KITLV — Aankomende evenementen**", ""]
    for e in events:
        lines.append(f"**{e['titel']}**")
        lines.append(f"  Datum: {e['datum']}")
        lines.append(f"  Locatie: {e['locatie']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def search_events(query: str) -> str:
    """
    Zoek evenementen op trefwoord (bijv. 'Caribbean', 'klimaat', 'seminar').
    """
    data = _fetch_all()
    q = query.lower()
    matches = [
        e for e in data["evenementen"]
        if q in e["titel"].lower() or q in e["beschrijving"].lower()
    ]

    if not matches:
        return f"Geen evenementen gevonden voor '{query}'."

    lines = [f"**KITLV evenementen over '{query}'**", ""]
    for e in matches:
        lines.append(f"**{e['titel']}**")
        lines.append(f"  Datum: {e['datum']} | Locatie: {e['locatie']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def search_projects(query: str = "") -> str:
    """
    Zoek onderzoeksprojecten op trefwoord (bijv. 'Indonesia', 'climate', 'Caribbean').
    Laat query leeg voor alle projecten.
    """
    data = _fetch_all()
    q = query.lower()
    projects = data["projecten"]

    if q:
        projects = [
            p for p in projects
            if q in p["titel"].lower() or q in p["beschrijving"].lower()
        ]

    if not projects:
        return f"Geen projecten gevonden{' voor ' + query if query else ''}."

    lines = [f"**KITLV onderzoeksprojecten{' — ' + query if query else ''}**", ""]
    for p in projects:
        lines.append(f"- {p['titel']}")

    return "\n".join(lines)


@mcp.tool()
def get_info() -> str:
    """
    Geeft algemene informatie over KITLV: missie, onderzoeksgebieden,
    contact en adres.
    """
    data = _fetch_all()
    c = data["contact"]

    lines = [
        f"**{c['naam']}**",
        "",
        f"Opgericht: {c['opgericht']}",
        f"Onderdeel van: {c['onderdeel_van']}",
        "",
        f"Adres: {c['adres']}",
        f"Telefoon: {c['telefoon']}",
        f"Email: {c['email']}",
        f"Website: {c['website']}",
        "",
        f"Onderzoeksgebieden: {', '.join(c['onderzoeksgebieden'])}",
        "",
        "Onderzoekslijnen:",
    ]
    for lijn in c["onderzoekslijnen"]:
        lines.append(f"  - {lijn}")

    return "\n".join(lines)


@mcp.tool()
def list_staff(role: str = "") -> str:
    """
    Geeft een overzicht van alle KITLV-medewerkers met naam en functie.
    role: filter op rol, bijv. 'senior', 'phd', 'postdoc' (leeg = iedereen).
    """
    now = time.time()
    if _staff_list_cache["data"] is None or now - _staff_list_cache["fetched_at"] > CACHE_SECONDS:
        html = _fetch_html("/about/people/")
        _staff_list_cache["data"] = _parse_staff_list(html)
        _staff_list_cache["fetched_at"] = now

    staff = _staff_list_cache["data"]
    if role:
        staff = [s for s in staff if role.lower() in s["functie"].lower() or role.lower() in s["naam"].lower()]

    if not staff:
        return f"Geen medewerkers gevonden{' voor rol: ' + role if role else ''}."

    lines = [f"**KITLV medewerkers{' — ' + role if role else ''}** ({len(staff)} personen)", ""]
    for s in staff:
        functie_str = f" — {s['functie']}" if s["functie"] else ""
        lines.append(f"- {s['naam']}{functie_str}")

    return "\n".join(lines)


@mcp.tool()
def get_researcher(name: str) -> str:
    """
    Zoek een specifieke KITLV-onderzoeker op naam en geef hun profiel terug:
    onderzoeksgebieden, lopende projecten, publicaties en contactinfo.
    name: (deel van) de naam, bijv. 'Berenschot' of 'Ward Berenschot'.
    """
    now = time.time()
    # Haal de stafflijst op als die er nog niet is
    if _staff_list_cache["data"] is None or now - _staff_list_cache["fetched_at"] > CACHE_SECONDS:
        html = _fetch_html("/about/people/")
        _staff_list_cache["data"] = _parse_staff_list(html)
        _staff_list_cache["fetched_at"] = now

    q = name.lower()
    matches = [s for s in _staff_list_cache["data"] if q in s["naam"].lower()]

    if not matches:
        return f"Geen medewerker gevonden met naam '{name}'."

    results = []
    for person in matches[:3]:  # max 3 resultaten
        path = person["profiel_url"]

        # Check cache
        if path not in _staff_cache:
            try:
                html = _fetch_html(path)
                profiel = _parse_profile(html, person["naam"])
                profiel["url"] = f"{BASE_URL}{path}"
                profiel["functie"] = person["functie"]
                _staff_cache[path] = profiel
            except Exception:
                _staff_cache[path] = {"naam": person["naam"], "functie": person["functie"],
                                       "bio": "", "projecten": [], "publicaties": [], "email": "", "url": f"{BASE_URL}{path}"}

        p = _staff_cache[path]
        lines = [f"**{p['naam']}**"]
        if p.get("functie"):
            lines.append(f"  Functie: {p['functie']}")
        if p.get("email"):
            lines.append(f"  Email: {p['email']}")
        if p.get("url"):
            lines.append(f"  Profiel: {p['url']}")
        if p.get("bio"):
            lines.append(f"\n  {p['bio'][:400]}")
        if p.get("projecten"):
            lines.append("\n  Projecten:")
            for pr in p["projecten"]:
                lines.append(f"    - {pr}")
        if p.get("publicaties"):
            lines.append("\n  Publicaties:")
            for pub in p["publicaties"]:
                lines.append(f"    - {pub}")

        results.append("\n".join(lines))

    return "\n\n---\n\n".join(results)


@mcp.tool()
def get_news(query: str = "") -> str:
    """
    Geeft recent nieuws van KITLV terug.
    query: optioneel trefwoord om te filteren (leeg = al het nieuws).
    """
    now = time.time()
    if _news_cache["data"] is None or now - _news_cache["fetched_at"] > CACHE_SECONDS:
        html = _fetch_html("/news/")
        _news_cache["data"] = _parse_news(html)
        _news_cache["fetched_at"] = now

    items = _news_cache["data"]
    if query:
        q = query.lower()
        items = [i for i in items if q in i["titel"].lower() or q in i["samenvatting"].lower()]

    if not items:
        return f"Geen nieuws gevonden{' voor: ' + query if query else ''}."

    lines = [f"**KITLV Nieuws{' — ' + query if query else ''}**", ""]
    for item in items:
        datum_str = f" ({item['datum']})" if item["datum"] else ""
        lines.append(f"**{item['titel']}**{datum_str}")
        if item["samenvatting"]:
            lines.append(f"  {item['samenvatting'][:150]}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
