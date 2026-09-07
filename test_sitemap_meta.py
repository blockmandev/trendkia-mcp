"""The archive-reachability and field-consistency faults reported from real connector use."""
import importlib.util
import re
import sys

spec = importlib.util.spec_from_file_location("tk", "trendkia_mcp.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


sm = getattr(m.list_sitemap_urls, "fn", m.list_sitemap_urls)
lst = getattr(m.list_recent_articles, "fn", m.list_recent_articles)
srch = getattr(m.search_articles, "fn", m.search_articles)
ART = re.compile(r"-\d{4,}\s*$")

print("1) the sitemap can reach ARTICLES (it could not: 999/1000 were ledger pages)")
out = sm(20)
urls = [l[2:].split("  (")[0].strip() for l in out.split("\n") if l.startswith("- ")]
check(len(urls) > 0, f"default kind returns URLs (got {len(urls)})")
check(all("/bribe-ledger" not in u for u in urls), "NOT one bribe-ledger page in the default listing")
check(sum(1 for u in urls if ART.search(u)) >= len(urls) // 2, "the listing is article URLs")

print("\n2) paging works, so the archive is walkable")
p1 = [l for l in sm(5, offset=0).split("\n") if l.startswith("- ")]
p2 = [l for l in sm(5, offset=5).split("\n") if l.startswith("- ")]
check(len(p1) == 5 and len(p2) == 5, "two pages of 5 both fill")
check(not set(p1) & set(p2), "offset actually advances -- pages do not overlap")
check("offset=" in sm(5), "the response tells the caller how to get the next page")

print("\n3) the ledger is still reachable, just opt-in")
led = [l for l in sm(5, kind="ledger").split("\n") if l.startswith("- ")]
check(len(led) == 5 and all("/bribe-ledger" in l for l in led), "kind='ledger' returns ledger pages")
allk = sm(5, kind="all")
check("kind=all" in allk, "kind='all' still lists everything in sitemap order")

print("\n4) category means the same thing in both tools")
one = lst(1)
cat_line = [l for l in one.split("\n") if l.startswith("- Category:")][0]
cat = cat_line.split(": ", 1)[1].strip()
check("," not in cat, f"list category is a SINGLE category, not a joined tag list (got {cat!r})")
check("finance" != cat.lower(), "and not the stray English slug")
check(any(l.startswith("- Tags:") for l in one.split("\n")), "tags are their own field")

s_cat = [l for l in srch("cricket", 1).split("\n") if l.startswith("- Category:")]
if s_cat:
    check("," not in s_cat[0].split(": ", 1)[1], "search category is single too -- the two tools agree in shape")

print("\n5) summaries carry no social hashtags")
summ = [l for l in lst(5).split("\n") if l.startswith("- Summary:")]
check(bool(summ), "summaries present")
check(not any(re.search(r"#\S+\s*$", s) for s in summ),
      "no trailing #hashtag runs (they are social furniture, noise to an API consumer)")

print()
if fails:
    print(f"RESULT: {len(fails)} FAILED")
    for x in fails:
        print("  - " + x)
    sys.exit(1)
print("RESULT: all checks passed")
