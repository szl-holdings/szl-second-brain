"""Run from the repository root: python -m examples.showcase --help."""
from __future__ import annotations

import argparse
import html
import json

from .engine import Showcase
from .evaluate import evaluate


def render(report: dict) -> str:
    def esc(value):
        return html.escape(str(value), quote=True)

    cards = []
    for row in report["details"]:
        result = row["output"]
        if not row["schema_valid"]:
            cards.append(f'<article><h3>{esc(row["query"])}</h3><p>INVALID OUTPUT — counted as failure.</p></article>')
            continue
        citations = "".join(
            f'<li><blockquote>{esc(c["quote"])}</blockquote>'
            f'<code>{esc(c["record_id"])}</code> · {esc(c["source_id"])} · {esc(c["date"])}'
            f'<br>Text SHA-256: <code>{esc(c["text_sha256"])}</code></li>'
            for c in result["citations"])
        cards.append(f'<article><small>{esc(row["split"])} · {esc(row["id"])}</small>'
                     f'<h3>{esc(result["query"] or "(empty query)")}</h3>'
                     f'<p><strong>{esc(result["state"])}</strong> · {esc(result["reason"])}</p>'
                     f'<p>{esc(result["answer"] or "Unknown / abstain. No supported answer emitted.")}</p>'
                     f'<p>Lexical candidates: {esc(", ".join(result["retrieved_ids"]) or "none")}</p>'
                     f'<ol>{citations}</ol></article>')
    metrics = report["splits"]["evaluation"]
    rows = "".join(f'<tr><td>{esc(key.replace("_", " "))}</td><td>{value["success"]}/{value["total"]}</td></tr>'
                   for key, value in metrics.items() if isinstance(value, dict))
    return '<!doctype html><html lang="en"><head><meta charset="utf-8">' + (
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        '<title>Second Brain · Synthetic retrieval showcase</title>'
        '<style>body{font:17px/1.6 system-ui,sans-serif;background:#101827;color:#e6edf7;margin:0}'
        'main{max-width:1000px;margin:auto;padding:44px 24px}h1{font-size:2.7rem;line-height:1.15}'
        'h2{margin-top:40px}small{color:#93c5fd}article{background:#19263c;border:1px solid #34445c;'
        'padding:22px;margin:18px 0;border-radius:12px}code{overflow-wrap:anywhere;font-size:.85em}'
        'table{border-collapse:collapse;width:100%}td{border-bottom:1px solid #34445c;padding:8px}'
        'blockquote{border-left:3px solid #67e8c2;padding-left:16px;margin:10px 0}strong{color:#67e8c2}'
        '</style></head><body><main><small>MODEL-FREE · OFFLINE · SYNTHETIC FIXTURES</small>'
        '<h1>Evidence you can follow.<br>Unknowns you can see.</h1>'
        '<p>Freshly authored fictional records. This page demonstrates deterministic search, '
        'cited facts and directed paths over explicit fixture edges. It grants no training or execution authority.</p>'
        '<p>Lexical overlap ranks candidates; exact structured statements support answers. '
        'Graph traversal scans admitted synthetic edges separately from the top-k lexical result.</p>'
        f'<h2>Evaluation partition · {metrics["cases"]} queries · k={report["k"]}</h2><table>' + rows + '</table>'
        '<p>' + esc(report['baseline']) + '.</p><p>' + esc(report['limitations']) + '</p>'
        '<p>Future promotion targets: ' + esc(report['promotion_targets']) + '.</p>'
        '<p>Fixture revision: <code>' + esc(report['fixture_revision']) + '</code><br>'
        'Query revision: <code>' + esc(report['query_revision']) + '</code></p>'
        '<h2>Frozen query results</h2>' + ''.join(cards) +
        '<footer>No production-readiness, novelty, model-quality or Conjecture 1 proof claim. '
        'All source identities and dates above belong to fictional fixtures.</footer></main></body></html>')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", help="A documented fact or directed-path question")
    parser.add_argument("--evaluate", action="store_true", help="Print frozen evaluation JSON")
    parser.add_argument("--html", action="store_true", help="Print a static evaluation page to stdout")
    parser.add_argument("--k", type=int, default=3, choices=range(1, 13))
    args = parser.parse_args(argv)
    if args.query is not None and (args.evaluate or args.html):
        parser.error("choose a query or evaluation output")
    if args.query is None and not (args.evaluate or args.html):
        parser.error("supply a query, --evaluate, or --html")
    demo = Showcase.bundled()
    try:
        output = evaluate(demo, k=args.k) if args.evaluate or args.html else demo.query(args.query, args.k)
    except ValueError as exc:
        parser.error(str(exc))
    print(render(output) if args.html else json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
