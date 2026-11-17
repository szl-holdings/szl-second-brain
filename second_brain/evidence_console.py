"""Server-rendered inspector over the exact evidence-graph API payload."""
from __future__ import annotations

import html
import json
from urllib.parse import urlencode


def _e(value):
    return html.escape(str(value), quote=True)


def render_evidence(query, k, snapshot=None, error=None):
    content = '<p role="alert">Evidence is unavailable. No sample result has been substituted.</p>'
    if snapshot is not None:
        groups = []
        for kind, heading in (("CORPUS_HANDLE", "Retrieved evidence"), ("REVIEW_CANDIDATE", "Research candidates"),
                              ("LUTAR_REFERENCE", "Lutar source references"), ("CITATION_PLAN", "Software proposal"),
                              ("VIEW_RECEIPT", "View binding")):
            cards = []
            for node in snapshot["nodes"]:
                if node["kind"] != kind:
                    continue
                index = node["ordinal"]
                links = [f'{edge["relation"]} → #{edge["target"]}' for edge in snapshot["edges"] if edge["source"] == index]
                cards.append(
                    f'<details class="node" id="node-{index}" data-node-id="{_e(node["node_id"])}">'
                    f'<summary><span class="number">{index:02d}</span><span>{_e(node["title"])}</span></summary>'
                    f'<p class="grade">{_e(node["evidence_level"])}</p>'
                    f'<dl><dt>Source</dt><dd>{_e(node["source"] or "This local transaction")}</dd>'
                    f'<dt>Revision / identity</dt><dd>{_e(node["revision"] or "Bound below")}</dd>'
                    f'<dt>Revision kind</dt><dd>{_e(node["revision_kind"])}</dd>'
                    f'<dt>SHA-256</dt><dd><code>{_e(node["sha256"])}</code></dd>'
                    f'<dt>Execution authority</dt><dd>NONE</dd></dl>'
                    f'<p>{_e("; ".join(links) or "No outgoing dependency")}</p></details>')
            groups.append(f'<section class="lane"><h2>{_e(heading)} <span>{len(cards)}</span></h2>'
                          + ("".join(cards) or '<p class="empty">No observed handles in this category.</p>') + '</section>')
        health = "".join(f'<div><span>{_e(name)}</span><strong>{_e(part["state"])}</strong></div>'
                         for name, part in snapshot["components"].items())
        edges = "".join(f'<tr><td><a href="#node-{e["source"]}">#{e["source"]}</a></td>'
                        f'<td>{_e(e["relation"])}</td><td><a href="#node-{e["target"]}">#{e["target"]}</a></td></tr>'
                        for e in snapshot["edges"])
        api = "/api/v1/evidence-graph?" + urlencode({"q": query, "k": k})
        content = (f'<section class="status" aria-label="Component observations">{health}</section>'
                   f'<p id="view-state"><strong>{_e(snapshot["state"])}</strong> · '
                   f'{snapshot["node_count"]} objects · {snapshot["edge_count"]} typed links · '
                   'No external provider requests</p>'
                   '<div class="lanes">' + "".join(groups) + '</div>'
                   '<section class="binding"><h2>Inspect the binding</h2>'
                   '<p>This digest binds the complete view. It is unsigned; it is not a proof of source truth or permission to act.</p>'
                   f'<code id="snapshot-digest">{_e(snapshot["content_sha256"])}</code>'
                   '<details><summary>Typed dependency links</summary><table><thead><tr>'
                   '<th>From</th><th>Relation</th><th>To</th></tr></thead><tbody>' + edges + '</tbody></table></details>'
                   '<details><summary>Exact graph payload</summary><pre id="graph-json">'
                   + _e(json.dumps(snapshot, ensure_ascii=False, indent=2)) + '</pre></details>'
                   f'<a id="graph-api" href="{_e(api)}">Read the same graph contract as JSON</a></section>')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SZL · Evidence graph</title>
<style>
:root{color-scheme:dark;--bg:#091218;--panel:#10232d;--line:#2c4654;--ink:#e9f2f4;--muted:#b4c6ce;--accent:#97e5c7;--gold:#f1d18b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}header,main,footer{max-width:1440px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;gap:24px;border-bottom:1px solid var(--line)}nav{display:flex;gap:20px;flex-wrap:wrap}a{color:var(--accent)}.brand{font-weight:750;letter-spacing:.08em}h1{font-size:clamp(32px,5vw,56px);letter-spacing:-.035em;line-height:1.1;margin:18px 0}h2{font-size:16px;margin:0 0 16px}h2 span{color:var(--muted);font-weight:400}p{color:var(--muted)}.eyebrow{font-size:12px;color:var(--accent);text-transform:uppercase;letter-spacing:.16em}.lead{max-width:950px}.boundary{border-left:3px solid var(--gold);padding:8px 18px;color:var(--gold)}form{display:grid;grid-template-columns:1fr 90px auto;gap:14px;align-items:end;background:var(--panel);padding:20px;border:1px solid var(--line);border-radius:12px;margin:26px 0}label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px}input,select,button{font:inherit;padding:12px;width:100%;border:1px solid #537280;background:#081820;color:var(--ink);border-radius:7px}button{background:var(--accent);color:#0a231b;font-weight:700;cursor:pointer}a:focus,summary:focus,input:focus,select:focus,button:focus{outline:2px solid var(--accent);outline-offset:3px}.status{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.status div{padding:14px;border-bottom:1px solid var(--line)}.status span{display:block;color:var(--muted);font-size:12px;text-transform:uppercase}.status strong{font-size:12px;overflow-wrap:anywhere}.lanes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:30px 0}.lane{padding:18px;background:#0c1a22;border-radius:12px;border:1px solid var(--line)}.node{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:13px;margin:10px 0;overflow-wrap:anywhere}.node summary{display:flex;gap:10px;cursor:pointer;font-size:14px}.number{flex:0 0 20px;white-space:nowrap;color:var(--accent);font:12px/1.7 ui-monospace,monospace}.grade{font-size:10px;color:var(--gold);letter-spacing:.02em}dl{font-size:12px}dt{color:var(--muted);margin-top:10px}dd{margin:3px 0}code{font:12px/1.7 ui-monospace,monospace;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}.binding{border:1px solid var(--line);padding:22px;border-radius:12px}.binding summary{padding:16px 0;cursor:pointer;color:var(--accent)}table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}td,th{padding:8px;border-bottom:1px solid var(--line)}footer{color:var(--muted);font-size:13px}.empty{font-size:13px}@media(max-width:900px){.lanes{grid-template-columns:1fr 1fr}}@media(max-width:620px){header{display:block}nav{margin-top:14px}.lanes,.status,form{grid-template-columns:1fr}main{padding:18px}}
</style></head><body><header><div class="brand">SZL / EVIDENCE GRAPH</div><nav><a href="/">Console</a><a href="/hologram">Hologram</a><a href="/readyz">Service readiness</a></nav></header><main>
<div class="eyebrow">One transaction · typed evidence · explicit limits</div><h1>Inspect what supports the decision.</h1>
<p class="lead">Follow public evidence handles, research candidates, Lutar references and the software citation plan. Open any object to inspect its source and content identity.</p>
<p class="boundary">Reference is not proof. Observation is not authorization. This view does not execute tools, train models or certify deployed systems.</p>
<form action="/evidence" method="get"><div><label for="q">Public evidence query</label><input id="q" name="q" maxlength="2000" value="''' + _e(query) + '''"></div><div><label for="k">Results</label><select id="k" name="k">''' + "".join(f'<option value="{i}"{" selected" if i == k else ""}>{i}</option>' for i in range(1,13)) + '''</select></div><button type="submit">Trace evidence</button></form>''' + content + '''
</main><footer>Local source-bound inspection · Optional LangChain / LangGraph adapters use this same contract · NVIDIA telemetry is controller-configured, never a source of authority.</footer></body></html>'''
