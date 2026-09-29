"""
Regression tests: converter.convert() extra_args arrive as strings and
must be coerced to match numeric option defaults, not crash on comparison.

Run:  python -m pytest tests/ -v
  or: python -m unittest tests.test_converter_extra_args -v
"""

import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_convert_all_formats import _make_minimal_epub


class TestConverterExtraArgs(unittest.TestCase):
    """converter.convert() with string-valued numeric extra args."""

    def test_remove_text_lines_become_search_patterns(self):
        import converter

        options = converter._parse_extra_args(("--remove-text", "-a II E-\nChapter \\d+"))

        self.assertEqual(options["sr1_search"], r"(?:-a II E-|Chapter \d+)")
        self.assertEqual(options["sr1_replace"], "")

    def test_econverter_arg_set_maps_to_plumber_option_names(self):
        """Every flag econverter's buildExtraArgs() emits must land on a real Plumber option."""
        import converter
        from ebook_converter import logging
        from ebook_converter.ebooks.conversion.plumber import Plumber

        options = converter._parse_extra_args(
            (
                "--output-profile",
                "kindle",
                "--smarten-punctuation",
                "--epub-version",
                "3",
                "--title",
                "A Title",
                "--authors",
                "An Author",
                "--publisher",
                "A Publisher",
                "--comments",
                "A description",
                "--cover",
                "/tmp/cover.jpg",
                "--base-font-size",
                "12",
                "--disable-font-rescaling",
                "--margin-top",
                "10",
                "--margin-bottom",
                "10",
                "--margin-left",
                "8",
                "--margin-right",
                "8",
                "--remove-text",
                "Chapter \\d+",
            )
        )

        self.assertEqual(options["output_profile"], "kindle")
        self.assertIs(options["smarten_punctuation"], True)
        self.assertIs(options["disable_font_rescaling"], True)
        self.assertEqual(options["epub_version"], "3")
        self.assertEqual(options["title"], "A Title")
        self.assertEqual(options["cover"], "/tmp/cover.jpg")
        self.assertEqual(options["sr1_search"], r"(?:Chapter \d+)")
        self.assertNotIn("remove_text", options)

        plumber = Plumber(self._epub, os.path.join(self._tmpdir, "names.epub"), logging.default_log)
        for name in options:
            self.assertIsNotNone(plumber.get_option_by_name(name), f"unknown Plumber option: {name}")

    def test_econverter_arg_set_converts(self):
        """End-to-end with the full flag set econverter sends, minus --cover."""
        import converter

        out_path = os.path.join(self._tmpdir, "econverter_args.epub")
        result = converter.convert(
            self._epub,
            out_path,
            "--output-profile",
            "tablet",
            "--smarten-punctuation",
            "--epub-version",
            "3",
            "--title",
            "A Title",
            "--authors",
            "An Author",
            "--publisher",
            "A Publisher",
            "--comments",
            "A description",
            "--base-font-size",
            "12",
            "--disable-font-rescaling",
            "--margin-top",
            "10",
            "--margin-bottom",
            "10",
            "--margin-left",
            "8",
            "--margin-right",
            "8",
            "--remove-text",
            "Chapter \\d+",
        )

        self._assert_converted(result, out_path)

    def test_trailing_flag_without_value_is_true(self):
        """econverter appends --remove-text last, so a bare flag can end the list."""
        import converter

        options = converter._parse_extra_args(("--base-font-size", "12", "--smarten-punctuation"))

        self.assertEqual(options["base_font_size"], "12")
        self.assertIs(options["smarten_punctuation"], True)

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="econverter_test_")
        cls._epub = os.path.join(cls._tmpdir, "test.epub")
        _make_minimal_epub(cls._epub)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _assert_converted(self, result, out_path):
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(os.path.isfile(out_path))
        self.assertGreater(os.path.getsize(out_path), 0)

    def test_base_font_size_string_arg_does_not_crash(self):
        """Used to raise: TypeError: '<' not supported between 'str' and 'float'."""
        import converter

        out_path = os.path.join(self._tmpdir, "base_font_size.epub")
        result = converter.convert(self._epub, out_path, "--base-font-size", "12")
        self._assert_converted(result, out_path)

    def test_margin_string_args_do_not_crash(self):
        """Margins default to float(5.0); string values must be coerced too."""
        import converter

        out_path = os.path.join(self._tmpdir, "margins.epub")
        result = converter.convert(
            self._epub,
            out_path,
            "--margin-top",
            "10",
            "--margin-bottom",
            "10",
            "--margin-left",
            "8",
            "--margin-right",
            "8",
        )
        self._assert_converted(result, out_path)

    def test_boolean_string_args_coerced_correctly(self):
        """Boolean options passed as string 'false' must be coerced to False."""
        from ebook_converter import logging
        from ebook_converter.customize.conversion import OptionRecommendation
        from ebook_converter.ebooks.conversion.plumber import Plumber

        out_path = os.path.join(self._tmpdir, "bool_test.mobi")
        p = Plumber(self._epub, out_path, logging.default_log)
        p.merge_ui_recommendations([("enable_heuristics", "false", OptionRecommendation.MED)])
        self.assertIs(p.get_option_by_name("enable_heuristics").recommended_value, False)

    def test_xml_parse_returns_none_on_invalid_xml(self):
        """safe_xml_fromstring should return None rather than raising XMLSyntaxError on invalid XML or empty input."""
        from ebook_converter.utils.xml_parse import safe_xml_fromstring

        self.assertIsNone(safe_xml_fromstring(""))
        self.assertIsNone(safe_xml_fromstring(b""))
        self.assertIsNone(safe_xml_fromstring("not xml at all"))

    def test_txt_conversion_allows_missing_detection_confidence(self):
        import converter

        input_path = os.path.join(self._tmpdir, "detected.txt")
        out_path = os.path.join(self._tmpdir, "detected.epub")
        with open(input_path, "wb") as input_file:
            input_file.write("\u88ab\u5144\u63a7\u59b9\u59b9\u8bf1\u60d1\u800c\u5f00\u59cb\u7684\u7eaf\u7231".encode())

        with patch(
            "ebook_converter.ebooks.chardet.detect",
            return_value={"encoding": "utf-8", "confidence": None},
        ):
            result = converter.convert(input_path, out_path)

        self._assert_converted(result, out_path)

    def test_encoding_detection_normalizes_missing_confidence(self):
        from ebook_converter.ebooks.chardet import detect

        with patch.dict(
            sys.modules,
            {"chardet": SimpleNamespace(detect=lambda _: {"encoding": "utf-8", "confidence": None})},
        ):
            result = detect(b"plain text")

        self.assertEqual(result["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
