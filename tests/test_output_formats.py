"""
Smoke tests: convert a minimal EPUB to every supported output format.

Each test runs a conversion and asserts the artifact exists and is non-empty.
Failures surface missing modules, missing data files, and runtime crashes —
the most common bugs right now.

Run:  python -m pytest tests/test_output_formats.py -v
  or: python -m unittest tests.test_output_formats -v
"""

import os
import shutil
import unittest

from tests.support import OUTPUT_FORMATS, MinimalEpubTestCase, convert


class TestOutputFormats(MinimalEpubTestCase):
    """Smoke-test EPUB -> every output format."""

    def _convert(self, fmt):
        out_path = self.tmp_path(f"output.{fmt}")
        if os.path.isdir(out_path):
            shutil.rmtree(out_path)
        elif os.path.exists(out_path):
            os.remove(out_path)

        convert(self._epub, out_path)
        self.assert_artifact(out_path, fmt)


def _output_test(fmt):
    def test(self):
        self._convert(fmt)

    test.__doc__ = f"Convert minimal EPUB to {fmt.upper()}"
    return test


for _fmt in OUTPUT_FORMATS:
    setattr(TestOutputFormats, f"test_epub_to_{_fmt}", _output_test(_fmt))


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
