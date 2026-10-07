"""Run from the repository root: python -m examples.showcase --help."""
from __future__ import annotations

import argparse
import json

from .engine import Showcase
from .evaluate import evaluate
from .view import render_page


def render(report: dict, *, demo: Showcase | None = None) -> str:
    return render_page(report, demo=demo)


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
        return 2
    print(render(output, demo=demo) if args.html else json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
