"""Python-rendered public console: real forms, real results, no client build."""
from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import urlencode


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_console(query: str, k: int, status: dict[str, Any],
                   bundle: dict[str, Any] | None = None, error: str | None = None) -> str:
    components = status["components"]
    cards = "".join(
        f'<article class="metric"><span>{_e(name.title())}</span>'
        f'<strong>{"Ready" if part["ready"] else "Unavailable"}</strong>'
        f'<small>{_e(part.get("chunk_count", part.get("candidate_count", part.get("pattern_count", "—"))))} records</small></article>'
        for name, part in components.items()
    )
    results = '<p class="empty">Search the public corpus and review candidates to inspect their evidence.</p>'
    if error:
        results = f'<p role="alert" class="error">Request unavailable: {_e(error)}</p>'
    elif bundle:
        retrieval, plan, frontier = bundle["retrieve"], bundle["plan"], bundle["frontier"]
        evidence = {row["node_id"]: row for row in retrieval["evidence"]}
        cited = set(plan["citedNodeIds"])
        rows = "".join(
            '<article class="result">'
            f'<span class="tag">{"Cited by planner" if h["nodeId"] in cited else "Retrieved"}</span>'
            f'<h3>{_e(h["note"])}</h3><p>{_e(evidence[h["nodeId"]]["source"])}</p>'
            f'<code>{_e(h["nodeId"])}</code><details><summary>Content digest</summary>'
            f'<code>{_e(evidence[h["nodeId"]]["sha256"])}</code></details></article>'
            for h in retrieval["handles"]
        ) or '<p class="empty">No corpus handles found. The planner abstains.</p>'
        review = "".join(
            '<article class="result">'
            f'<span class="tag review">Review required · {_e(h["kind"])}</span>'
            f'<h3>{_e(h["title"])}</h3><p>{_e(h["repository"])}</p>'
            f'<code>{_e(h["nodeId"])}</code><details><summary>Source revision and digest</summary>'
            f'<p>{_e(h["path"])}</p><code>{_e(h["revision"])}</code>'
            f'<code>{_e(h["sha256"])}</code></details></article>'
            for h in frontier["handles"]
        ) or f'<p class="empty">{_e(frontier["state"])} · no review handles returned.</p>'
        api_url = "/api/v1/query?" + urlencode({"q": query, "k": k})
        results = (
            f'<section class="outcome" aria-live="polite"><strong>{_e(plan["decision"])}</strong>'
            f'<span>{_e(bundle["state"])}</span><span>{_e(retrieval["ranking_receipt"]["mode"])}</span></section>'
            '<div class="columns"><section><h2>Corpus evidence</h2>' + rows + '</section>'
            '<section><h2>Research &amp; formula review</h2>' + review + '</section></div>'
            '<section class="receipt"><h2>Evidence receipt</h2>'
            '<p>Content digests bind this result to its retrieval and plan. This receipt is unsigned.</p>'
            f'<code>{_e(bundle["receipt"]["sha256"])}</code>'
            '<details><summary>Inspect this result as JSON</summary>'
            f'<pre>{_e(json.dumps(bundle, indent=2, ensure_ascii=False))}</pre></details>'
            f'<a href="{_e(api_url)}">Run the same query through the JSON API</a></section>'
        )
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Second Brain · Evidence console</title><style>
:root{color-scheme:dark;--bg:#081116;--panel:#102028;--line:#27404b;--ink:#e8f1ef;--muted:#a1b7bd;--mint:#8fe2bd}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,sans-serif}
a{color:var(--mint)}header,main,footer{max-width:1160px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line)}nav{display:flex;gap:20px;flex-wrap:wrap}.brand{font-weight:750;letter-spacing:.06em}h1{font-size:clamp(34px,5vw,58px);line-height:1.1;letter-spacing:-.04em;margin:20px 0}h2{font-size:21px}h3{font-size:17px;margin:10px 0}p{color:var(--muted)}.eyebrow{color:var(--mint);font-size:12px;letter-spacing:.14em;text-transform:uppercase}.lead{max-width:730px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:28px 0}.metric,.search,.result,.receipt{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px}.metric span,.metric small{display:block;color:var(--muted)}.metric strong{display:block;font-size:24px;margin:8px 0}.search{display:grid;grid-template-columns:1fr 90px auto;gap:14px;align-items:end}label{display:block;font-size:13px;color:var(--muted)}input,select,button{font:inherit;border-radius:7px;padding:12px;width:100%;border:1px solid #42616c;background:#08151b;color:var(--ink)}button{background:var(--mint);color:#0b2019;font-weight:700;cursor:pointer}input:focus,select:focus,button:focus,a:focus,summary:focus{outline:2px solid var(--mint);outline-offset:3px}.outcome{display:flex;gap:16px;flex-wrap:wrap;padding:24px 0}.outcome strong{color:var(--mint)}.outcome span,.tag{font-size:12px;color:var(--muted)}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}.result{margin:14px 0}.tag{color:var(--mint)}.review{color:#e1c582}code{display:block;overflow-wrap:anywhere;font:12px/1.7 ui-monospace,monospace;color:#b8cbd3}summary{cursor:pointer;margin:12px 0;color:var(--mint)}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere}.receipt{margin-top:24px}.empty{padding:24px 0}.error{color:#ffb6ae}footer{font-size:13px;color:var(--muted)}@media(max-width:680px){header{display:block}nav{margin-top:12px}.metrics{grid-template-columns:1fr}.search,.columns{grid-template-columns:1fr}.search button{margin-top:6px}main{padding:18px}}
</style></head><body><header><div class="brand">SZL / SECOND BRAIN</div><nav>
<a href="/">Console</a><a href="/hologram">Hologram</a><a href="/api/v1/retrieval-capabilities">Capabilities</a><a href="/readyz">Readiness</a>
</nav></header><main><div class="eyebrow">Public evidence workspace</div><h1>Follow the evidence.</h1>
<p class="lead">Search governed memory, trace source digests, and inspect research and formula candidates. The software planner proposes citations; review candidates carry no execution authority.</p>
<div class="metrics">''' + cards + '''</div><form class="search" action="/" method="get">
<div><label for="q">Search query</label><input id="q" name="q" maxlength="2000" placeholder="Formula authority, Khipu, retrieval…" value="''' + _e(query) + '''"></div>
<div><label for="k">Results</label><select id="k" name="k">''' + "".join(f'<option value="{n}"{" selected" if n == k else ""}>{n}</option>' for n in range(1,13)) + '''</select></div>
<button type="submit">Search evidence</button></form><p>Ranking measures relevance. It is not a correctness probability or a mathematical proof.</p>''' + results + '''</main><footer>Python frontend and backend · Public handles only · Dense retrieval and model generation are not configured.</footer></body></html>'''
