"""
Regression tests for PDF input conversion.

PDF is the one input format the round-trip suite cannot reach, since we never
emit PDF.

Run:  python -m pytest tests/test_input_pdf.py -v
  or: python -m unittest tests.test_input_pdf -v
"""

import os
import unittest
import zipfile
from unittest.mock import patch

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from tests.support import TempDirTestCase, convert, html_of


def _make_minimal_pdf(path):
    document = canvas.Canvas(path, pagesize=letter)
    document.setTitle("Spacing Title")
    document.setAuthor("Ada Lovelace")
    for number in range(1, 4):
        document.bookmarkPage(f"chapter{number}")
        document.addOutlineEntry(f"Chapter {number}", f"chapter{number}", level=0)
        document.drawString(50, 750, f"Chapter {number} body")
        if number == 1:
            # TeX-style: words positioned apart without space glyphs
            x = 50
            for word in ("discrete", "structures", "graphs"):
                document.drawString(x, 700, word)
                x += document.stringWidth(word, "Helvetica", 12) + 3.3
            document.drawString(50, 650, "Café")
        document.showPage()
    document.save()


def _make_image_pdf(path, jpeg_path, png_path):
    from PIL import Image

    Image.new("RGB", (64, 48), "red").save(jpeg_path, quality=90)
    Image.new("RGB", (64, 48), "blue").save(png_path)
    document = canvas.Canvas(path, pagesize=letter)
    document.drawString(50, 750, "Before image")
    document.drawImage(jpeg_path, 50, 550, width=160, height=120)
    document.drawString(50, 500, "Between images")
    document.drawImage(png_path, 50, 300, width=160, height=120)
    document.drawString(50, 250, "After image")
    document.showPage()
    document.save()


class TestPDFImages(TempDirTestCase):
    """Images embedded in a PDF land in the book where they sit on the page."""

    prefix = "econverter_test_pdf_images_"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._jpeg = os.path.join(cls._tmpdir, "photo.jpg")
        cls._pdf = os.path.join(cls._tmpdir, "images.pdf")
        _make_image_pdf(cls._pdf, cls._jpeg, os.path.join(cls._tmpdir, "chart.png"))

    def _body(self, epub):
        with zipfile.ZipFile(epub) as archive:
            pages = (archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".html"))
            return next(page for page in pages if "Before image" in page)

    def test_images_sit_between_the_surrounding_text(self):
        epub = self.tmp_path("images.epub")
        convert(self._pdf, epub)

        body = self._body(epub)
        first = body.index("<img")
        second = body.index("<img", first + 1)
        self.assertLess(body.index("Before image"), first)
        self.assertLess(first, body.index("Between images"))
        self.assertLess(body.index("Between images"), second)
        self.assertLess(second, body.index("After image"))

    def test_jpeg_is_kept_byte_for_byte(self):
        epub = self.tmp_path("jpeg.epub")
        convert(self._pdf, epub)

        with open(self._jpeg, "rb") as original, zipfile.ZipFile(epub) as archive:
            data = original.read()
            self.assertIn(data, [archive.read(name) for name in archive.namelist()])

    def test_no_images_option_skips_them(self):
        import converter

        epub = self.tmp_path("no-images.epub")
        result = converter.convert(self._pdf, epub, "--no-images")

        self.assertTrue(result["success"], result["message"])
        self.assertNotIn("<img", self._body(epub))


def _make_figure_pdf(path, inner_image_path):
    from PIL import Image

    Image.new("RGB", (16, 16), "green").save(inner_image_path)
    document = canvas.Canvas(path, pagesize=letter)
    document.drawString(50, 740, "Before figure")
    # A small graph drawn with vector paths, labelled like TikZ output
    nodes = {"v1": (100, 640), "v2": (220, 640), "v3": (160, 540)}
    for a, b in (("v1", "v2"), ("v2", "v3"), ("v3", "v1")):
        document.line(*nodes[a], *nodes[b])
    document.setFont("Helvetica", 9)
    for label, (x, y) in nodes.items():
        document.circle(x, y, 4, fill=1)
        document.drawString(x + 6, y + 4, label)
    # Already part of the rendered figure, so it must not be saved again
    document.drawImage(inner_image_path, 150, 600, width=16, height=16)
    # Off-page drawings must not abort the conversion
    document.circle(730, 630, 20)
    document.line(700, 600, 760, 660)
    document.setFont("Helvetica", 12)
    document.drawString(50, 470, "After figure")
    # Neither a framed paragraph nor a rule is a figure
    document.rect(45, 330, 420, 70)
    document.drawString(50, 380, "This framed paragraph is ordinary prose and stays text.")
    document.drawString(50, 350, "It wraps onto a second line inside the very same frame.")
    document.line(50, 300, 500, 300)
    document.drawString(50, 260, "Closing words")
    document.showPage()
    document.save()


class TestPDFFigures(TempDirTestCase):
    """Vector-drawn figures become images in place; frames and rules stay as they are."""

    prefix = "econverter_test_pdf_figures_"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._pdf = os.path.join(cls._tmpdir, "figures.pdf")
        _make_figure_pdf(cls._pdf, os.path.join(cls._tmpdir, "inner.png"))

    def _body(self, *options):
        import converter

        epub = self.tmp_path("figures%d.epub" % len(options))
        result = converter.convert(self._pdf, epub, *options)
        self.assertTrue(result["success"], result["message"])
        with zipfile.ZipFile(epub) as archive:
            pages = (archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".html"))
            return next(page for page in pages if "Before figure" in page)

    def test_drawn_figure_becomes_one_image_between_its_paragraphs(self):
        body = self._body()

        self.assertEqual(body.count("<img"), 1)
        self.assertLess(body.index("Before figure"), body.index("<img"))
        self.assertLess(body.index("<img"), body.index("After figure"))

    def test_figure_labels_leave_the_text_flow(self):
        body = self._body()

        for label in ("v1", "v2", "v3"):
            self.assertNotIn(label, body)
        self.assertIn("framed paragraph is ordinary prose", body)

    def test_no_images_option_skips_figures(self):
        self.assertNotIn("<img", self._body("--no-images"))


class TestPDFInput(TempDirTestCase):
    """Text-based PDFs can be converted to EPUB."""

    prefix = "econverter_test_pdf_"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._pdf = os.path.join(cls._tmpdir, "test.pdf")
        _make_minimal_pdf(cls._pdf)

    def _epub(self):
        if not hasattr(type(self), "_converted"):
            convert(self._pdf, self.tmp_path("shared.epub"))
            type(self)._converted = self.tmp_path("shared.epub")
        return self._converted

    def _entry(self, suffix):
        with zipfile.ZipFile(self._epub()) as archive:
            name = next(name for name in archive.namelist() if name.endswith(suffix))
            return archive.read(name).decode("utf-8")

    def test_pdf_to_epub_succeeds(self):
        import converter

        output_path = self.tmp_path("output.epub")
        result = converter.convert(self._pdf, output_path)

        self.assertTrue(result["success"], result["message"])
        self.assert_artifact(output_path)
        with zipfile.ZipFile(output_path) as archive:
            self.assertIn("mimetype", archive.namelist())
            self.assertIn("META-INF/container.xml", archive.namelist())
        self.assertIn("Café", html_of(output_path))

    def test_words_positioned_apart_keep_their_spaces(self):
        self.assertIn("discrete structures graphs", html_of(self._epub()))

    def test_outline_becomes_table_of_contents(self):
        ncx = self._entry(".ncx")
        for number in range(1, 4):
            self.assertIn(f"Chapter {number}", ncx)

    def test_title_and_author_come_from_pdf_info(self):
        opf = self._entry(".opf")
        self.assertIn("Spacing Title</dc:title>", opf)
        self.assertIn("Ada Lovelace</dc:creator>", opf)

    def test_first_page_becomes_cover(self):
        self.assertIn('name="cover"', self._entry(".opf"))

    def test_html_preserves_czech_text_without_page_headings(self):
        from ebook_converter.ebooks.pdf.pdftohtml import pdftohtml

        page = type("Page", (), {"get_textpage": lambda self: textpage})()
        textpage = type("TextPage", (), {"get_text_bounded": lambda self: "Český text"})()
        document = type("Doc", (), {"__iter__": lambda self: iter([page]), "get_toc": lambda self: []})()
        output_dir = self.tmp_path("czech")
        os.makedirs(output_dir)
        with patch("pypdfium2.PdfDocument", return_value=document):
            pdftohtml(output_dir, self._pdf, no_images=True)

        with open(os.path.join(output_dir, "index.html"), encoding="utf-8") as index:
            html = index.read()
        self.assertIn("Český text", html)
        self.assertNotIn("<h2>", html)

    def test_html_recovery_preserves_czech_text(self):
        from ebook_converter.ebooks.oeb.parse_utils import parse_html

        document = parse_html(
            "<html><body><p>áľščÁĽŠČ</p></body></html>",
            decoder=lambda data: data,
        )

        self.assertIn("áľščÁĽŠČ", " ".join(document.itertext()))

    def test_html_parse_survives_libxml2_without_ucs4(self):
        # Chaquopy's libxml2 can't decode the UCS-4 buffer lxml passes for non-BMP str (issue #24)
        from lxml import etree

        from ebook_converter.ebooks.oeb.parse_utils import parse_html

        fromstring = etree.fromstring

        def chaquopy_fromstring(text, *args, **kwargs):
            if isinstance(text, str) and any(ord(char) > 0xFFFF for char in text):
                raise etree.XMLSyntaxError("Char 0x0 out of allowed range", 9, 1, 2, "<string>")
            return fromstring(text, *args, **kwargs)

        with patch.object(etree, "fromstring", chaquopy_fromstring):
            document = parse_html("<html><body><p>Let 𝐴 be a set & more</p></body></html>")

        self.assertIn("Let 𝐴 be a set", " ".join(document.itertext()))

    def test_metadata_is_read_without_poppler(self):
        from ebook_converter.ebooks.metadata.pdf import get_metadata

        with open(self._pdf, "rb") as stream, patch("subprocess.check_output", side_effect=FileNotFoundError):
            metadata = get_metadata(stream)

        self.assertEqual(metadata.title, "Spacing Title")
        self.assertEqual(metadata.authors, ["Ada Lovelace"])
        self.assertEqual(metadata.cover_data[0], "jpeg")


if __name__ == "__main__":
    unittest.main()
