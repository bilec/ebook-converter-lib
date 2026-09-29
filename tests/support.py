"""
Shared fixtures and helpers for the conversion suite.

Kept free of pytest-only constructs so the modules here still run under
``python -m unittest``.
"""

import os
import shutil
import struct
import tempfile
import time
import unittest
import zipfile

# Every output format registered by the builtin plugins.
OUTPUT_FORMATS = [
    "azw3",
    "docx",
    "epub",
    "fb2",
    "html",
    "htmlz",
    "lrf",
    "mobi",
    "oeb",
    "txt",
    "txtz",
]

# The Yellow Wallpaper (Gilman, 1892), Project Gutenberg ebook #1952: public
# domain, redistributed unmodified with the Gutenberg header intact per its
# licence clause 1.E.1.  Test-only, never packaged into the sdist or wheel.
SEED_EPUB = os.path.join(os.path.dirname(__file__), "fixtures", "pg1952.epub")


def convert(src, dest):
    """Run a conversion through the real pipeline."""
    from ebook_converter import logging
    from ebook_converter.ebooks.conversion.plumber import Plumber

    Plumber(src, dest, logging.default_log).run()


def html_of(epub_path):
    """Concatenate the HTML payload of an EPUB, for content assertions."""
    with zipfile.ZipFile(epub_path) as archive:
        return "".join(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".html"))


def make_minimal_epub(path):
    """Create the smallest valid EPUB 2 file possible."""
    container_xml = (
        '<?xml version="1.0"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Test Book</dc:title>"
        "<dc:language>en</dc:language>"
        '<dc:identifier id="uid">test-book-001</dc:identifier>'
        "<dc:creator>Test Author</dc:creator>"
        "</metadata>"
        "<manifest>"
        '<item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>'
        "</manifest>"
        '<spine><itemref idref="ch1"/></spine>'
        "</package>"
    )
    chapter_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        "<head><title>Chapter 1</title></head>"
        "<body><h1>Chapter 1</h1><p>Hello, world.</p></body>"
        "</html>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("content.opf", content_opf)
        zf.writestr("chapter1.xhtml", chapter_xhtml)


def make_minimal_odt(path):
    """Create the smallest ODT the reader accepts; text:h needs an outline level."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text", zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/manifest.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"'
            ' manifest:version="1.2">'
            '<manifest:file-entry manifest:full-path="/"'
            ' manifest:media-type="application/vnd.oasis.opendocument.text"/>'
            '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
            "</manifest:manifest>",
        )
        zf.writestr(
            "content.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">'
            "<office:body><office:text>"
            '<text:h text:outline-level="1">Chapter 1</text:h>'
            "<text:p>Hello, world.</text:p>"
            "</office:text></office:body></office:document-content>",
        )
        zf.writestr(
            "styles.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
            ' office:version="1.2"/>',
        )
        zf.writestr(
            "meta.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" office:version="1.2">'
            "<office:meta><dc:title>Test Book</dc:title></office:meta></office:document-meta>",
        )


def make_minimal_rtf(path):
    with open(path, "wb") as handle:
        handle.write(
            rb"{\rtf1\ansi\deff0{\fonttbl{\f0 Times New Roman;}}"
            rb"\f0\fs24 Chapter 1\par Hello, world.\par}"
        )


def make_minimal_pdb(path):
    """Create an uncompressed PalmDOC container (identity TEXtREAd)."""
    text = b"Chapter 1\r\n\r\nHello, world.\r\n"
    records = [text[index : index + 4096] for index in range(0, len(text), 4096)]
    sections = [struct.pack(">HHIHHI", 1, 0, len(text), len(records), 4096, 0)] + records

    offset = 78 + len(sections) * 8 + 2
    record_info = b""
    for index, section in enumerate(sections):
        record_info += struct.pack(">IBBH", offset, 0, 0, index)
        offset += len(section)

    stamp = int(time.time()) + 2082844800  # Palm epoch is 1904-01-01
    header = struct.pack(
        ">32shhIIIIII4s4sIIh",
        b"TestBook".ljust(32, b"\0"),
        0,
        0,
        stamp,
        stamp,
        0,
        0,
        0,
        0,
        b"TEXt",
        b"REAd",
        0,
        0,
        len(sections),
    )
    with open(path, "wb") as handle:
        handle.write(header + record_info + b"\0\0" + b"".join(sections))


class TempDirTestCase(unittest.TestCase):
    """Class-scoped temp directory, removed when the class finishes."""

    prefix = "econverter_test_"

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix=cls.prefix)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def tmp_path(self, name):
        return os.path.join(self._tmpdir, name)

    def assert_artifact(self, path, label=""):
        """Assert a conversion produced a non-empty file or directory."""
        label = label or os.path.basename(path)
        if os.path.isdir(path):
            self.assertTrue(os.listdir(path), f"{label}: output directory is empty")
        else:
            self.assertTrue(os.path.isfile(path), f"{label}: output file not created")
            self.assertGreater(os.path.getsize(path), 0, f"{label}: output file is empty")


class MinimalEpubTestCase(TempDirTestCase):
    """Temp directory plus a synthetic minimal EPUB at ``self._epub``."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._epub = os.path.join(cls._tmpdir, "test.epub")
        make_minimal_epub(cls._epub)
