from __future__ import annotations

import re
from html.parser import HTMLParser
from xml.etree import ElementTree

import pytest

from examples.showcase.__main__ import render
from examples.showcase.engine import Showcase, fixture_revision, read_fixture
from examples.showcase.evaluate import evaluate, load_queries
from examples.showcase.view import STYLE, evidence_graph, source_anchor


class Markup(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.elements = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


@pytest.fixture
def visual():
    demo = Showcase.bundled()
    page = render(evaluate(demo), demo=demo)
    return demo, page, Markup(page)


def test_graph_and_record_cards_are_exact_admitted_projection(visual):
    demo, page, markup = visual
    graph = next(attrs for _, attrs in markup.elements if attrs.get("id") == "graph")
    assert graph["data-admitted-record-count"] == "13"
    assert graph["data-entity-count"] == "7" and graph["data-edge-count"] == "5"
    cards = [a for t, a in markup.elements if t == "article" and a.get("class") == "source-card"]
    assert len(cards) == 13 and {a["data-record-id"] for a in cards} == set(demo.by_id)
    edges = [a for _, a in markup.elements if a.get("class") == "graph-edge"]
    actual = {(a["data-subject"], a["data-predicate"], a["data-object"], a["data-record-id"]) for a in edges}
    expected = {(c.subject, c.predicate, c.object, r.id)
                for r in demo.records for c in r.claims if c.kind == "edge"}
    assert len(edges) == len(expected) == 5 and actual == expected
    entities = [a["data-entity"] for _, a in markup.elements if a.get("class") == "graph-entity"]
    assert len(entities) == len(set(entities)) == 7
    assert set(entities) == {n for s, _, o, _ in expected for n in (s, o)}
    assert "SYNTHETIC / UNVERIFIED" in page


def test_denied_record_identity_and_content_never_enter_evidence_view(visual):
    demo, page, _ = visual
    graph_and_sources = page.split('<section id="graph"', 1)[1].split('<section id="metrics"', 1)[0]
    records, _ = read_fixture("records.json")
    denied = [r for r in records if r["id"] not in demo.by_id]
    assert len(denied) == 4
    for row in denied:
        assert row["id"] not in page and row["source_id"] not in page
        assert row["title"] not in graph_and_sources
        for claim in row["claims"]:
            assert f'{claim["subject"]} | {claim["predicate"]} | {claim["object"]}.' not in page
    # Negative test questions remain visible in the query-results section; they
    # are caller input, not permission to disclose excluded source records.


def test_removing_admission_removes_source_card_edge_and_entity():
    values, _ = read_fixture("records.json")
    next(r for r in values if r["id"] == "syn-catalog-edge")["rights"]["retrieval"] = False
    demo = Showcase(values, fixture_revision(values))
    page = render(evaluate(demo), demo=demo)
    assert 'data-admitted-record-count="12"' in page
    assert 'data-edge-count="4"' in page and 'data-entity-count="6"' in page
    assert 'data-entity="elm annex"' not in page
    assert source_anchor("syn-catalog-edge") not in page


def test_all_links_are_keyboard_native_local_targets_and_fallback_is_complete(visual):
    demo, _, markup = visual
    ids = [a["id"] for _, a in markup.elements if "id" in a]
    assert len(ids) == len(set(ids)), "duplicate HTML IDs"
    for tag, attrs in markup.elements:
        if "href" in attrs:
            assert tag == "a" and attrs["href"].startswith("#")
            assert attrs["href"][1:] in ids
        assert "tabindex" not in attrs or attrs["tabindex"] == "0"
        assert not any(name.lower().startswith("on") for name in attrs)
    scroll = next(a for _, a in markup.elements if a.get("class") == "graph-scroll")
    assert scroll["tabindex"] == "0" and scroll["role"] == "region" and scroll["aria-describedby"] == "graph-help"
    fallback = next(a for t, a in markup.elements if t == "details" and a.get("class") == "edge-fallback")
    assert "open" in fallback
    listed = {a["data-record-id"] for t, a in markup.elements if t == "li" and "data-record-id" in a}
    assert listed == {r.id for r in demo.records if any(c.kind == "edge" for c in r.claims)}


def test_svg_is_well_formed_with_semantics_and_bounded_geometry(visual):
    _, page, _ = visual
    svg_text = re.search(r"<svg\b.*?</svg>", page, re.DOTALL).group()
    svg = ElementTree.fromstring(svg_text)
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert svg.attrib["role"] == "group"
    assert svg.find("s:title", ns).text and svg.find("s:desc", ns).text
    _, _, width, height = map(float, svg.attrib["viewBox"].split())
    for rect in svg.findall(".//s:rect", ns):
        x, y, w, h = (float(rect.attrib[k]) for k in ("x", "y", "width", "height"))
        assert 0 <= x < x + w <= width and 0 <= y < y + h <= height
    directed = [p for p in svg.findall(".//s:path", ns) if "marker-end" in p.attrib]
    assert len(directed) == 5 and all(p.attrib["marker-end"] == "url(#arrow)" for p in directed)


def test_css_has_narrow_viewport_overflow_and_reduced_motion_contracts():
    # Structural design checks for 320/375/768/1440 widths, not browser-render claims.
    assert all(f"@media(max-width:{n}px)" in STYLE for n in (360, 600, 900))
    assert "max-width:1280px" in STYLE
    assert "minmax(0,1fr)" in STYLE and "overflow-wrap:anywhere" in STYLE
    assert ".graph-scroll{max-width:100%;min-width:0;overflow-x:auto" in STYLE
    assert "svg{display:block;width:100%;min-width:1104px;height:auto}" in STYLE
    assert "@media(prefers-reduced-motion:reduce)" in STYLE
    assert "animation:none!important;transition:none!important;scroll-behavior:auto!important" in STYLE
    assert ":focus-visible" in STYLE
    assert "@import" not in STYLE and "http" not in STYLE


def test_text_palette_meets_contrast_against_declared_surfaces():
    def luminance(color):
        rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb]
        return sum(w * x for w, x in zip((0.2126, 0.7152, 0.0722), linear))

    for text in ("#f0edf7", "#c3bfd1", "#d0bfff", "#ded2f5"):
        for surface in ("#100e17", "#181622", "#302640", "#251e34"):
            assert (luminance(text) + 0.05) / (luminance(surface) + 0.05) >= 4.5


def test_no_script_external_assets_or_active_injection_in_source_fields():
    values, _ = read_fixture("records.json")
    values[0]["title"] = '<img src="https://invalid.example" onerror="alert(1)">'
    values[0]["source_id"] = 'synthetic:<script>alert(1)</script>'
    demo = Showcase(values, fixture_revision(values))
    page = render(evaluate(demo), demo=demo)
    markup = Markup(page)
    assert "&lt;img" in page and "&lt;script&gt;" in page
    assert not ({t for t, _ in markup.elements} & {"script", "iframe", "img", "object", "embed", "foreignobject"})
    for _, attrs in markup.elements:
        assert not any(k in attrs for k in ("src", "srcset", "xlink:href"))
        assert not any(k.startswith("on") for k in attrs)
        if "href" in attrs:
            assert attrs["href"].startswith("#")
    assert "default-src 'none'" in page


def test_visuals_cannot_mix_fixture_generations(visual):
    demo, _, _ = visual
    report = evaluate(demo)
    report["fixture_revision"] = "0" * 64
    with pytest.raises(ValueError, match="revisions differ"):
        render(report, demo=demo)


@pytest.mark.parametrize("forgery", ["denied-record", "wrong-generation"])
def test_invalid_evaluated_evidence_is_neutral_and_never_echoed(visual, forgery):
    demo, _, _ = visual
    cases, _ = load_queries()
    predictions = {r["id"]: demo.query(r["query"]) for r in cases}
    citation = predictions["eval-status"]["citations"][0]
    if forgery == "denied-record":
        citation.update(record_id="syn-denied", quote="quartz engine | status | ready.")
    else:
        citation["fixture_revision"] = "0" * 64
    report = evaluate(demo, predictions=predictions)
    failed = next(row for row in report["details"] if row["id"] == "eval-status")
    assert failed["schema_valid"] and not failed["evidence_valid"]
    page = render(report, demo=demo)
    card = page.split('<article class="result-card" data-case-id="eval-status">', 1)[1].split('</article>', 1)[0]
    assert "INVALID EVIDENCE" in card and "counted as failure" in card
    assert "ANSWERED" not in card and "syn-" not in card and "href=" not in card
    assert "quartz engine | status | ready." not in page
    assert source_anchor("syn-denied") not in page


def test_empty_projection_has_no_fabricated_vertices_or_edges():
    values, _ = read_fixture("records.json")
    for row in values:
        row["rights"]["retrieval"] = False
    demo = Showcase(values, fixture_revision(values))
    graph = evidence_graph(demo)
    assert 'data-admitted-record-count="0"' in graph
    assert 'data-entity-count="0"' in graph and 'data-edge-count="0"' in graph
    assert 'class="graph-entity"' not in graph and 'class="graph-edge"' not in graph
