import sys
from types import SimpleNamespace

from ebook_converter_lib import check_deps_str, convert
from ebook_converter_lib.bridge import _parse_extra_args


def test_public_convert_is_bridge_function():
    assert convert.__module__ == "ebook_converter_lib.bridge"


def test_dependency_check_reports_a_string():
    assert isinstance(check_deps_str(), str)


def test_remove_text_lines_become_search_pattern():
    options = _parse_extra_args(("--remove-text", "-a II E-\nChapter \\d+"))

    assert options["sr1_search"] == r"(?:-a II E-|Chapter \d+)"
    assert options["sr1_replace"] == ""


def test_parse_extra_args_preserves_string_and_boolean_values():
    assert _parse_extra_args(("--base-font-size", "12", "--enable-heuristics")) == {
        "base_font_size": "12",
        "enable_heuristics": True,
    }


def test_encoding_detection_normalizes_missing_confidence(monkeypatch):
    from ebook_converter.ebooks.chardet import detect

    monkeypatch.setitem(
        sys.modules,
        "chardet",
        SimpleNamespace(detect=lambda _: {"encoding": "utf-8", "confidence": None}),
    )

    assert detect(b"plain text")["confidence"] == 0.0
