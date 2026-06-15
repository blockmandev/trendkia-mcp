# TrendKia MCP Server

An MCP server that exposes [TrendKia](https://trendkia.com) content to AI assistants
(Claude Desktop, claude.ai custom connectors, Claude Code, Cursor, etc.).

The site publishes a clean `.md` version of every article, so this server serves
clean text — no HTML scraping.

## Tools
- `list_recent_articles` — newest posts from the RSS feed
- `search_articles` — keyword search over the feed (Hindi + English)
- `get_article` — full clean markdown of one article
- `list_sitemap_urls` — every URL from the sitemap

## Run locally (Claude Desktop, stdio)
```bash
pip install -r requirements.txt
python trendkia_mcp.py
```
Add to `claude_desktop_config.json`:
```json
{ "mcpServers": { "trendkia": { "command": "python", "args": ["/full/path/to/trendkia_mcp.py"] } } }
```

## Run as a remote web connector (claude.ai, Pro+)
```bash
MCP_TRANSPORT=http PORT=8000 python trendkia_mcp.py
```
Endpoint: `http://<host>:8000/mcp`. Deploy with the included `Dockerfile` /
`render.yaml`, then in claude.ai go to Connectors → Add custom connector and paste
`https://<your-host>/mcp`.

## Config
- `MCP_TRANSPORT` — `stdio` (default) or `http`
- `PORT` — HTTP port (default 8000)
- `TRENDKIA_BASE_URL` — override site (default https://trendkia.com)
