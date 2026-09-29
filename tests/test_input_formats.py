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

from tests.support import SEED_EPUB, TempDirTestCase, convert

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
    setattr(TestInputFormats, f"test_input_{_fmt}_opf", _dir_test(_fmt))
for _ext in TXT_ALIASES:
    setattr(TestInputFormats, f"test_input_{_ext}", _alias_test(_ext))


if __name__ == "__main__":
    unittest.main()
