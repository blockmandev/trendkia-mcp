# TrendKia MCP Server

**Version 1.2.1**

An MCP server that exposes [TrendKia](https://trendkia.com) — a bilingual Hindi/English
news site — to AI assistants (Claude Desktop, claude.ai custom connectors, Claude Code,
Cursor, etc.).

The site publishes a clean `.md` version of every article, so this server serves clean
text — no HTML scraping.

## Connect to the hosted server

A public, read-only instance is already running. Nothing to install:

```
https://mcp.trendkia.com
```

- **claude.ai** (Pro and above) — Settings → Connectors → *Add custom connector*, paste the URL.
- **Claude Code** — `claude mcp add --transport http trendkia https://mcp.trendkia.com`
- **Claude Desktop / Cursor** — add it as a remote HTTP MCP server in the client's config.

`https://trendkia.com/mcp` remains live for anything already pointed at it.

No API key or auth: it serves only content that is already public on the site.

## Tools

| Tool | Arguments | What it returns |
|---|---|---|
| `search_articles` | `query, limit, lang` | Keyword search across the **whole archive**. An English query finds Hindi articles and vice versa. |
| `list_recent_articles` | `limit, lang` | The newest posts, from the RSS feed (~30 most recent). |
| `get_article` | `url, lang` | Full clean markdown of one article, in either language. |
| `list_sitemap_urls` | `limit, kind, offset` | Enumerate URLs. `kind="articles"` (default), `"ledger"`, or `"all"`; page with `offset`. |

### Languages

TrendKia publishes in **Hindi at the site root**, with an English edition under `/en`.
There is no `/hi` prefix — a bare path *is* the Hindi article:

```
https://trendkia.com/market/<slug>-<id>        Hindi
https://trendkia.com/en/market/<slug>-<id>     English
```

**The URL decides the language, and `lang` only overrides it.**

- `get_article(url)` returns the article *at that URL*, in the language that URL is in.
  A URL you pass is never silently swapped for another edition.
- `get_article(url, lang="en")` returns the **other** edition of the same article — the
  server rewrites the path, so you never edit a URL yourself.
- `search_articles` and `list_recent_articles` default to **Hindi**, the site's own language,
  and take the same `lang` to switch.

Every result carries `Language:` and `Alternate (…):`, so the other edition is one field away
in any single response — and the alternate is a clean canonical URL, never an echo of whatever
query string you passed in.

The search index is **shared, not per-locale** — one full-text index over Hindi *and* English
headlines, summaries and tags. So `lang` chooses which language the results come back in, not
which index is consulted. That is why an English query matches Hindi articles.

### Search vs. recent — the useful distinction

**To find an article, use `search_articles`.** It queries the site's full-text index and
reaches every published article, however old. `list_recent_articles` reads the RSS feed and
is limited to roughly the last 30 posts by design — it answers "what's new", nothing else.

`list_sitemap_urls` **enumerates** what exists; it is not a search tool. It defaults to
`kind="articles"` because the sitemap opens with ~6,900 bribe-ledger state and district
pages: before 1.3.0 the first 6,995 entries contained no article at all, so at the 1000-URL
ceiling every possible response was ledger pages and the archive looked unreachable through
it. Page through with `offset`.

Before 1.1.0 `search_articles` also read the feed, so a query for a common word returned
only a handful of same-day hits. If you are running an older copy, upgrade.

## Run it yourself

### Local (Claude Desktop, stdio)
```bash
pip install -r requirements.txt
python trendkia_mcp.py
```
Add to `claude_desktop_config.json`:
```json
{ "mcpServers": { "trendkia": { "command": "python", "args": ["/full/path/to/trendkia_mcp.py"] } } }
```

### Hosted (HTTP transport)
```bash
MCP_TRANSPORT=http PORT=8000 python trendkia_mcp.py
```
Serves `http://<host>:8000/mcp`. Put it behind a TLS reverse proxy and point clients at
the public URL. `Dockerfile` and `render.yaml` are included.

**Reverse-proxy gotcha:** FastMCP rejects a non-localhost `Host` header as DNS-rebinding
protection, so a proxy forwarding `Host: your-domain.com` gets `Invalid Host header` until
that host is allowed. Set it via the environment rather than patching the code.

## Config

| Variable | Default | Purpose |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` for local, `http` for a hosted connector |
| `PORT` | `8000` | HTTP port |
| `HOST` | `0.0.0.0` | HTTP bind address |
| `TRENDKIA_BASE_URL` | `https://trendkia.com` | Site to serve from |
| `TRENDKIA_DEFAULT_LANG` | `hi` | Last-resort language when neither `lang` nor the URL says |
| `MCP_ALLOWED_HOSTS` | `trendkia.com,127.0.0.1:*,…` | Hosts accepted behind a reverse proxy |
| `MCP_ALLOWED_ORIGINS` | `https://trendkia.com,https://claude.ai,…` | Allowed browser origins |

## Requirements

`mcp` is pinned below 2.0 on purpose: mcp 2.x renames `FastMCP` to `MCPServer` and changes
the decorator API, so an unpinned install fails at import. Moving to 2.x is a migration,
not a version bump.
