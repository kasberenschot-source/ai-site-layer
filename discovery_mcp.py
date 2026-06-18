#!/usr/bin/env python3
"""
MCP Discovery Agent

Werking:
1. Haal de HTML van een URL op
2. Zoek naar een <meta name="mcp-server" content="..."> tag
3. Als gevonden: verbind met die MCP-server en roep de beste tool aan
4. Als niet gevonden: geef de schone tekst van de pagina terug

Zo kunnen agents automatisch de beste databron voor elke site vinden.
"""

import json
import re
import urllib.request
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("discovery-agent")


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "mcp-discovery-agent/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8", errors="replace")


def _find_mcp_server(html: str) -> str | None:
    """Zoek naar <meta name="mcp-server" content="..."> in de HTML."""
    match = re.search(
        r'<meta\s+name=["\']mcp-server["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    )
    if match:
        return match.group(1)
    # Ook omgekeerde volgorde: content eerst, dan name
    match = re.search(
        r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']mcp-server["\']',
        html, re.IGNORECASE
    )
    return match.group(1) if match else None


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


class MCPClient:
    """Eenvoudige JSON-RPC client voor MCP-servers."""

    def __init__(self, url: str):
        self.url = url
        self.session_id = None
        self._initialize()

    def _post(self, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        req = urllib.request.Request(self.url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            # Sla session-id op voor vervolgvragen
            self.session_id = r.headers.get("mcp-session-id", self.session_id)
            raw = r.read().decode()

        # SSE-formaat: "data: {...}\n\n" → pak de JSON eruit
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return json.loads(raw)

    def _initialize(self):
        self._post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "discovery-agent", "version": "1.0"}
            }
        })

    def list_tools(self) -> list[dict]:
        result = self._post({
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/list", "params": {}
        })
        return result.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        result = self._post({
            "jsonrpc": "2.0", "id": 3,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        })
        content = result.get("result", {}).get("content", [])
        return " ".join(c.get("text", "") for c in content if c.get("type") == "text")


def _pick_best_tool(tools: list[dict], question: str) -> tuple[str, dict]:
    """Kies de beste tool op basis van de vraag en de tool-beschrijvingen."""
    q = question.lower()

    # Score elke tool op basis van overlap met de vraag
    best_tool = None
    best_score = -1

    for tool in tools:
        name = tool.get("name", "")
        desc = tool.get("description", "").lower()
        score = sum(1 for word in q.split() if len(word) > 3 and word in desc)
        if score > best_score:
            best_score = score
            best_tool = tool

    if not best_tool:
        best_tool = tools[0]

    # Bouw argumenten op basis van het schema van de tool
    name = best_tool["name"]
    schema = best_tool.get("inputSchema", {})
    props = schema.get("properties", {})

    arguments = {}
    # Vul het eerste string-argument met de vraag als zoekopdracht
    for prop_name, prop_schema in props.items():
        if prop_schema.get("type") == "string" and prop_name in ("query", "name", "search"):
            arguments[prop_name] = question
            break

    return name, arguments


# --- MCP tools ---

@mcp.tool()
def discover(url: str) -> str:
    """
    Controleer of een website een MCP-server heeft.
    Geeft de server-URL en beschikbare tools terug als die er is.
    url: de volledige URL van de website (bijv. https://restaurantdekas.com)
    """
    try:
        html = _fetch_html(url)
    except Exception as e:
        return f"Kon {url} niet ophalen: {e}"

    mcp_url = _find_mcp_server(html)

    if not mcp_url:
        return f"Geen MCP-server gevonden op {url}.\n(De site heeft geen <meta name=\"mcp-server\"> tag.)"

    try:
        client = MCPClient(mcp_url)
        tools = client.list_tools()
        tool_names = [t["name"] for t in tools]
        return (
            f"MCP-server gevonden: {mcp_url}\n"
            f"Beschikbare tools ({len(tools)}):\n" +
            "\n".join(f"  - {t['name']}: {t.get('description', '')[:80]}" for t in tools)
        )
    except Exception as e:
        return f"MCP-server gevonden op {mcp_url} maar verbinding mislukt: {e}"


@mcp.tool()
def discover_and_query(url: str, question: str) -> str:
    """
    Stel een vraag over een website. Als de site een MCP-server heeft,
    wordt die gebruikt. Anders wordt de pagina direct gelezen.

    url: de volledige URL van de website
    question: de vraag die je wilt stellen over de site
    """
    try:
        html = _fetch_html(url)
    except Exception as e:
        return f"Kon {url} niet ophalen: {e}"

    mcp_url = _find_mcp_server(html)

    if mcp_url:
        try:
            client = MCPClient(mcp_url)
            tools = client.list_tools()
            tool_name, arguments = _pick_best_tool(tools, question)
            result = client.call_tool(tool_name, arguments)
            return f"[Via MCP-server: {mcp_url}]\n\n{result}"
        except Exception as e:
            # Fallback naar HTML als MCP-server faalt
            pass

    # Geen MCP-server of fout: geef schone tekst terug
    text = _strip_html(html)[:3000]
    return f"[Geen MCP-server gevonden, pagina direct gelezen]\n\n{text}"


if __name__ == "__main__":
    mcp.run()
