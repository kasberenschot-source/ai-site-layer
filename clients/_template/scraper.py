"""
Scraper template voor nieuwe klanten.
Vervang de URL en pas de functies aan op de site.
"""

import urllib.request
import re
import time

_BASE_URL = "https://website.com"
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
    """Geeft algemene informatie over het bedrijf."""
    html = _fetch(_BASE_URL)
    # Pas dit aan op de site
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


def get_content(query: str = "") -> str:
    """Zoek specifieke informatie op de website."""
    html = _fetch(_BASE_URL)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    if query:
        lines = [l for l in text.split(".") if query.lower() in l.lower()]
        return ". ".join(lines[:10]) or "Geen resultaten gevonden."
    return text[:2000]
