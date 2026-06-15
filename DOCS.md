# TrendKia Connector for Claude

Connect Claude to **[TrendKia](https://trendkia.com)** — trending news and viral
stories from India, published primarily in Hindi. Once connected, Claude can
browse, search, summarize, and cite TrendKia articles directly inside your
conversation.

This connector is **free, public, and read-only**. No account or login is
required, and it never changes anything on your device or on TrendKia.

---

## What you can do

Ask Claude things like:

- **"What's trending in India right now?"** — Claude lists the newest TrendKia stories.
- **"Find TrendKia's coverage on the Jalore blood donor and summarize it."** — Claude searches, opens the article, and gives you a cited summary.
- **"Summarize this article: https://trendkia.com/health/..."** — Claude reads the full article and distills it.
- **"जालौर के रक्तवीर के बारे में बताइए।"** — Search and answer in Hindi or English; Claude can also translate.

Every answer links back to the original article on trendkia.com so you can read more.

---

## How to connect (Claude.ai — Pro, Max, Team, or Enterprise)

1. In Claude, go to **Settings → Connectors**.
2. Click **Add custom connector**.
3. Enter:
   - **Name:** TrendKia
   - **URL:** `https://trendkia.com/mcp`
4. Click **Add**. No login or authentication is needed.
5. Start a new chat. In the message box, open the **+ menu** to enable TrendKia
   for the conversation, then ask one of the prompts above.

That's it — the connector's tools become available immediately.

---

## What the connector can do (tools)

| Tool | What it does |
| --- | --- |
| `list_recent_articles` | Returns the newest TrendKia articles (title, category, date, summary, link). |
| `search_articles` | Keyword search across recent articles — works in Hindi and English. |
| `get_article` | Fetches the full, clean text of a single article. |
| `list_sitemap_urls` | Lists URLs from the site map for broader browsing. |

All tools are **read-only**.

---

## Troubleshooting

**The connector won't connect / "failed to connect."**
Make sure the URL is exactly `https://trendkia.com/mcp` (with the `/mcp` path and
`https://`). Custom connectors require a Pro, Max, Team, or Enterprise plan.

**I don't see the tools in my chat.**
Open the **+ menu** in the message box and enable TrendKia for that conversation.
Connectors are enabled per-conversation.

**A search returns nothing.**
TrendKia may not cover that topic yet, or it may be older than the recent feed.
Try different keywords, or ask Claude to check the full site map.

**Visiting `https://trendkia.com/mcp` in a browser shows an error.**
That's expected. The endpoint only responds to MCP clients (like Claude), not to
a normal browser visit.

---

## Privacy & data

This connector is read-only and requires no login. It only fetches the specific
public TrendKia content you ask for and does not collect or store personal data.
See the full privacy policy at **https://trendkia.com/privacy**.

---

## Support

Questions, issues, or feedback? Contact us at **[email protected]**
(replace with your real support address) or open an issue on the
[GitHub repository](https://github.com/blockmandev/trendkia-mcp).
