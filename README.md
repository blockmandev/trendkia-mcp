# TrendKia MCP Server

**Version 1.1.0**

An MCP server that exposes [TrendKia](https://trendkia.com) — a bilingual Hindi/English
news site — to AI assistants (Claude Desktop, claude.ai custom connectors, Claude Code,
Cursor, etc.).

The site publishes a clean `.md` version of every article, so this server serves clean
text — no HTML scraping.

## Connect to the hosted server

A public, read-only instance is already running. Nothing to install:

```
https://trendkia.com/mcp
```

- **claude.ai** (Pro and above) — Settings → Connectors → *Add custom connector*, paste the URL.
- **Claude Code** — `claude mcp add --transport http trendkia https://trendkia.com/mcp`
- **Claude Desktop / Cursor** — add it as a remote HTTP MCP server in the client's config.

No API key or auth: it serves only content that is already public on the site.

## Tools

| Tool | What it returns |
|---|---|
| `search_articles` | Keyword search across the **whole archive**, Hindi **or** English. An English query finds Hindi articles and vice versa; results carry both titles and both category names. |
| `list_recent_articles` | The newest posts, from the RSS feed (~30 most recent). |
| `get_article` | Full clean markdown of one article. |
| `list_sitemap_urls` | URLs from `sitemap.xml`, following nested sitemap indexes. |

### Search vs. recent — the useful distinction

`search_articles` queries the site's own full-text index, so it reaches every published
article, not just the latest ones. `list_recent_articles` reads the RSS feed and is
therefore limited to roughly the last 30 posts by design — use it for "what's new",
and `search_articles` for anything else.

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

## Requirements

`mcp` is pinned below 2.0 on purpose: mcp 2.x renames `FastMCP` to `MCPServer` and changes
the decorator API, so an unpinned install fails at import. Moving to 2.x is a migration,
not a version bump.
