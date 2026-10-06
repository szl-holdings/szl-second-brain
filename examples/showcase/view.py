"""Deterministic, script-free presentation of an admitted synthetic projection."""
from __future__ import annotations

import html

from .engine import Showcase, digest


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def source_anchor(record_id: str) -> str:
    return "source-" + digest(record_id.encode())


def evidence_graph(demo: Showcase) -> str:
    edges = sorted((c.subject, c.predicate, c.object, r.id)
                   for r in demo.records for c in r.claims if c.kind == "edge")
    entities = sorted({n for s, _, o, _ in edges for n in (s, o)})
    neighbors = {n: set() for n in entities}
    for subject, _, obj, _ in edges:
        neighbors[subject].add(obj)
        neighbors[obj].add(subject)
    remaining, components = set(entities), []
    while remaining:
        pending, component = [min(remaining)], set()
        while pending:
            node = pending.pop()
            if node not in component:
                component.add(node)
                pending.extend(sorted(neighbors[node] - component))
        remaining -= component
        components.append(component)
    positions = {}
    for row, component in enumerate(components):
        incoming = {n: sum(o == n for _, _, o, _ in edges) for n in component}
        ready, order = sorted(n for n in component if incoming[n] == 0), []
        while ready:
            node = ready.pop(0)
            order.append(node)
            for subject, _, obj, _ in edges:
                if subject == node:
                    incoming[obj] -= 1
                    if incoming[obj] == 0:
                        ready.append(obj)
                        ready.sort()
        # Cycles affect layout only, never the recorded direction or relation.
        order.extend(sorted(component - set(order)))
        positions.update({n: (112 + column * 220, 80 + row * 150)
                          for column, n in enumerate(order)})
    width = max((x for x, _ in positions.values()), default=112) + 112
    height = max((y for _, y in positions.values()), default=80) + 80
    paths, nodes, fallback = [], [], []
    for subject, predicate, obj, record_id in edges:
        x1, y1 = positions[subject]
        x2, y2 = positions[obj]
        direction = 1 if x2 >= x1 else -1
        start, end = x1 + 88 * direction, x2 - 96 * direction
        paths.append(
            f'<g class="graph-edge" data-record-id="{esc(record_id)}" data-subject="{esc(subject)}" '
            f'data-predicate="{esc(predicate)}" data-object="{esc(obj)}">'
            f'<path d="M {start} {y1} L {end} {y2}" marker-end="url(#arrow)"/>'
            f'<a href="#{source_anchor(record_id)}" aria-label="{esc(subject + " " + predicate + " " + obj + ": source record")}">'
            f'<text x="{(x1+x2)/2:g}" y="{min(y1,y2)-44}" text-anchor="middle">{esc(predicate)}</text></a></g>')
        fallback.append(f'<li data-record-id="{esc(record_id)}">{esc(subject)} '
                        f'<strong>{esc(predicate)}</strong> {esc(obj)} '
                        f'<a href="#{source_anchor(record_id)}">Source: {esc(record_id)}</a></li>')
    for entity, (x, y) in sorted(positions.items()):
        record_id = next(r for s, _, o, r in edges if entity in (s, o))
        nodes.append(f'<g class="graph-entity" data-entity="{esc(entity)}">'
                     f'<a href="#{source_anchor(record_id)}" aria-label="{esc(entity + ": inspect supporting edge record")}">'
                     f'<rect x="{x-88}" y="{y-30}" width="176" height="60" rx="14"/>'
                     f'<circle cx="{x-65}" cy="{y-12}" r="3"/>'
                     f'<text x="{x}" y="{y+7}" text-anchor="middle">{esc(entity)}</text></a></g>')
    return (
        f'<section id="graph" class="panel" aria-labelledby="graph-heading" data-admitted-record-count="{len(demo.records)}" '
        f'data-entity-count="{len(entities)}" data-edge-count="{len(edges)}">'
        '<div class="section-top"><div><p class="eyebrow">01 / Evidence map</p><h2 id="graph-heading">Follow the recorded connections.</h2></div>'
        '<span class="badge">SYNTHETIC / UNVERIFIED</span></div>'
        f'<p>{len(entities)} entity vertices · {len(edges)} explicit directed edges. The {len(demo.records)} admitted record cards appear below; '
        'excluded records are absent from this projection.</p>'
        '<p id="graph-help" class="muted">Arrows show fixture statements, not inferred truth. On a small screen, scroll the focused map '
        'with the arrow keys or use the complete text list below.</p>'
        '<div class="graph-scroll" tabindex="0" role="region" aria-label="Scrollable evidence map" aria-describedby="graph-help">'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="group" aria-labelledby="graph-title graph-description">'
        '<title id="graph-title">Synthetic directed evidence graph</title><desc id="graph-description">Each arrow has an admitted source record. '
        'Entity and edge links jump to that record. The following text list contains the same connections.</desc>'
        '<defs><linearGradient id="node-fill" x2="1" y2="1"><stop stop-color="#302640"/><stop offset="1" stop-color="#191b29"/></linearGradient>'
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#c5b4ff"/></marker></defs>'
        + ''.join(paths) + ''.join(nodes) + '</svg></div>'
        '<details open class="edge-fallback"><summary>Text equivalent: every recorded edge</summary><ul>'
        + (''.join(fallback) or '<li>No admitted explicit edges.</li>') + '</ul></details></section>')


STYLE = """
:root{color-scheme:dark;--ink:#f0edf7;--muted:#c3bfd1;--violet:#d0bfff;--line:#554967;--panel:#181622}
*{box-sizing:border-box}html{scroll-behavior:auto}body{margin:0;background:#100e17;color:var(--ink);font:16px/1.65 system-ui,sans-serif}
body{background-image:radial-gradient(ellipse at 82% 0,rgba(130,94,181,.19),transparent 42rem)}
main{max-width:1280px;min-width:0;margin:auto;padding:28px 24px 56px}a{color:var(--violet);text-underline-offset:.2em;overflow-wrap:anywhere}
a:hover{color:#fff}a:focus-visible,summary:focus-visible,.graph-scroll:focus-visible{outline:3px solid #e7d8ff;outline-offset:5px;border-radius:4px}
.skip{position:absolute;left:16px;top:-100px;background:#211a30;padding:12px;z-index:2}.skip:focus{top:12px}
nav{display:flex;flex-wrap:wrap;gap:12px 24px;align-items:center;padding:0 0 24px;border-bottom:1px solid var(--line)}
.wordmark{font-weight:750;letter-spacing:.12em;font-size:.85rem;margin-right:auto}.wordmark span{color:var(--violet)}
.hero{padding:64px 0 40px;max-width:900px}.eyebrow{color:var(--violet);font-size:.76rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;margin:0 0 12px}
h1{font-size:clamp(2.25rem,5.5vw,4.75rem);line-height:1.04;font-weight:620;letter-spacing:-.045em;margin:16px 0 24px}
h1 span{color:#d6c5f2}h2{font-size:clamp(1.5rem,3vw,2rem);line-height:1.22;letter-spacing:-.02em;margin:0 0 16px}h3{font-size:1.05rem;line-height:1.4;margin:12px 0}
p{margin:12px 0}.lead{font-size:1.16rem;color:#d7d3df;max-width:720px}.muted,small{color:var(--muted)}
.badge{display:inline-block;max-width:100%;border:1px solid #6f6088;border-radius:999px;color:#e2d4ff;background:#251e34;padding:6px 12px;font-size:.69rem;font-weight:750;letter-spacing:.08em;overflow-wrap:anywhere}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 28px}.stat{border-top:1px solid #796592;padding:18px 8px 12px;min-width:0}
.stat b{font-size:2rem;line-height:1.15;font-weight:550;display:block;color:#eee5ff}.stat span{display:block;color:var(--muted);font-size:.8rem;margin-top:8px}
.panel{min-width:0;border:1px solid var(--line);border-radius:20px;padding:28px;background:linear-gradient(135deg,#211a2b,var(--panel) 65%);box-shadow:0 20px 55px #0003;margin:28px 0}
.section-top{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap}.section-top .badge{flex-shrink:0}
.graph-scroll{max-width:100%;min-width:0;overflow-x:auto;overscroll-behavior-x:contain;border:1px solid #4d425f;border-radius:16px;margin:24px 0;background:#13111d;scrollbar-color:#9b84bd #201a2a}
svg{display:block;width:100%;min-width:1104px;height:auto}.graph-edge path{stroke:#c5b4ff;stroke-width:2;fill:none}.graph-edge text{fill:#ded2f5;font:13px system-ui,sans-serif}
.graph-entity rect{fill:url(#node-fill);stroke:#a796bd;stroke-width:1.2;filter:drop-shadow(0 3px 7px #77509828)}
.graph-entity text{fill:#f0edf7;font:14px system-ui,sans-serif}.graph-entity circle{fill:#d2b9ff}
svg a:focus-visible rect{stroke:#fff;stroke-width:3}svg a:focus-visible text{text-decoration:underline}
details{border-top:1px solid var(--line);padding-top:14px}summary{cursor:pointer;color:#e3d4ff;font-weight:600;min-height:44px;padding:6px 0}
.edge-fallback ul{padding-left:22px;margin:10px 0}.edge-fallback li{padding:5px 0}.edge-fallback a{display:block;font-size:.8rem}.edge-fallback strong{color:#deccff}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.source-card,.result-card{min-width:0;padding:20px;border:1px solid #51455f;border-radius:14px;background:#181520;scroll-margin-top:20px}
.source-card:target{outline:3px solid #d8bfff;background:#262032}.source-card h3{margin-top:8px}.source-card ul{padding-left:18px;font-size:.9rem}
code{font:.76rem/1.6 ui-monospace,monospace;overflow-wrap:anywhere;word-break:break-word}.source-card code{color:#d6c6ed}.provenance{font-size:.82rem;color:var(--muted);overflow-wrap:anywhere}
.source-card a,.result-card a{min-height:44px;display:inline-flex;align-items:center}.source-card details{margin-top:12px}.source-card summary{font-size:.84rem}
.metric-wrap{max-width:100%;overflow-x:auto}table{width:100%;border-collapse:collapse;text-align:left}caption{text-align:left;color:var(--muted);padding:8px 0 16px}
th,td{border-bottom:1px solid #4b405b;padding:12px 10px;vertical-align:top}th{font-size:.8rem;color:#dfd5ec}td:last-child{font-variant-numeric:tabular-nums;white-space:nowrap;color:#e0d0f9}
.results{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.result-card blockquote{border-left:2px solid #aa8ecc;padding-left:14px;margin:14px 0;color:#e8dff5}
.result-card ol{padding-left:20px}.status{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.state{font-size:.7rem;font-weight:750;border:1px solid #796492;border-radius:5px;padding:3px 8px;color:#e4d4f9}
.reason{font-size:.7rem;color:var(--muted);overflow-wrap:anywhere}.answer{font-size:1.1rem;color:#f1e9fc}.result-card small{font-size:.73rem}.result-card p{overflow-wrap:anywhere}
.notice{border-left:3px solid #bda2df;padding:12px 18px;background:#221a2e;color:#ded5e8}.receipt{margin-top:20px}footer{color:var(--muted);font-size:.85rem;padding:32px 4px 0;max-width:900px}
@media(max-width:900px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.panel{padding:22px}}
@media(max-width:600px){main{padding:20px 16px 40px}.hero{padding:40px 0 28px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.cards,.results{grid-template-columns:minmax(0,1fr)}.panel{padding:18px;border-radius:16px}nav{gap:10px 18px}.wordmark{flex-basis:100%}th,td{padding:10px 4px;font-size:.82rem}}
@media(max-width:360px){main{padding-left:12px;padding-right:12px}.panel{padding:14px}.badge{font-size:.63rem}.source-card,.result-card{padding:16px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}.graph-entity rect{filter:none}}
"""


def render_page(report: dict, *, demo: Showcase | None = None) -> str:
    demo = demo if demo is not None else Showcase.bundled()
    if report.get("fixture_revision") != demo.revision:
        raise ValueError("report and visual projection fixture revisions differ")
    cards, sources = [], []
    for record in demo.records:
        quotes = ''.join(f'<li>{esc(c.quote)}</li>' for c in record.claims)
        sources.append(
            f'<article class="source-card" id="{source_anchor(record.id)}" data-record-id="{esc(record.id)}">'
            f'<small>{esc(record.split)} / {esc(record.source_family)}</small><h3>{esc(record.title)}</h3>'
            f'<code>{esc(record.id)}</code><ul>{quotes}</ul><p class="provenance">{esc(record.source_id)}<br>Fixture date: {esc(record.date)}</p>'
            f'<details><summary>Evidence fingerprint</summary><code>{esc(record.sha256)}</code></details>'
            '<a href="#graph">Back to evidence map</a></article>')
    for row in report["details"]:
        result = row["output"]
        if not row["schema_valid"] or not row["evidence_valid"]:
            failure = "INVALID OUTPUT" if not row["schema_valid"] else "INVALID EVIDENCE"
            cards.append(f'<article class="result-card" data-case-id="{esc(row["id"])}">'
                         f'<h3>{esc(row["query"])}</h3><p>{failure} — counted as failure.</p></article>')
            continue
        citations = ''.join(
            f'<li><blockquote>{esc(c["quote"])}</blockquote><a href="#{source_anchor(c["record_id"])}">{esc(c["record_id"])}</a>'
            f'<p class="provenance">{esc(c["source_id"])} · {esc(c["date"])}</p>'
            f'<details><summary>Text SHA-256</summary><code>{esc(c["text_sha256"])}</code></details></li>'
            for c in result["citations"])
        cards.append(f'<article class="result-card" data-case-id="{esc(row["id"])}"><small>{esc(row["split"])} / {esc(row["id"])}</small>'
                     f'<h3>{esc(result["query"] or "(empty query)")}</h3><div class="status"><span class="state">{esc(result["state"])}</span>'
                     f'<span class="reason">{esc(result["reason"])}</span></div>'
                     f'<p class="answer">{esc(result["answer"] or "Unknown / abstain. No supported answer emitted.")}</p>'
                     f'<p class="muted">Lexical candidates: {esc(", ".join(result["retrieved_ids"]) or "none")}</p><ol>{citations}</ol></article>')
    metrics = report["splits"]["evaluation"]
    rows = ''.join(f'<tr><th scope="row">{esc(key.replace("_", " "))}</th><td>{value["success"]}/{value["total"]}</td></tr>'
                   for key, value in metrics.items() if isinstance(value, dict))
    positives, abstentions = metrics["supported_answer_coverage"], metrics["abstention_correctness"]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        '<title>Second Brain · Synthetic evidence atlas</title><style>' + STYLE + '</style></head><body>'
        '<a class="skip" href="#content">Skip to showcase content</a><main id="content"><nav aria-label="Showcase sections">'
        '<div class="wordmark">SZL <span>/</span> SECOND BRAIN</div><a href="#graph">Evidence map</a><a href="#sources">Sources</a>'
        '<a href="#metrics">Evaluation</a><a href="#results">Query results</a></nav>'
        '<header class="hero"><p class="eyebrow">MODEL-FREE · OFFLINE · SYNTHETIC FIXTURES</p>'
        '<h1>A small world.<br><span>Every connection accountable.</span></h1>'
        '<p class="lead">Follow a fact to its source. Trace a recorded path. See exactly where the answer stops.</p>'
        '<span class="badge">SYNTHETIC / UNVERIFIED</span><p class="muted">Fictional evidence, deterministic software. '
        'No real-world verification, model weights, training or execution authority.</p></header><div class="stats" aria-label="Fixture summary">'
        f'<div class="stat"><b>{len(demo.records)}</b><span>admitted synthetic records</span></div>'
        f'<div class="stat"><b>{metrics["cases"]}</b><span>evaluation queries</span></div>'
        f'<div class="stat"><b>{positives["success"]}/{positives["total"]}</b><span>supported fixture answers</span></div>'
        f'<div class="stat"><b>{abstentions["success"]}/{abstentions["total"]}</b><span>correct fixture abstentions</span></div></div>'
        '<p class="notice">Developer-visible synthetic regressions. These counts establish software behavior, '
        'not statistical acceptance, model quality or production readiness.</p>' + evidence_graph(demo) +
        '<section id="sources" class="panel" aria-labelledby="sources-heading"><p class="eyebrow">02 / Admitted sources</p>'
        f'<h2 id="sources-heading">{len(demo.records)} records. Explicit evidence.</h2><p class="muted">Every card passed the exact synthetic '
        'retrieval/display policy. Source IDs and dates belong to fictional records. Untrusted source instructions have no authority.</p>'
        '<div class="cards">' + ''.join(sources) + '</div></section>'
        '<section id="metrics" class="panel" aria-labelledby="metrics-heading"><p class="eyebrow">03 / Measured software</p>'
        '<h2 id="metrics-heading">Retrieval and correctness, measured separately.</h2><p>Lexical overlap ranks candidates; exact statements support answers. '
        'Graph traversal scans admitted edges independently of lexical top-k. It makes no inferred, reversed or transitive claim.</p>'
        f'<div class="metric-wrap"><table><caption>Evaluation partition: {metrics["cases"]} queries, k={report["k"]}. '
        'Ratios show successes / denominator; lower is better only for unsafe or invalid negative output.</caption>'
        '<thead><tr><th scope="col">Metric</th><th scope="col">Count</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
        '<p class="muted">' + esc(report['baseline']) + '.</p><p>' + esc(report['limitations']) + '</p>'
        '<p class="notice">Future promotion targets: ' + esc(report['promotion_targets']) + '.</p>'
        '<details class="receipt"><summary>Frozen fixture revisions</summary><p>Records: <code>' + esc(report['fixture_revision']) + '</code></p>'
        '<p>Queries: <code>' + esc(report['query_revision']) + '</code></p></details></section>'
        '<section id="results" aria-labelledby="results-heading"><p class="eyebrow">04 / Query receipts</p>'
        '<h2 id="results-heading">Answers with evidence. Abstentions without a guess.</h2><div class="results">' + ''.join(cards) + '</div></section>'
        '<footer>No production-readiness, novelty, AGI, model-quality or Conjecture 1 proof claim. The graph states only the fixture’s recorded '
        'directed relationships. No scripts, external assets, network requests, inference or training. Authority: NONE.</footer></main></body></html>')
