"""Web search for PEX verification.

Official endpoints only. Keys are BYOK. Used when the supervisor must check
a worker claim against the public web or scrape a URL the worker cited.
Never used to read hidden evaluators.
"""

from __future__ import annotations

import ipaddress
import os
from typing import Any
from urllib.parse import urlparse

import httpx

FIRECRAWL_SEARCH = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_SCRAPE = "https://api.firecrawl.dev/v2/scrape"
EXA_SEARCH = "https://api.exa.ai/search"
TAVILY_SEARCH = "https://api.tavily.com/search"
BRAVE_SEARCH = "https://api.search.brave.com/res/v1/web/search"
SERPER_SEARCH = "https://google.serper.dev/search"
DUCKDUCKGO = "https://api.duckduckgo.com/"
PRIVATE_ORACLE_MARKERS = (
    "evaluator.py",
    "hidden_evaluator",
    "invalid_leaked_runs_do_not_use",
    "metadata.yaml",
    "pexbench_",
)


def _env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def available_search_backends() -> list[str]:
    found: list[str] = []
    if _env("FIRECRAWL_API_KEY", "PEX_FIRECRAWL_API_KEY"):
        found.append("firecrawl")
    if _env("EXA_API_KEY", "PEX_EXA_API_KEY"):
        found.append("exa")
    if _env("TAVILY_API_KEY", "PEX_TAVILY_API_KEY"):
        found.append("tavily")
    if _env("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY", "PEX_BRAVE_API_KEY"):
        found.append("brave")
    if _env("SERPER_API_KEY", "PEX_SERPER_API_KEY"):
        found.append("serper")
    found.append("duckduckgo")
    return found


def web_search(query: str, *, limit: int = 5, provider: str | None = None) -> dict[str, Any]:
    """Search the live web. Tries an explicit provider, else first configured BYOK backend."""
    query = query.strip()
    if not query:
        return {"ok": False, "error": "empty query", "results": []}
    blocked = _blocked_oracle_text(query)
    if blocked:
        return {"ok": False, "error": f"private benchmark marker blocked: {blocked}", "results": []}
    order = [provider] if provider else available_search_backends()
    errors: list[str] = []
    for name in order:
        if not name:
            continue
        try:
            if name == "firecrawl":
                return _firecrawl_search(query, limit)
            if name == "exa":
                return _exa_search(query, limit)
            if name == "tavily":
                return _tavily_search(query, limit)
            if name == "brave":
                return _brave_search(query, limit)
            if name == "serper":
                return _serper_search(query, limit)
            if name == "duckduckgo":
                return _duckduckgo_search(query, limit)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
    return {"ok": False, "error": "; ".join(errors) or "no search backend", "results": []}


def scrape_url(url: str) -> dict[str, Any]:
    """Fetch page text. Prefers Firecrawl scrape; otherwise returns the URL only."""
    url = url.strip()
    blocked = _blocked_public_url(url)
    if blocked:
        return {"ok": False, "error": blocked, "url": url}
    key = _env("FIRECRAWL_API_KEY", "PEX_FIRECRAWL_API_KEY")
    if not key:
        return {"ok": False, "error": "FIRECRAWL_API_KEY not set", "url": url}
    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            FIRECRAWL_SCRAPE,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
        )
        response.raise_for_status()
        body = response.json()
    data = body.get("data") if isinstance(body, dict) else body
    markdown = ""
    if isinstance(data, dict):
        markdown = str(data.get("markdown") or "")[:8000]
    return {"ok": True, "provider": "firecrawl", "url": url, "markdown": markdown}


def _firecrawl_search(query: str, limit: int) -> dict[str, Any]:
    key = _env("FIRECRAWL_API_KEY", "PEX_FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY missing")
    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            FIRECRAWL_SEARCH,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"query": query, "limit": limit, "sources": [{"type": "web"}]},
        )
        response.raise_for_status()
        body = response.json()
    rows = []
    data = body.get("data") if isinstance(body, dict) else None
    web = data.get("web") if isinstance(data, dict) else None
    items = (
        web
        if isinstance(web, list)
        else body.get("data")
        if isinstance(body.get("data"), list)
        else []
    )
    if isinstance(body, dict) and isinstance(body.get("web"), list):
        items = body["web"]
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "title": item.get("title") or item.get("metadata", {}).get("title"),
                "url": item.get("url") or item.get("metadata", {}).get("sourceURL"),
                "snippet": item.get("description") or item.get("markdown", "")[:400],
            }
        )
    return {"ok": True, "provider": "firecrawl", "query": query, "results": rows}


def _exa_search(query: str, limit: int) -> dict[str, Any]:
    key = _env("EXA_API_KEY", "PEX_EXA_API_KEY")
    if not key:
        raise RuntimeError("EXA_API_KEY missing")
    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            EXA_SEARCH,
            headers={"Content-Type": "application/json", "x-api-key": key},
            json={"query": query, "numResults": limit, "type": "auto", "contents": {"text": True}},
        )
        response.raise_for_status()
        body = response.json()
    rows = []
    for item in body.get("results") or []:
        rows.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": (item.get("text") or item.get("summary") or "")[:400],
            }
        )
    return {"ok": True, "provider": "exa", "query": query, "results": rows}


def _tavily_search(query: str, limit: int) -> dict[str, Any]:
    key = _env("TAVILY_API_KEY", "PEX_TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY missing")
    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            TAVILY_SEARCH,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"query": query, "max_results": limit, "search_depth": "basic"},
        )
        response.raise_for_status()
        body = response.json()
    rows = [
        {"title": item.get("title"), "url": item.get("url"), "snippet": item.get("content")}
        for item in body.get("results") or []
    ]
    return {"ok": True, "provider": "tavily", "query": query, "results": rows}


def _brave_search(query: str, limit: int) -> dict[str, Any]:
    key = _env("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY", "PEX_BRAVE_API_KEY")
    if not key:
        raise RuntimeError("BRAVE_API_KEY missing")
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            BRAVE_SEARCH,
            params={"q": query, "count": limit},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
        )
        response.raise_for_status()
        body = response.json()
    web = (body.get("web") or {}).get("results") or []
    rows = [
        {"title": item.get("title"), "url": item.get("url"), "snippet": item.get("description")}
        for item in web[:limit]
    ]
    return {"ok": True, "provider": "brave", "query": query, "results": rows}


def _serper_search(query: str, limit: int) -> dict[str, Any]:
    key = _env("SERPER_API_KEY", "PEX_SERPER_API_KEY")
    if not key:
        raise RuntimeError("SERPER_API_KEY missing")
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            SERPER_SEARCH,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": query, "num": limit},
        )
        response.raise_for_status()
        body = response.json()
    rows = [
        {"title": item.get("title"), "url": item.get("link"), "snippet": item.get("snippet")}
        for item in body.get("organic") or []
    ]
    return {"ok": True, "provider": "serper", "query": query, "results": rows}


def _duckduckgo_search(query: str, limit: int) -> dict[str, Any]:
    with httpx.Client(timeout=20.0) as client:
        response = client.get(
            DUCKDUCKGO,
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        response.raise_for_status()
        body = response.json()
    rows: list[dict[str, Any]] = []
    abstract = body.get("AbstractText")
    if abstract:
        rows.append(
            {"title": body.get("Heading"), "url": body.get("AbstractURL"), "snippet": abstract}
        )
    for topic in body.get("RelatedTopics") or []:
        if isinstance(topic, dict) and topic.get("FirstURL"):
            rows.append(
                {
                    "title": (topic.get("Text") or "")[:80],
                    "url": topic.get("FirstURL"),
                    "snippet": topic.get("Text"),
                }
            )
        if len(rows) >= limit:
            break
    return {
        "ok": bool(rows),
        "provider": "duckduckgo",
        "mode": "instant_answer",
        "query": query,
        "results": rows[:limit],
        **({} if rows else {"error": "DuckDuckGo returned no instant-answer results"}),
    }


def _blocked_oracle_text(value: str) -> str | None:
    lowered = value.replace("\\", "/").lower()
    return next((marker for marker in PRIVATE_ORACLE_MARKERS if marker in lowered), None)


def _blocked_public_url(url: str) -> str | None:
    marker = _blocked_oracle_text(url)
    if marker:
        return f"private benchmark marker blocked: {marker}"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "only public http(s) URLs may be scraped"
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        return "local URLs may not be scraped"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    if not address.is_global:
        return "private or non-global IP URLs may not be scraped"
    return None
