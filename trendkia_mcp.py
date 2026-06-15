#!/usr/bin/env python3
"""
TrendKia MCP server
===================
Exposes TrendKia (https://trendkia.com) content to any MCP-compatible AI
(Claude Desktop, Claude Code, Cursor, etc.) as a small set of tools.

The site is already AI-friendly: every article URL has a clean `.md`, `.txt`
and `.json` version. So this server fetches the `.md` version for article
content instead of scraping HTML.

Tools exposed:
  - list_recent_articles : newest posts from /feed.xml
  - search_articles      : keyword search over the feed (title + summary + category)
  - get_article          : clean markdown text of one article
  - list_sitemap_urls    : every URL from /sitemap.xml (handles sitemap indexes)

Run:  python trendkia_mcp.py
"""

import os
import time
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import feedparser
import httpx
from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
BASE_URL = os.environ.get("TRENDKIA_BASE_URL", "https://trendkia.com").rstrip("/")
FEED_URL = f"{BASE_URL}/feed.xml"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
USER_AGENT = "TrendKia-MCP/1.0 (+https://trendkia.com)"
TIMEOUT = 20.0
CACHE_TTL = 300  # seconds — avoid hammering the site

# Transport: "stdio" for local (Claude Desktop), "http" for a hosted web connector.
TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio").lower()
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))

mcp = FastMCP("trendkia", host=HOST, port=PORT)

_cache: dict[str, tuple[float, object]] = {}


def _http_get(url: str) -> httpx.Response:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as client:
        r = client.get(url)
        r.raise_for_status()
        return r


def _cached_feed():
    """Fetch + parse /feed.xml with a short TTL cache."""
    now = time.time()
    hit = _cache.get("feed")
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    raw = _http_get(FEED_URL).content
    parsed = feedparser.parse(raw)
    _cache["feed"] = (now, parsed)
    return parsed


def _md_url_for(article_url: str) -> str:
    """Turn an article URL into its clean markdown sibling (`...path.md`)."""
    u = article_url.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    for ext in (".md", ".txt", ".json", ".html"):
        if u.endswith(ext):
            u = u[: -len(ext)]
            break
    return u + ".md"


def _entry_to_dict(e) -> dict:
    return {
        "title": getattr(e, "title", "").strip(),
        "url": getattr(e, "link", "").strip(),
        "category": ", ".join(t.get("term", "") for t in getattr(e, "tags", []))
        if getattr(e, "tags", None)
        else getattr(e, "category", ""),
        "published": getattr(e, "published", ""),
        "summary": getattr(e, "summary", "").strip(),
    }


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_recent_articles(limit: int = 10) -> str:
    """List the most recent TrendKia articles (title, URL, category, date, summary).

    Args:
        limit: How many articles to return (1-50). Default 10.
    """
    limit = max(1, min(limit, 50))
    feed = _cached_feed()
    if not feed.entries:
        return "No articles found in the feed."

    out = [f"# Recent TrendKia articles (showing {min(limit, len(feed.entries))})\n"]
    for e in feed.entries[:limit]:
        d = _entry_to_dict(e)
        out.append(
            f"## {d['title']}\n"
            f"- URL: {d['url']}\n"
            f"- Category: {d['category'] or 'n/a'}\n"
            f"- Published: {d['published'] or 'n/a'}\n"
            f"- Summary: {d['summary'] or 'n/a'}\n"
        )
    return "\n".join(out)


@mcp.tool()
def search_articles(query: str, limit: int = 10) -> str:
    """Search recent TrendKia articles by keyword (matches title, summary, category).

    Note: this searches the feed (latest posts). For older content use
    list_sitemap_urls. Matching is case-insensitive and works for Hindi text too.

    Args:
        query: Keyword or phrase to look for.
        limit: Max results to return (1-50). Default 10.
    """
    q = query.strip().lower()
    if not q:
        return "Please provide a non-empty search query."
    limit = max(1, min(limit, 50))

    feed = _cached_feed()
    matches = []
    for e in feed.entries:
        d = _entry_to_dict(e)
        haystack = f"{d['title']} {d['summary']} {d['category']}".lower()
        if q in haystack:
            matches.append(d)
        if len(matches) >= limit:
            break

    if not matches:
        return f"No articles in the feed matched '{query}'."

    out = [f"# Search results for '{query}' ({len(matches)})\n"]
    for d in matches:
        out.append(
            f"## {d['title']}\n- URL: {d['url']}\n- Category: {d['category'] or 'n/a'}\n"
            f"- Published: {d['published'] or 'n/a'}\n- Summary: {d['summary'] or 'n/a'}\n"
        )
    return "\n".join(out)


@mcp.tool()
def get_article(url: str) -> str:
    """Fetch the full, clean text of one TrendKia article as markdown.

    Pass the normal article URL; the server automatically uses the site's clean
    `.md` version. Falls back to `.txt` if markdown is unavailable.

    Args:
        url: The article URL (e.g. https://trendkia.com/health/...-863).
    """
    if not url.strip():
        return "Please provide an article URL."
    if urlparse(url).netloc and urlparse(BASE_URL).netloc not in urlparse(url).netloc:
        return f"Refusing to fetch a URL outside {BASE_URL}."

    md_url = _md_url_for(url)
    for candidate in (md_url, md_url[:-3] + ".txt"):
        try:
            text = _http_get(candidate).text.strip()
            if text:
                return f"Source: {candidate}\n\n{text}"
        except httpx.HTTPError:
            continue
    return f"Could not fetch clean content for {url} (.md and .txt both failed)."


@mcp.tool()
def list_sitemap_urls(limit: int = 100) -> str:
    """List URLs from TrendKia's sitemap.xml (handles nested sitemap indexes).

    Args:
        limit: Max URLs to return (1-1000). Default 100.
    """
    limit = max(1, min(limit, 1000))

    def parse(xml_bytes: str):
        root = ET.fromstring(xml_bytes)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        tag = root.tag.split("}")[-1]
        urls, child_sitemaps = [], []
        if tag == "sitemapindex":
            for sm in root.findall("sm:sitemap", ns):
                loc = sm.findtext("sm:loc", default="", namespaces=ns).strip()
                if loc:
                    child_sitemaps.append(loc)
        else:  # urlset
            for u in root.findall("sm:url", ns):
                loc = u.findtext("sm:loc", default="", namespaces=ns).strip()
                lastmod = u.findtext("sm:lastmod", default="", namespaces=ns).strip()
                if loc:
                    urls.append((loc, lastmod))
        return urls, child_sitemaps

    try:
        urls, children = parse(_http_get(SITEMAP_URL).content)
    except (httpx.HTTPError, ET.ParseError) as exc:
        return f"Could not read sitemap: {exc}"

    # If it's an index, pull child sitemaps until we hit the limit.
    for child in children:
        if len(urls) >= limit:
            break
        try:
            more, _ = parse(_http_get(child).content)
            urls.extend(more)
        except (httpx.HTTPError, ET.ParseError):
            continue

    urls = urls[:limit]
    if not urls:
        return "No URLs found in the sitemap."

    out = [f"# Sitemap URLs (showing {len(urls)})\n"]
    for loc, lastmod in urls:
        out.append(f"- {loc}" + (f"  (lastmod: {lastmod})" if lastmod else ""))
    return "\n".join(out)


if __name__ == "__main__":
    if TRANSPORT in ("http", "streamable-http"):
        # Hosted web connector. Endpoint is served at /mcp on $PORT.
        mcp.run(transport="streamable-http")
    else:
        # Local Claude Desktop (stdio).
        mcp.run()
