"""
The README format list is the PyPI landing page, so it must not drift from the
plugin registry.  Covers both directions, hence its own module.

Run:  python -m pytest tests/test_readme_formats.py -v
  or: python -m unittest tests.test_readme_formats -v
"""

import os
import re
import unittest

from tests.support import OUTPUT_FORMATS

README = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")


def _registry():
    from ebook_converter.customize.builtins import plugins
    from ebook_converter.customize.conversion import InputFormatPlugin, OutputFormatPlugin

    inputs, outputs = set(), set()
    for plugin in plugins:
        if isinstance(plugin, type) and issubclass(plugin, InputFormatPlugin):
            inputs |= set(plugin.file_types)
        if isinstance(plugin, type) and issubclass(plugin, OutputFormatPlugin):
            outputs.add(plugin.file_type)
    return inputs, outputs


def _listed(heading):
    with open(README, encoding="utf-8") as handle:
        section = handle.read().split("## Supported formats", 1)[1]
    line = section.split(f"{heading}:", 1)[1].split(".")[0]
    return set(re.findall(r"`([a-z0-9]+)`", line))


class TestReadmeFormats(unittest.TestCase):
    """README advertises the formats on PyPI, so it must match the plugin registry."""

    def test_readme_input_formats_match_registry(self):
        self.assertEqual(_listed("Input"), _registry()[0])

    def test_readme_output_formats_match_registry(self):
        self.assertEqual(_listed("Output"), _registry()[1])

    def test_output_formats_constant_matches_registry(self):
        self.assertEqual(set(OUTPUT_FORMATS), _registry()[1])


if __name__ == "__main__":
    unittest.main()
