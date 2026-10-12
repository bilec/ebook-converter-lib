import os
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


def _convert_minimal(tmp_path, *extra_args):
    from tests.support import make_minimal_epub

    src = str(tmp_path / "in.epub")
    make_minimal_epub(src)
    return convert(src, str(tmp_path / "out.epub"), *extra_args)


def test_convert_leaves_no_temp_files(tmp_path):
    from ebook_converter.ptempfile import base_dir

    assert _convert_minimal(tmp_path)["success"]
    assert os.listdir(base_dir()) == []


def test_invalid_remove_text_pattern_fails_instead_of_being_ignored(tmp_path):
    result = _convert_minimal(tmp_path, "--remove-text", "Chapter 1\nNote (draft")

    assert not result["success"]
    assert "Note (draft" in result["message"]


def test_remove_text_lines_valid_alone_but_not_joined_fail(tmp_path):
    result = _convert_minimal(tmp_path, "--remove-text", "Chapter 1\n(?i)note")

    assert not result["success"]
    assert "(?i)note" in result["message"]


def test_unknown_option_fails_instead_of_being_ignored(tmp_path):
    result = _convert_minimal(tmp_path, "--marign-top", "5")

    assert not result["success"]
    assert "--marign-top" in result["message"]


def test_stray_argument_fails_instead_of_being_ignored(tmp_path):
    result = _convert_minimal(tmp_path, "--title", "My", "Book")

    assert not result["success"]
    assert "Book" in result["message"]


def test_encoding_detection_normalizes_missing_confidence(monkeypatch):
    from ebook_converter.ebooks.chardet import detect

    monkeypatch.setitem(
        sys.modules,
        "chardet",
        SimpleNamespace(detect=lambda _: {"encoding": "utf-8", "confidence": None}),
    )

    assert detect(b"plain text")["confidence"] == 0.0
