# SPDX-License-Identifier: Apache-2.0
"""Accessible server-rendered evidence inspector over the same API projection."""
from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import urlencode


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def render_lineage(payload: dict[str, Any]) -> str:
    """No network, scripts, state writes or second source read while rendering."""
    effective = payload["effective_reference_ready"]
    scenario = payload["scenario"]
    rehearsal = scenario != "observed"
    source = payload["source"]
    source_url = ("https://github.com/" + source["repository"] + "/blob/"
                  + source["revision"] + "/" + source["path"])
    api_url = "/api/v1/lutar-lineage?" + urlencode({"scenario": scenario})
    banner = (
        '<aside class="notice" role="status"><strong>Evidence-loss rehearsal · hypothetical</strong>'
        '<p>The source reference is withheld from this projection only. No file, provider, '
        'model or permission is changed. Return to the observed view to discard the scenario.</p></aside>'
        if rehearsal else '<aside class="notice" role="status"><strong>Observed local reference</strong>'
        '<p>Source bytes are rechecked for this request. Upstream freshness, proof replay, '
        'runtime refinement and model quality are separate gates.</p></aside>'
    )
    if not payload["observed_reference_ready"]:
        banner += '<p class="error" role="alert">Pinned source unavailable or changed. No claim or carrier references are served.</p>'
    gates = ''.join(
        '<li class="gate"><div><span class="gate-name">' + _e(g["label"]) + '</span>'
        '<code>' + _e(g["state"]) + '</code></div><p>' + _e(g["requirement"]) + '</p></li>'
        for g in payload["gates"]
    )
    claims = ''.join(
        '<details class="claim" id="claim-' + _e(c["claimId"]) + '"><summary><span>'
        + _e(c["claimId"]) + '</span> ' + _e(c["title"]) + '</summary>'
        '<p>Source-declared carrier names; not proof replay or runtime verification in this consumer.</p>'
        '<ul>' + ''.join('<li><code>' + _e(n) + '</code></li>' for n in c["declarationNames"]) + '</ul>'
        '<div class="identities"><span>Claim content digest</span><code>' + _e(c["sha256"]) + '</code>'
        '<span>Source document digest</span><code>' + _e(c["sourceSha256"]) + '</code></div></details>'
        for c in payload["claims"]
    ) or '<p class="empty">No supported claim handles in this view.</p>'
    impact = payload["impact"]
    coverage = payload["coverage"]
    facts = [
        (str(coverage["claim_handles"]["observed"]) + ' / 8', 'Supported claim references'),
        (str(coverage["carrier_names"]["observed"]) + ' / 24', 'Named carriers, not replayed proofs'),
        ('Not measured', 'Proof replay and model quality'),
        ('None', 'Execution and training authority'),
    ]
    metrics = ''.join('<article class="metric"><strong>' + _e(value) + '</strong><span>' + _e(label)
                      + '</span></article>' for value, label in facts)
    state = 'Reference support available' if effective else 'Reference support unavailable'
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Lutar · Evidence lineage</title>
<style>
:root{color-scheme:dark;--bg:#081116;--panel:#102028;--line:#27404b;--ink:#e8f1ef;--muted:#a1b7bd;--accent:#8fe2bd;--amber:#ebc68c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,sans-serif}a{color:var(--accent)}header,main,footer{max-width:1200px;margin:auto;padding:24px}header{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line)}nav{display:flex;gap:18px;flex-wrap:wrap}.brand{font-weight:750;letter-spacing:.05em}.eyebrow{color:var(--accent);font-size:12px;text-transform:uppercase;letter-spacing:.14em}h1{font-size:clamp(30px,4.5vw,52px);line-height:1.1;letter-spacing:-.04em;max-width:900px;margin:20px 0}h2{font-size:23px}p{color:var(--muted)}.lead{max-width:800px}.notice,.source,.gate,.claim,.snapshot,.metric,.rehearsal{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px}.notice{border-left:4px solid var(--amber);margin:24px 0}.notice strong{color:var(--amber)}.notice p{margin-bottom:0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.metric strong,.metric span{display:block}.metric strong{font-size:25px}.metric span{font-size:12px;color:var(--muted);margin-top:8px}.flow{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:16px;align-items:center;margin:28px 0}.flow>div{border:1px solid var(--line);border-radius:8px;padding:14px}.flow small{display:block;color:var(--muted)}.arrow{color:var(--amber);font-size:13px;text-align:center}.columns{display:grid;grid-template-columns:1.05fr 1fr;gap:26px}.claim{margin:12px 0}.claim summary{cursor:pointer;font-weight:650}.claim summary span{color:var(--accent);margin-right:12px}.claim ul{padding-left:18px}.identities span{color:var(--muted);display:block;margin-top:12px;font-size:12px}.gates{padding:0;list-style:none}.gate{margin:12px 0}.gate>div{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}.gate-name{font-weight:650}.gate p{font-size:14px;margin-bottom:0}.gate code{color:var(--amber)}code{font:12px/1.7 ui-monospace,monospace;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.source code,.snapshot code{display:block}.rehearsal{margin:24px 0}.rehearsal form{display:flex;gap:12px;align-items:end;flex-wrap:wrap}label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px}select,button{font:inherit;border:1px solid var(--line);border-radius:7px;padding:11px;background:var(--bg);color:var(--ink)}button{background:var(--accent);color:#092015;font-weight:650;cursor:pointer}a:focus,summary:focus,select:focus,button:focus{outline:2px solid var(--accent);outline-offset:4px}.error{color:#ffb6ae}.snapshot{margin-top:26px}.empty{padding:15px 0}footer{color:var(--muted);font-size:13px}@media(max-width:800px){.metrics{grid-template-columns:repeat(2,1fr)}.columns{grid-template-columns:1fr}header{display:block}nav{margin-top:12px}.flow{grid-template-columns:1fr}.arrow{padding:0}.flow>div{padding:12px}.flow .arrow{transform:none}main{padding:18px}}
</style></head><body><header><div class="brand">SZL / LUTAR</div><nav><a href="/">Evidence console</a><a href="/hologram">Hologram</a><a href="/api/v1/anatomy-feed">Anatomy feed</a></nav></header>
<main><div class="eyebrow">Source-bound evidence · read-only</div><h1>What does the evidence actually support?</h1>
<p class="lead">Follow one pinned Lutar claim document into its eight claim handles and 24 named carriers. Inspect the remaining assurance gates without turning source declarations into proof or production claims.</p>''' + banner + '<section class="metrics" aria-label="Reference coverage">' + metrics + '</section>' + '''
<section class="source"><h2>''' + _e(state) + '</h2><a rel="noreferrer" href="' + _e(source_url) + '">Inspect the immutable source document</a><p>' + _e(source["repository"]) + ' · ' + _e(source["path"]) + '</p><code>' + _e(source["revision"]) + '</code><code>' + _e(source["sha256"]) + '</code></section>' + '''
<div class="flow" aria-label="Typed evidence relationships"><div>Pinned claim document<small>Byte identity, not a signature</small></div><span class="arrow">DECLARES →</span><div>Claim handles<small>Active counts are shown above; source-declared scope</small></div><span class="arrow">NAMES CARRIER →</span><div>Carrier names<small>Active counts are shown above; not proof terms</small></div></div>
<section class="rehearsal"><h2>Rehearse evidence loss</h2><p>Withhold the source from a copy of the projection. Nothing is deleted, restarted or published. Removing evidence can only remove support.</p>
<form method="get" action="/lutar"><div><label for="scenario">Read-only scenario</label><select name="scenario" id="scenario">''' + ''.join('<option value="' + name + '"' + (' selected' if name == scenario else '') + '>' + label + '</option>' for name, label in (('observed', 'Observed reference'), ('withhold-source', 'Hypothetically withhold source'))) + '</select></div><button type="submit">Inspect scenario</button></form><p>Withdrawn in this projection: ' + str(impact["withdrawn_claim_handles"]) + ' claim handles and ' + str(impact["withdrawn_carrier_names"]) + ' carrier names. Actions performed: 0.</p></section>' + '<div class="columns"><section><h2>Claim handles</h2>' + claims + '</section><section><h2>Assurance gates</h2><p>A verified source does not close the other gates.</p><ol class="gates">' + gates + '</ol></section></div>' + '<section class="snapshot"><h2>One projection, shared contract</h2><p>The HTML view and JSON API use the same deterministic projection. Anatomy retains the same source identity. This digest is unsigned; it is not an attestation.</p><code id="snapshot-digest">' + _e(payload["snapshot_sha256"]) + '</code><p><a href="' + _e(api_url) + '">Inspect the same projection through the JSON API</a></p><details><summary>Read the complete public projection</summary><pre>' + _e(json.dumps(payload, indent=2, ensure_ascii=False)) + '</pre></details></section></main><footer>No private graph content · No proof replay in this consumer · No provider requests · No training, execution, promotion or merge authority</footer></body></html>'
