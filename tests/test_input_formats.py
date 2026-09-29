"""
Input-side coverage: feed every reachable input format back into the pipeline.

A real public-domain EPUB is converted once to each output format, and every
artifact is then used as *input* for a conversion back to EPUB.  This exercises
the input plugins against non-synthetic markup (real CSS, cover image, multiple
spine items) without committing a fixture per format.

Round-trip fixtures validate the readers against our own writers, so they catch
crashes and regressions rather than semantic correctness.

Run:  python -m pytest tests/test_input_formats.py -v
  or: python -m unittest tests.test_input_formats -v
"""

import os
import shutil
import unittest
import zipfile

from tests.support import (
    SEED_EPUB,
    TempDirTestCase,
    convert,
    make_minimal_odt,
    make_minimal_pdb,
    make_minimal_rtf,
)

# Output formats whose artifact is a single file usable as input.
FILE_ROUNDTRIP = ["azw3", "docx", "epub", "fb2", "htmlz", "lrf", "mobi", "txt", "txtz"]

# HTML Output writes a zip holding the entry document; OEB Output a directory.
ARCHIVE_ROUNDTRIP = ["html"]
DIR_ROUNDTRIP = ["oeb"]

# TXT Input aliases: same bytes, different extension, different detection path.
TXT_ALIASES = ["markdown", "md", "text", "textile"]


class TestInputFormats(TempDirTestCase):
    """Every input plugin reachable from our own output formats must round-trip."""

    prefix = "econverter_inputs_"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._artifacts = {}
        for fmt in FILE_ROUNDTRIP + ARCHIVE_ROUNDTRIP + DIR_ROUNDTRIP:
            out = os.path.join(cls._tmpdir, f"seed.{fmt}")
            convert(SEED_EPUB, out)
            cls._artifacts[fmt] = out

    def _roundtrip(self, src, label):
        out = self.tmp_path(f"back_{label}.epub")
        convert(src, out)
        self.assert_artifact(out, label)

    def test_seed_fixture_present(self):
        self.assertTrue(os.path.isfile(SEED_EPUB), f"missing seed fixture: {SEED_EPUB}")


def _file_test(fmt):
    def test(self):
        self._roundtrip(self._artifacts[fmt], fmt)

    test.__doc__ = f"Convert {fmt.upper()} back to EPUB"
    return test


def _dir_test(fmt):
    def test(self):
        self._roundtrip(os.path.join(self._artifacts[fmt], "content.opf"), fmt)

    test.__doc__ = f"Convert {fmt.upper()} output (via content.opf) back to EPUB"
    return test


def _archive_test(fmt):
    def test(self):
        unpacked = self.tmp_path(f"unpacked_{fmt}")
        with zipfile.ZipFile(self._artifacts[fmt]) as zf:
            zf.extractall(unpacked)
        entry = os.path.join(unpacked, f"seed.{fmt}")
        self.assertTrue(os.path.isfile(entry), f"{fmt}: no entry document in archive")
        self._roundtrip(entry, fmt)

    test.__doc__ = f"Convert {fmt.upper()} output (entry document) back to EPUB"
    return test


def _alias_test(ext):
    def test(self):
        src = self.tmp_path(f"alias.{ext}")
        shutil.copyfile(self._artifacts["txt"], src)
        self._roundtrip(src, ext)

    test.__doc__ = f"Convert .{ext} back to EPUB"
    return test


for _fmt in FILE_ROUNDTRIP:
    setattr(TestInputFormats, f"test_input_{_fmt}", _file_test(_fmt))
for _fmt in ARCHIVE_ROUNDTRIP:
    setattr(TestInputFormats, f"test_input_{_fmt}", _archive_test(_fmt))
for _fmt in DIR_ROUNDTRIP:
    setattr(TestInputFormats, "test_input_opf", _dir_test(_fmt))
for _ext in TXT_ALIASES:
    setattr(TestInputFormats, f"test_input_{_ext}", _alias_test(_ext))


# Extensions read by a plugin we already round-trip, under a different name.
SAME_BYTES_ALIASES = {"azw": "mobi", "prc": "mobi", "pobi": "mobi", "docm": "docx"}

# HTMLInput keys off the extension but reads the same markup.
HTML_ALIASES = ["htm", "shtm", "shtml", "xhtm", "xhtml"]


class TestListedExtensions(TempDirTestCase):
    """README advertises these, so each must convert, not just be registered."""

    prefix = "econverter_listed_"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mobi = os.path.join(cls._tmpdir, "seed.mobi")
        convert(SEED_EPUB, cls._mobi)
        cls._docx = os.path.join(cls._tmpdir, "seed.docx")
        convert(SEED_EPUB, cls._docx)
        cls._fb2 = os.path.join(cls._tmpdir, "seed.fb2")
        convert(SEED_EPUB, cls._fb2)
        cls._html_zip = os.path.join(cls._tmpdir, "seed.html")
        convert(SEED_EPUB, cls._html_zip)

    def _converts(self, src, label):
        out = self.tmp_path(f"listed_{label}.epub")
        convert(src, out)
        self.assert_artifact(out, label)

    def test_input_fbz(self):
        fbz = self.tmp_path("seed.fbz")
        with zipfile.ZipFile(fbz, "w") as archive:
            archive.write(self._fb2, "book.fb2")
        self._converts(fbz, "fbz")

    def test_input_odt(self):
        odt = self.tmp_path("seed.odt")
        make_minimal_odt(odt)
        self._converts(odt, "odt")

    def test_input_rtf(self):
        rtf = self.tmp_path("seed.rtf")
        make_minimal_rtf(rtf)
        self._converts(rtf, "rtf")

    def test_input_pdb(self):
        pdb = self.tmp_path("seed.pdb")
        make_minimal_pdb(pdb)
        self._converts(pdb, "pdb")

    def test_input_updb(self):
        updb = self.tmp_path("seed.updb")
        make_minimal_pdb(updb)
        self._converts(updb, "updb")


def _same_bytes_test(ext, source):
    def test(self):
        src = self.tmp_path(f"alias.{ext}")
        shutil.copyfile(getattr(self, f"_{source}"), src)
        self._converts(src, ext)

    test.__doc__ = f"Convert .{ext} ({source} bytes) to EPUB"
    return test


def _html_alias_test(ext):
    def test(self):
        # Keep the document beside its linked CSS and images; only the name changes.
        site = self.tmp_path(f"site_{ext}")
        with zipfile.ZipFile(self._html_zip) as archive:
            archive.extractall(site)
        entry = os.path.join(site, f"seed.{ext}")
        os.rename(os.path.join(site, "seed.html"), entry)
        self._converts(entry, ext)

    test.__doc__ = f"Convert .{ext} to EPUB"
    return test


for _ext, _source in SAME_BYTES_ALIASES.items():
    setattr(TestListedExtensions, f"test_input_{_ext}", _same_bytes_test(_ext, _source))
for _ext in HTML_ALIASES:
    setattr(TestListedExtensions, f"test_input_{_ext}", _html_alias_test(_ext))


if __name__ == "__main__":
    unittest.main()
