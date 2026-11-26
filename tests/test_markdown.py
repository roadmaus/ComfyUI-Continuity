"""A model's reply is drawn from its markdown, and never as HTML.

    python3 tests/test_markdown.py

Reads `web/creator/markdown.js` under node: what the parser makes of the
markdown chat models write, and what the drawing makes of the tree, over the DOM
shim. No server, no browser.
"""

import layout
from domshim import DOM
from harness import check, passed

layout.skip_without_node()

SCRIPT = r'''
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const { parse, inline, markdown, safe } = await import("./web/creator/markdown.js");
const out = {};
const tags = (node) => node.tagName === "#text" ? JSON.stringify(node.textContent)
  : `${node.tagName.toLowerCase()}(${node.children.length ? node.children.map(tags).join(",") : JSON.stringify(node.textContent)})`;
const drawn = (text) => markdown(text).map(tags).join(" ");

out.emphasis = inline("**bold**, *em*, ***both***, ~~gone~~ and `code`");
out.underscores = inline("load lora_name_v2_final.safetensors, _quiet_ and snake_case_");
out.arithmetic = inline("2 * 3 * 4 and a * b");
out.unclosed = inline("**never closed and *this either");
out.escaped = inline("\\*not em\\* and \\`not code\\`");
out.ticks = inline("``a ` b`` and `x`");
out.links = inline("[site](https://example.com/a_(b)) [js](javascript:alert(1)) ![pic](https://example.com/p.png)");
out.bare = inline("see https://example.com/page. Or (https://example.com/x).");
out.breaks = inline("one\ntwo<br>three");
out.safe = ["https://a.b", "http://a.b", "javascript:alert(1)", "data:text/html,x", "/relative", "mailto:x@y"].map(safe);

out.blocks = parse([
  "## Shots", "Here is the plan:", "1. Wide", "2. Close", "   - on @mira", "", "3. Out",
  "", "> a quote", "carried on", "", "```py", "x = 1", "```",
  "| a | b |", "|:--|--:|", "| 1 | `p\\|q` |", "", "***", "- [x] done", "- [ ] not yet",
].join("\n"));
out.lonedash = parse("before\n-\nafter");
out.unclosedFence = parse("```\nstill code");
out.ordered = parse("3. three\n4. four");

// Drawn: tags and text only, so a <script> is its characters.
out.script = drawn("<script>alert(1)</script> <img src=x onerror=alert(1)>");
out.drawn = drawn("# T\n- **a** [l](https://e.com)\n\n```\n<b>x</b>\n```");
{
  const [p] = markdown("[l](https://e.com)");
  const a = p.children[0];
  out.anchor = [a.attrs.href, a.attrs.target, a.attrs.rel];
}
{
  const [list] = markdown("5. five\n6. six");
  out.start = list.attrs.start;
}
out.text = markdown("**Done** with `it`")[0].textContent;
console.log(JSON.stringify(out));
'''

with layout.pack(skip=["atlas"]) as target:
    out = layout.in_pack(DOM + SCRIPT, target)

S = lambda kind, *inner: {"type": kind, "inline": list(inner)}
check("emphasis, strike and code", out["emphasis"], [
    S("strong", "bold"), ", ", S("em", "em"), ", ", S("strong", S("em", "both")), ", ",
    {"type": "strike", "inline": ["gone"]}, " and ", {"type": "code", "text": "code"}])
check("an underscore inside a word is the word's", out["underscores"], [
    "load lora_name_v2_final.safetensors, ", S("em", "quiet"), " and snake_case_"])
check("a star with spaces round it is arithmetic", out["arithmetic"], ["2 * 3 * 4 and a * b"])
check("a run that closes nothing is its characters", out["unclosed"], ["**never closed and *this either"])
check("a backslash makes a mark a character", out["escaped"], ["*not em* and `not code`"])
check("a code span closes on a run as long as it opened with", out["ticks"], [
    {"type": "code", "text": "a ` b"}, " and ", {"type": "code", "text": "x"}])
check("only http(s) links are links; a picture is a link, never fetched", out["links"], [
    {"type": "link", "href": "https://example.com/a_(b)", "inline": ["site"]}, " ", "js", " ",
    {"type": "link", "href": "https://example.com/p.png", "inline": ["pic"]}])
check("a bare address leaves the sentence its punctuation", out["bare"], [
    "see ", {"type": "link", "href": "https://example.com/page", "inline": ["https://example.com/page"]},
    ". Or (", {"type": "link", "href": "https://example.com/x", "inline": ["https://example.com/x"]}, ")."])
check("a newline and a <br> break the line", out["breaks"], ["one", {"type": "break"}, "two", {"type": "break"}, "three"])
check("safe", out["safe"], [True, True, False, False, False, False])

P = lambda *inner: {"type": "paragraph", "inline": list(inner)}
item = lambda *blocks, check=None: {"check": check, "blocks": list(blocks)}
check("the blocks a model writes", out["blocks"], [
    {"type": "heading", "level": 2, "inline": ["Shots"]},
    P("Here is the plan:"),
    {"type": "list", "ordered": True, "start": 1, "items": [
        item(P("Wide")),
        item(P("Close"), {"type": "list", "ordered": False, "start": 1, "items": [item(P("on @mira"))]}),
        item(P("Out")),
    ]},
    {"type": "quote", "blocks": [P("a quote", {"type": "break"}, "carried on")]},
    {"type": "code", "lang": "py", "text": "x = 1"},
    {"type": "table", "align": ["left", "right"], "head": [["a"], ["b"]],
     "rows": [[["1"], [{"type": "code", "text": "p|q"}]]]},
    {"type": "rule"},
    {"type": "list", "ordered": False, "start": 1, "items": [
        item(P("done"), check=True), item(P("not yet"), check=False)]},
])
check("a lone dash is not an empty item", out["lonedash"], [P("before", {"type": "break"}, "-", {"type": "break"}, "after")])
check("a reply that stops inside a fence is code to the end", out["unclosedFence"], [
    {"type": "code", "lang": "", "text": "still code"}])
check("a numbered list keeps its first number", out["ordered"][0]["start"], 3)

check("markup in a reply is its characters", out["script"],
      'p("<script>alert(1)</script> <img src=x onerror=alert(1)>")')
check("drawn as elements", out["drawn"],
      'p("T") ul(li(strong("a")," ",a("l"))) pre(code("<b>x</b>"))')
check("a link opens apart and tells nobody where from", out["anchor"],
      ["https://e.com", "_blank", "noopener noreferrer"])
check("an ordered list's start", out["start"], "5")
check("the text of a drawn reply is what was said", out["text"], "Done with it")
passed("markdown is read and drawn")
