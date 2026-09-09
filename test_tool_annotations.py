"""Regression test for required MCP tool safety metadata."""
import ast
import sys
from pathlib import Path

EXPECTED = {
    "list_recent_articles": False,
    "search_articles": False,
    "get_article": False,
    "list_sitemap_urls": False,
}

tree = ast.parse(Path("trendkia_mcp.py").read_text(encoding="utf-8"))
failures = []

for node in tree.body:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in EXPECTED:
        continue
    tool = next(
        (decorator for decorator in node.decorator_list
         if isinstance(decorator, ast.Call)
         and isinstance(decorator.func, ast.Attribute)
         and decorator.func.attr == "tool"),
        None,
    )
    annotations = next((kw.value for kw in tool.keywords if kw.arg == "annotations"), None) if tool else None
    fields = {
        kw.arg: kw.value.value
        for kw in annotations.keywords
        if kw.arg is not None and isinstance(kw.value, ast.Constant)
    } if isinstance(annotations, ast.Call) else {}
    for field in ("readOnlyHint", "openWorldHint", "destructiveHint"):
        if field not in fields:
            failures.append(f"{node.name}: missing {field}")
    if fields.get("destructiveHint") is not EXPECTED[node.name]:
        failures.append(f"{node.name}: destructiveHint must be False")

missing = set(EXPECTED) - {
    node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}
failures.extend(f"missing tool {name}" for name in sorted(missing))

if failures:
    print("FAIL")
    print("\n".join(f"- {failure}" for failure in failures))
    sys.exit(1)
print("PASS: all tool safety annotations are explicit and correct")
