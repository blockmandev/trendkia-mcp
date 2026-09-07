"""The calls that were actually broken in production.

The previous test only ever passed lang explicitly, both ways, so it passed while the DEFAULT call --
a bare Hindi URL with no lang -- returned English and made the Hindi edition unreachable. These are
the owner's reported failures, written as assertions.
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
g = getattr(m.get_article, "fn", m.get_article)

print("1) the URL decides — the caller's URL is never overridden")
check(m._lang_of_url(HI) == "hi", "a bare path is Hindi (there is no /hi prefix)")
check(m._lang_of_url(EN) == "en", "an /en path is English")
check(m._lang_of_url(f"{B}/") == "hi", "the site root is Hindi")

a = g(HI)                       # THE call that was broken: no lang at all
check("Language: hi" in a, "bare Hindi URL + NO lang -> Hindi (was English)")
check("/en/" not in a.split("\n")[0], "  and it fetched the bare .md, not /en/")
b = g(EN)
check("Language: en" in b, "/en/ URL + NO lang -> English")

print("\n2) lang still overrides, so the other edition stays reachable")
check("Language: en" in g(HI, "en"), "Hindi URL + lang=en -> English")
check("Language: hi" in g(EN, "hi"), "English URL + lang=hi -> Hindi")

print("\n3) the alternate link is a real URL, not an echo of the input")
q = g(f"{HI}?lang=hi&utm_source=x#frag")
alt = [l for l in q.split("\n") if l.startswith("Alternate")][0]
check("?" not in alt and "#" not in alt, f"query/fragment stripped from the alternate — got: {alt[:90]}")
check("/en/" in alt, "  and it points at the OTHER edition")
# The alternate must be followable: round-tripping it returns the edition it advertises.
alt_url = alt.split(": ", 1)[1].strip()
check("Language: en" in g(alt_url), "following Alternate(en) actually returns English — not a dead end")
back = g(alt_url)
alt2 = [l for l in back.split("\n") if l.startswith("Alternate")][0].split(": ", 1)[1].strip()
check(alt2 == m._clean(HI), f"and ITS alternate returns to the original Hindi URL exactly ({alt2[-40:]})")

print()
if fails:
    print(f"RESULT: {len(fails)} FAILED")
    for x in fails:
        print("  - " + x)
    sys.exit(1)
print("RESULT: all checks passed")
