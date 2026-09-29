"""
The vendored tree imports modules that were never copied in.

`ebook_converter/` came from gryf/ebook-converter, which is itself a partial port
of calibre, so a number of imports point at modules that do not exist here.  They
are nearly all lazy (inside a function), so they stay invisible until a specific
option or input format is used, and then raise ModuleNotFoundError mid-conversion.

This pins the remaining gaps: anything left in BASELINE is a known dead code path
kept only because deleting it would cost more than it saves.  A new entry means
fresh rot.

Run:  python -m pytest tests/test_vendored_tree.py -v
  or: python -m unittest tests.test_vendored_tree -v
"""

import importlib.util
import os
import re
import unittest

PACKAGE_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ebook_converter")

IMPORT = re.compile(r"^\s*(?:from|import)\s+(ebook_converter[\w.]*)", re.M)

BASELINE = {
    "ebook_converter.db.categories",
    # Library-management leftovers: reachable only from calibre database code
    # that this fork does not ship, never from a conversion.
    "ebook_converter.db.categories",
    "ebook_converter.ebooks.metadata.book.serialize",
    "ebook_converter.ebooks.tweak",
    "ebook_converter.utils.ipc.simple_worker",
}


def _is_vendored(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, AttributeError):  # a parent package is missing too
        return False


def _missing_modules():
    referenced = set()
    for root, dirs, files in os.walk(PACKAGE_ROOT):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as handle:
                referenced |= set(IMPORT.findall(handle.read()))
    return {module for module in referenced if not _is_vendored(module)}


class TestVendoredTree(unittest.TestCase):
    """Imports of modules that were never vendored must not grow."""

    def test_missing_modules_match_baseline(self):
        self.assertEqual(_missing_modules(), BASELINE)


if __name__ == "__main__":
    unittest.main()
