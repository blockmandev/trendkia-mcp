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
from mcp.types import ToolAnnotations
from mcp.server.transport_security import TransportSecuritySettings

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
# Server version, tagged in git as v<__version__>. NOTE: this is NOT what a client sees in the MCP
# initialize handshake — FastMCP 1.x takes no `version` argument, so the version reported there is the
# mcp library's own (1.27.2 in production). Keep the two straight when reading a client's logs.
__version__ = "1.1.1"

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

# FastMCP turns on DNS-rebinding protection when bound to localhost, and it accepts only a localhost
# Host header. Behind a reverse proxy that forwards `Host: trendkia.com` every request is therefore
# rejected with "Invalid Host header" — i.e. the hosted deployment cannot work without this.
#
# This lived ONLY on the production box from June until 2026-09-07, applied by hand and never
# committed, so the committed code could not actually run behind the proxy it was written for and a
# `git pull` on that box would have silently taken the public endpoint down. Keeping it in source is
# what makes the deployment reproducible.
ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    "MCP_ALLOWED_HOSTS", "trendkia.com,127.0.0.1:*,localhost:*,[::1]:*").split(",") if h.strip()]
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "MCP_ALLOWED_ORIGINS", "https://trendkia.com,https://claude.ai,https://claude.com").split(",") if o.strip()]
mcp = FastMCP("trendkia", host=HOST, port=PORT,
              transport_security=TransportSecuritySettings(
                  enable_dns_rebinding_protection=True,
                  allowed_hosts=ALLOWED_HOSTS,
                  allowed_origins=ALLOWED_ORIGINS))

_cache: dict[str, tuple[float, object]] = {}


def _http_get(url: str, params: dict | None = None) -> httpx.Response:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as client:
        # params is passed to httpx rather than interpolated into the URL so the query string is
        # encoded properly -- Hindi queries are non-ASCII and a raw f-string would produce an
        # invalid URL for exactly the searches this server exists to serve.
        r = client.get(url, params=params)
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
@mcp.tool(annotations=ToolAnnotations(title="List recent TrendKia articles", readOnlyHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(title="Search TrendKia articles", readOnlyHint=True, openWorldHint=True))
def search_articles(query: str, limit: int = 10) -> str:
    """Search the whole TrendKia archive by keyword, in Hindi OR English.

    Queries the site's own search index, so it reaches every published article rather
    than only the latest ones, and matches Hindi and English headlines, summaries and
    tags alike -- an English query finds Hindi articles and vice versa.

    Args:
        query: Keyword or phrase, Hindi or English.
        limit: Max results to return (1-50). Default 10.
    """
    q = query.strip()
    if not q:
        return "Please provide a non-empty search query."
    limit = max(1, min(limit, 50))

    # The site index, NOT the feed. The feed carries only the ~30 newest posts, so the old
    # feed-substring search answered "भारत" with 4 hits on an archive of ~29,000 articles and
    # could never see anything older than about a day. The index is bilingual and archive-wide.
    try:
        resp = _http_get(f"{BASE_URL}/api/search", params={"q": q, "limit": limit})
        results = (resp.json() or {}).get("results", [])
    except Exception as exc:
        # Say the search FAILED. Quietly falling back to the feed would answer an archive query
        # with a handful of today's headlines and look like a thin archive rather than a broken
        # lookup -- the caller cannot tell those apart, so it must be told.
        return f"Search is unavailable right now ({type(exc).__name__}). Try again shortly."

    if not results:
        return f"No TrendKia articles matched '{query}'."

    out = [f"# Search results for '{query}' ({len(results)})\n"]
    for r in results:
        url = r.get("href") or ""
        if url.startswith("/"):
            url = f"{BASE_URL}{url}"
        title = r.get("title") or r.get("titleEn") or "(untitled)"
        line = f"## {title}\n- URL: {url}\n"
        # Both titles when they differ, so an English-speaking caller can read a Hindi headline.
        if r.get("titleEn") and r.get("titleEn") != title:
            line += f"- Title (EN): {r['titleEn']}\n"
        cat = r.get("cat") or ""
        cat_en = r.get("catEn") or ""
        if cat or cat_en:
            line += f"- Category: {cat}{f' / {cat_en}' if cat_en and cat_en != cat else ''}\n"
        out.append(line)
    return "\n".join(out)


@mcp.tool(annotations=ToolAnnotations(title="Get TrendKia article content", readOnlyHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(title="List TrendKia sitemap URLs", readOnlyHint=True, openWorldHint=True))
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
