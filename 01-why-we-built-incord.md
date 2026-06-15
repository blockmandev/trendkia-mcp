# Why We Built Incord

**VISION · 8 min read · The Incord Team · May 2026**

AI agents are only as good as the data they can reach. You can give an agent the best reasoning model on the market, a clean prompt, and a well-designed tool layer—and it will still confidently tell a user that Bitcoin is at last week's price, that a company hasn't reported earnings it reported yesterday, or that a policy is in force that was repealed this morning. The model isn't broken. Its window onto the world is.

We built Incord because the standard way agents reach for live data is fundamentally broken, and because bolting another web-search wrapper onto the problem doesn't fix it—it just hides it behind a slightly faster spinner.

## The problem with chat-time search

Most agents fetch live information the same way. Mid-conversation, the agent calls a web-search API, the API crawls the open web, scrapes a handful of pages, and returns links or snippets. The model then reads through that material, extracts what it needs, and continues. It looks reasonable in a demo. In production, it breaks down in three predictable ways.

**It's slow where slow hurts most.** Every query pays a latency tax while the web is crawled and scraped in real time. A single fetch can take one to three seconds before the model even begins reasoning. That's survivable for a one-shot question. But modern agents don't ask once—they chain. An agent that makes a dozen retrieval calls in a single workflow inherits a dozen crawls' worth of latency, and a voice or trading agent that needs sub-second responses is dead on arrival.

**It returns noise, not signal.** Crawl results come back unranked and unstructured. The model receives pages of HTML-stripped text and has to read all of it to find one number. That's tokens spent, money spent, and a real chance the model anchors on the wrong paragraph. A search API has no concept of "the validated spot price of BTC." It has a concept of "here are ten pages that mention Bitcoin."

**It's often already stale.** For anything time-sensitive—a price, a breaking headline, a rate decision—the crawled page may itself be minutes or hours behind. You've paid the latency tax and the token tax to retrieve data that was old before you asked.

None of these are bugs you can patch with a better crawler or a faster proxy. They're inherent to fetching at chat time. The work is simply happening at the worst possible moment: while the user waits.

## A brain, not a search box

Incord changes the order of operations. Instead of fetching when your agent asks, it ingests the world *ahead* of time. News, market prices, and global events stream in continuously. Each item is embedded into a knowledge graph the moment it arrives and ranked by relevance and freshness. The expensive work—fetching, parsing, embedding, ranking, validating—happens before any query exists.

So when your agent needs context, it doesn't start a search. It makes a single `/v1/context` call and gets back the top-K most relevant, already-embedded facts in milliseconds. Each result carries a confidence score and did-you-mean hints, so the agent knows not just *what* came back but how much to trust it. No crawl. No scraping. No pile of pages to read. The retrieval is a vector lookup plus a rerank, and the answer is already shaped for an agent to act on.

Consider a concrete case. A trading assistant is asked, "What's the setup on Bitcoin right now?" Through a web-search API, that's a crawl, a scrape, several pages of articles of varying age, and a model left to reconstruct a current picture from secondary reporting. Through Incord, it's one call that returns the validated spot price across venues, the 24-hour move, the current RSI relative to its moving averages, and the high-impact macro event on today's calendar—each tagged with a source and a confidence score, ranked, in tens of milliseconds. One of those agents is guessing from articles. The other is reading the world.

## Real-time by default

The freshness isn't a feature you toggle on. It's the default state of the system. A continuous heartbeat loop pulls market data, news, and global events on cadences ranging from every five minutes to daily, across more than fifty source feeds and five asset classes. Every fetch is embedded in-process and written straight into the knowledge graph—no batch job, no nightly reindex, no manual refresh.

The result is a data layer that's never more than minutes behind reality. Your agent answers like it read the news this morning, because in a very real sense it did. And because that ingestion runs continuously across a distributed network rather than a single server, "always current" also means "always available"—but that's a story for another post.

## Why this matters now

Agents are moving from answering questions to taking actions. An agent that books, trades, buys, or files on a user's behalf can't be working from stale, unranked, unverified data. The cost of a wrong answer used to be an awkward correction. The cost of a wrong *action* is real. As agents take on more, the data layer underneath them stops being a convenience and becomes the foundation everything else rests on.

That's the layer we set out to build: real-time, ranked, validated world knowledge, served in a single call, so the agents you build act on the world as it is—not as it was when someone last crawled it.

Spin up a key and call `/v1/context` in minutes. The world is already ingested and waiting.
