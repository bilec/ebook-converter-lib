"""Pure-Python stand-ins for packages Chaquopy cannot build."""

import logging

from ebook_converter.ebooks.oeb.parse_utils import parse_html


def test_html5_fallback_survives_prefixed_tag_names_in_text():
    # Technical books mention XML like <cache:annotation-driven> in prose.
    root = parse_html(
        '<html><body><p>use <cache:annotation-driven> and <x foo:bar="1"> now</p>'
        '<p>see <beans xmlns:context="urn:x"></beans> then <context:scan> end</p>'
        '<p>json <a {id}",="1" href="#x">link</a></p></body></html>',
        log=logging.getLogger("test"),
        filename="t.html",
    )
    assert "now" in "".join(root.itertext())


def test_html5_fallback_keeps_declared_prefixes():
    import html5_parser

    root = html5_parser.parse(
        '<html xmlns:epub="http://www.idpf.org/2007/ops"><body><p epub:type="note" xml:lang="cs">x</p></body></html>'
    )
    p = root.find(".//p")
    assert p.get("epub:type") == "note"
    assert p.get("xml:lang") == "cs"
