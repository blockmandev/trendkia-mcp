"""Format control, and the alternate-URL echo the owner reported with .txt/.json inputs."""
import importlib.util
import json
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
SLUG = "market/mexican-peso-slips-against-us-dollar-as-traders-brace-for-us-inflation-week-29291"
HI = f"{B}/{SLUG}"
g = getattr(m.get_article, "fn", m.get_article)

print("1) _clean canonicalises whatever the caller passed")
for suffix in (".md", ".txt", ".json", ".html", "?lang=hi", "#frag", "/", "?a=1&b=2#x"):
    check(m._clean(HI + suffix) == HI, f"strips {suffix!r}")

print("\n2) the alternate link never echoes the input (the reported bug)")
for suffix in (".txt", ".json", "?lang=hi"):
    out = g(HI + suffix)
    alt = [l for l in out.split("\n") if l.startswith("Alternate")]
    check(bool(alt), f"input {suffix!r}: an alternate line exists")
    if alt:
        a = alt[0].split(": ", 1)[1].strip()
        check(a == f"{B}/en/{SLUG}", f"  input {suffix!r} -> clean alternate (got …{a[-34:]})")

print("\n3) fmt selects the representation")
md = g(HI)
check(md.split("\n")[0].endswith(".md"), "fmt omitted -> markdown (default unchanged)")
js = g(HI, fmt="json")
check(not js.startswith("Source:"), "fmt=json returns JSON, not a prose header")
try:
    doc = json.loads(js)
    check(True, "fmt=json parses as JSON")
    check(isinstance(doc.get("tags"), list) or doc.get("tags") is None,
          f"tags is a real list, not a comma string (got {type(doc.get('tags')).__name__})")
    for f in ("title", "content", "url", "language", "alternateUrl", "alternateLanguage"):
        check(f in doc, f"  json has {f}")
    check(doc["language"] == "hi", "json language follows the URL (Hindi root)")
    check(doc["alternateUrl"] == f"{B}/en/{SLUG}", "json alternateUrl is the clean /en form")
except ValueError as e:
    check(False, f"fmt=json parses as JSON — {e}")

print("\n4) fmt still respects lang")
je = json.loads(g(HI, lang="en", fmt="json"))
check(je["language"] == "en", "lang=en + fmt=json -> English JSON")
check(je["alternateUrl"] == HI, "  and its alternate points back at the Hindi URL")

print()
if fails:
    print(f"RESULT: {len(fails)} FAILED")
    for x in fails:
        print("  - " + x)
    sys.exit(1)
print("RESULT: all checks passed")
