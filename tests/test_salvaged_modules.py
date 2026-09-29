"""
Modules ported from calibre to close gaps in the vendored tree.

`ebook_converter/` came from gryf/ebook-converter, which never included these,
so each one is backed by a test proving the code path it unblocks actually runs.

Run:  python -m pytest tests/test_salvaged_modules.py -v
  or: python -m unittest tests.test_salvaged_modules -v
"""

import unittest

from tests.support import SEED_EPUB, TempDirTestCase, convert


class TestLcid(unittest.TestCase):
    """DOCX files store languages as hex LCIDs; without the table they crash."""

    def _read_lang(self, value):
        from lxml import etree

        from ebook_converter.ebooks.docx.char_styles import read_lang
        from ebook_converter.ebooks.docx.names import DOCXNamespace

        namespace = DOCXNamespace()
        parent = etree.fromstring(f'<rPr xmlns:w="{namespace.namespaces["w"]}"><w:lang w:val="{value}"/></rPr>')
        dest = type("Dest", (), {})()
        read_lang(parent, dest, namespace.XPath, namespace.get)
        return dest.lang

    def test_hex_lcid_resolves_to_language_code(self):
        self.assertEqual(self._read_lang("0409"), "en")

    def test_plain_language_code_passes_through(self):
        self.assertEqual(self._read_lang("fr-FR"), "fr-FR")


class TestLinearizeTables(TempDirTestCase):
    """--linearize-tables raised ModuleNotFoundError instead of converting."""

    prefix = "econverter_salvage_"

    def test_linearize_tables_option_runs(self):
        import converter

        out = self.tmp_path("linearized.epub")
        result = converter.convert(SEED_EPUB, out, "--linearize-tables")

        self.assertTrue(result["success"], result["message"])
        self.assert_artifact(out, "linearize-tables")

    def test_tables_become_divs(self):
        from lxml import etree

        from ebook_converter.ebooks.oeb.transforms.linearize_tables import LinearizeTables

        root = etree.fromstring(
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            '<table border="1"><tr><td>cell</td></tr></table></body></html>'
        )
        LinearizeTables().linearize(root)

        tags = {etree.QName(node).localname for node in root.iter() if isinstance(node.tag, str)}
        self.assertNotIn("table", tags)
        self.assertNotIn("td", tags)


class TestExtzMetadata(TempDirTestCase):
    """HTMLZ and TXTZ input read their metadata through ebooks.metadata.extz."""

    prefix = "econverter_extz_"

    def _metadata_of(self, fmt):
        from ebook_converter.customize.ui import get_file_type_metadata

        archive = self.tmp_path(f"seed.{fmt}")
        convert(SEED_EPUB, archive)
        with open(archive, "rb") as handle:
            return get_file_type_metadata(handle, fmt)

    def test_htmlz_metadata_is_read(self):
        self.assertIn("Yellow Wall", self._metadata_of("htmlz").title)

    def test_txtz_metadata_is_read(self):
        self.assertIn("Yellow Wall", self._metadata_of("txtz").title)


if __name__ == "__main__":
    unittest.main()
