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

import json
import os
import time
from urllib.parse import urlparse, urlunparse
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
__version__ = "1.2.1"

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


# --------------------------------------------------------------------------- #
# Language
# --------------------------------------------------------------------------- #
# The site publishes every article twice: Hindi at /<section>/<slug>-<id> and English under an /en
# prefix. DEFAULT_LANG is "en" here because the callers are AI assistants, which overwhelmingly work
# in English -- note this differs from the WEBSITE's own default of Hindi, and the two are set
# independently on purpose.
DEFAULT_LANG = os.environ.get("TRENDKIA_DEFAULT_LANG", "hi").strip().lower()


def _norm_lang(lang: str | None, fallback: str = "hi") -> str:
    """Caller input -> 'hi' or 'en'. Unrecognised input uses `fallback` rather than raising."""
    v = (lang or "").strip().lower()
    if v in ("hi", "hindi"):
        return "hi"
    if v in ("en", "english"):
        return "en"
    return fallback if fallback in ("hi", "en") else "hi"


def _lang_of_url(url: str) -> str:
    """The language a URL is ALREADY in. There is no /hi prefix: the site root is Hindi and /en is
    the only locale prefix, so the path alone says which language a URL points at."""
    path = urlparse(url or "").path
    return "en" if path == "/en" or path.startswith("/en/") else "hi"


_REPR_EXT = (".md", ".txt", ".json", ".html")


def _clean(url: str) -> str:
    """The canonical article address behind whatever the caller passed.

    Strips the query, the fragment AND any representation extension, because every URL this server
    EMITS is an article address rather than an echo. Building an alternate link by keeping the
    caller's input intact is what produced `...-29263?lang=hi` and `...-29263.txt` in the Alternate
    line: links that point at nothing, and that imply the tool honours a parameter or format it does
    not. Canonicalise first, then rewrite the locale -- never the other way round.
    """
    if not url:
        return url
    parts = urlparse(url)
    path = parts.path.rstrip("/") or parts.path
    for ext in _REPR_EXT:
        if path.endswith(ext):
            path = path[: -len(ext)]
            break
    return urlunparse(parts._replace(path=path, query="", fragment=""))


def _to_lang(url: str, lang: str, keep_query: bool = False) -> str:
    """Return this article's URL in `lang`, accepting a URL in EITHER language.

    Callers must never have to add or strip the /en prefix themselves. Doing that with string
    manipulation is where it eventually goes wrong -- a slug containing "/en" mid-path, a trailing
    slash, a URL that already carries the prefix and gets a second one -- and the caller is the layer
    least able to notice. So the rewrite lives here, keyed on the path, once.
    """
    if not url:
        return url
    parts = urlparse(url)
    path = parts.path
    if path.startswith("/en/") or path == "/en":
        path = path[3:] or "/"          # strip -> the Hindi form IS the bare path (no /hi prefix)
    if lang == "en":
        path = "/en" + (path if path.startswith("/") else "/" + path)
    if not keep_query:
        parts = parts._replace(query="", fragment="")
    return urlunparse(parts._replace(path=path))


def _other_lang(lang: str) -> str:
    return "hi" if lang == "en" else "en"


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
def list_recent_articles(limit: int = 10, lang: str = "") -> str:
    """List the most recent TrendKia articles (title, URL, category, date, summary).

    Covers roughly the last 30 posts (the RSS feed). For anything older use search_articles,
    which reaches the whole archive.

    Args:
        limit: How many articles to return (1-50). Default 10.
        lang: Optional "en" or "hi" -- set this to match the language the user is writing
              in. The feed is Hindi (the site root); /en is the English edition. Each item
              also carries the other edition's URL.
    """
    limit = max(1, min(limit, 50))
    lang = _norm_lang(lang, fallback="hi")
    feed = _cached_feed()
    if not feed.entries:
        return "No articles found in the feed."

    out = [f"# Recent TrendKia articles (showing {min(limit, len(feed.entries))}, lang={lang})\n"]
    for e in feed.entries[:limit]:
        d = _entry_to_dict(e)
        # The feed itself is published in Hindi; the title stays as the feed gives it, but the URL is
        # rewritten so a caller working in English lands on the English page. Saying so explicitly
        # beats a URL whose language silently disagrees with the headline beside it.
        url = _to_lang(d["url"], lang)
        out.append(
            f"## {d['title']}\n"
            f"- URL: {url}\n"
            f"- Category: {d['category'] or 'n/a'}\n"
            f"- Published: {d['published'] or 'n/a'}\n"
            f"- Summary: {d['summary'] or 'n/a'}\n"
            f"- Language: {lang}\n"
            f"- Alternate ({_other_lang(lang)}): {_clean(_to_lang(d['url'], _other_lang(lang)))}\n"
        )
    return "\n".join(out)


@mcp.tool(annotations=ToolAnnotations(title="Search TrendKia articles", readOnlyHint=True, openWorldHint=True))
def search_articles(query: str, limit: int = 10, lang: str = "") -> str:
    """Search the whole TrendKia archive by keyword, in Hindi OR English.

    Queries the site's own search index, so it reaches every published article rather
    than only the latest ones. The index is bilingual and SHARED, not one index per
    language: an English query matches Hindi articles and vice versa. `lang` therefore
    selects which language the RESULTS come back in, not which index is consulted.

    Args:
        query: Keyword or phrase, Hindi or English.
        limit: Max results to return (1-50). Default 10.
        lang: Optional "en" or "hi" -- set this to match the language the user is writing
              in. The site publishes in Hindi at the root with an English edition under
              /en, and results default to Hindi. Every result also carries the other
              edition's URL, so you never rewrite a URL yourself.
    """
    q = query.strip()
    if not q:
        return "Please provide a non-empty search query."
    limit = max(1, min(limit, 50))
    # The site's own language is Hindi; /en is the alternate edition. Results follow that unless the
    # caller asks otherwise.
    lang = _norm_lang(lang, fallback="hi")

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

    out = [f"# Search results for '{query}' ({len(results)}, lang={lang})\n"]
    for r in results:
        href = r.get("href") or ""
        if href.startswith("/"):
            href = f"{BASE_URL}{href}"
        url = _to_lang(href, lang)
        # The English title when the caller asked for English and the site has one; the Hindi
        # headline is the fallback, because a missing translation must not produce a blank result.
        hi_t, en_t = r.get("title") or "", r.get("titleEn") or ""
        title = (en_t or hi_t) if lang == "en" else (hi_t or en_t)
        line = f"## {title or '(untitled)'}\n- URL: {url}\n"
        other = (hi_t if lang == "en" else en_t)
        if other and other != title:
            line += f"- Title ({_other_lang(lang)}): {other}\n"
        hi_c, en_c = r.get("cat") or "", r.get("catEn") or ""
        cat = (en_c or hi_c) if lang == "en" else (hi_c or en_c)
        if cat:
            line += f"- Category: {cat}\n"
        # lang + alternate_url on EVERY item, so the capability is visible from one response and a
        # caller never has to read the tool description -- or guess -- to find the other language.
        line += f"- Language: {lang}\n- Alternate ({_other_lang(lang)}): {_clean(_to_lang(href, _other_lang(lang)))}\n"
        out.append(line)
    return "\n".join(out)


@mcp.tool(annotations=ToolAnnotations(title="Get TrendKia article content", readOnlyHint=True, openWorldHint=True))
def get_article(url: str, lang: str = "", fmt: str = "md") -> str:
    """Fetch one TrendKia article as clean markdown, or as structured JSON.

    The URL decides the language: the site root is Hindi and `/en/...` is the English
    edition. Pass a URL and you get that article in that language -- the URL you hand
    over is never overridden. Set `lang` only when you want the OTHER edition of the
    same article, e.g. pass a Hindi URL with lang="en" to read it in English; the server
    rewrites the path for you.

    Args:
        url: The article URL. A bare path is Hindi, an /en/ path is English. Any
             .md/.txt/.json suffix or query string on it is ignored.
        lang: Optional "en" or "hi". Omit it to follow the URL. Set it to match the
              language the user is writing in when that differs from the URL you have.
        fmt: "md" (default) for readable markdown, or "json" for the same article as
             structured fields -- title, summary, content, category, publishedAt, tags
             as a real list, language, canonical url. Use "json" when you need to read
             specific fields rather than prose.
    """
    if not url.strip():
        return "Please provide an article URL."
    if urlparse(url).netloc and urlparse(BASE_URL).netloc not in urlparse(url).netloc:
        return f"Refusing to fetch a URL outside {BASE_URL}."

    # The URL's own language is the default, so omitting `lang` returns exactly what was asked for.
    # A server-side default that overrode it made the Hindi edition unreachable for any client whose
    # cached tool schema had no `lang` field to send -- a default that cannot be overridden is not a
    # default, it is a redirect.
    lang = _norm_lang(lang, fallback=_lang_of_url(url))
    # Canonicalise BEFORE rewriting the locale, so a caller's .txt/.json/?query never survives into
    # the URL we fetch or the alternate we publish.
    page_url = _to_lang(_clean(url), lang)
    ext = ".json" if (fmt or "").strip().lower() == "json" else ".md"
    # .txt is a genuine fallback for the markdown path, not a format the caller selects: it exists so
    # a missing .md still returns text. It is not offered for json, where a text body would not parse.
    candidates = [page_url + ext] if ext == ".json" else [page_url + ".md", page_url + ".txt"]
    for candidate in candidates:
        try:
            text = _http_get(candidate).text.strip()
            if text:
                # The header states the language and the other language's page URL, so a caller that
                # asked for the wrong one can correct it from this response alone rather than
                # rebuilding a URL by hand.
                alt = _to_lang(_clean(url), _other_lang(lang))
                if ext == ".json":
                    # Return the site's JSON verbatim so the caller parses real fields, and carry the
                    # locale metadata in a wrapper rather than prepending prose that would break
                    # json.loads on the whole response.
                    try:
                        doc = json.loads(text)
                    except ValueError:
                        return f"The article JSON at {candidate} could not be parsed."
                    doc["language"] = lang
                    doc["alternateUrl"] = alt
                    doc["alternateLanguage"] = _other_lang(lang)
                    return json.dumps(doc, ensure_ascii=False, indent=2)
                return (
                    f"Source: {candidate}\n"
                    f"Language: {lang}\n"
                    f"Alternate ({_other_lang(lang)}): {alt}\n\n"
                    f"{text}"
                )
        except httpx.HTTPError:
            continue
    # Name the URL actually fetched, not the one passed in: after canonicalising and rewriting the
    # locale they differ, and reporting the caller's URL blames one that was never requested.
    return f"Could not fetch {page_url + ext}."


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
