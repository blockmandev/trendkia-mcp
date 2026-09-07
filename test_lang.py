"""Does the lang layer actually work, against the live site?

The point of _to_lang is that a caller NEVER does URL string surgery, so the cases that matter are
the ones a model would get wrong by hand: a URL that already carries /en (must not get a second one),
a Hindi URL (must gain one), and a round-trip (must land back exactly where it started).
"""
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("tk", "trendkia_mcp.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

fails = []


def check(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


B = m.BASE_URL
HI = f"{B}/market/mexican-peso-slips-against-us-dollar-as-traders-brace-for-us-inflation-week-29291"
EN = f"{B}/en/market/mexican-peso-slips-against-us-dollar-as-traders-brace-for-us-inflation-week-29291"

print("1) _to_lang — the URL surgery callers must never do")
check(m._to_lang(HI, "en") == EN, "hi URL + lang=en -> /en form")
check(m._to_lang(EN, "hi") == HI, "en URL + lang=hi -> bare form")
check(m._to_lang(EN, "en") == EN, "en URL + lang=en is IDEMPOTENT (no /en/en/)")
check(m._to_lang(HI, "hi") == HI, "hi URL + lang=hi is unchanged")
check("/en/en/" not in m._to_lang(m._to_lang(HI, "en"), "en"), "applying en twice never doubles the prefix")
check(m._to_lang(m._to_lang(HI, "en"), "hi") == HI, "round-trip hi->en->hi returns the original exactly")
check(m._to_lang("", "en") == "", "empty URL is passed through, not turned into '/en'")

print("\n2) _norm_lang — a model that invents a value still gets a usable answer")
check(m._norm_lang("en") == "en" and m._norm_lang("hi") == "hi", "exact codes")
check(m._norm_lang("English") == "en" and m._norm_lang("hindi") == "hi", "full words, any case")
check(m._norm_lang(None) == "en", "None -> the en default")
check(m._norm_lang("klingon") == "en", "unknown -> the en default, not an exception")
check(m.DEFAULT_LANG == "en", "MCP default is en (the SITE's default is hi -- deliberately different)")

print("\n3) live: search returns the asked-for language + the alternate")
f = getattr(m.search_articles, "fn", m.search_articles)
en_out = f("cricket", 3, "en")
hi_out = f("cricket", 3, "hi")
check("lang=en" in en_out, "search header states lang=en")
check(en_out.count("- Alternate (hi):") >= 1, "each en result carries the hi alternate")
check(f"{B}/en/" in en_out, "en results link to /en/ URLs")
check(hi_out.count("- Alternate (en):") >= 1, "each hi result carries the en alternate")
check("/en/" not in hi_out.split("- Alternate")[0], "hi results link to bare URLs, not /en/")

print("\n4) live: get_article accepts EITHER URL and honours lang")
g = getattr(m.get_article, "fn", m.get_article)
a = g(HI, "en")          # Hindi URL in, English asked for -- the case the user cares about
check("Language: en" in a, "hi URL + lang=en -> English article, no caller-side rewriting")
check("/en/" in a.split("\n")[0], "it fetched the /en/ .md")
check("Alternate (hi):" in a, "response names the hi alternate")
b = g(EN, "hi")          # and the reverse
check("Language: hi" in b, "en URL + lang=hi -> Hindi article")
check("/en/" not in b.split("\n")[0], "it fetched the bare .md")

print()
if fails:
    print(f"RESULT: {len(fails)} FAILED")
    for x in fails:
        print("  - " + x)
    sys.exit(1)
print("RESULT: all checks passed")
