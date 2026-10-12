"""
Round-trip EPUB -> format -> EPUB and check internal links still resolve and
images survive. Guards against "links stop working" / "pictures get lost".
"""

import io
import posixpath
import re
import unittest
import zipfile

from PIL import Image

from tests.support import TempDirTestCase, convert

COLORS = {"red": (255, 0, 0), "blue": (0, 0, 255), "green": (0, 128, 0)}
BOOK_COLORS = {"red", "blue"}


def _image(fmt, color):
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buf, fmt)
    return buf.getvalue()


def make_linked_epub(path, quirks=False):
    """Two chapters linking to each other, a non-ASCII PNG and a GIF.

    ``quirks`` mimics real publisher EPUBs: an HTML cover page whose cover
    meta holds an href instead of an id, and a PNG declared as text/plain.
    """
    png_type = "text/plain" if quirks else "image/png"
    cover_meta = '<meta name="cover" content="images/cover.jpg"/>' if quirks else ""
    cover_items = (
        '<item id="cov" href="text/cover.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="covimg" href="images/cover.jpg" media-type="image/jpeg"/>'
        if quirks
        else ""
    )
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="2.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Links</dc:title>'
        '<dc:language>en</dc:language><dc:identifier id="uid">links-1</dc:identifier>' + cover_meta + "</metadata>"
        "<manifest>" + cover_items + '<item id="c1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="c2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="i1" href="images/%C5%BElu%C5%A5.png" media-type="' + png_type + '"/>'
        '<item id="i2" href="images/pic.gif" media-type="image/gif"/>'
        "</manifest><spine>"
        + ('<itemref idref="cov"/>' if quirks else "")
        + '<itemref idref="c1"/><itemref idref="c2"/></spine>'
        + ('<guide><reference type="cover" title="Cover" href="text/cover.xhtml"/></guide>' if quirks else "")
        + "</package>"
    )
    pad = "<p>" + "lorem ipsum " * 50 + "</p>"
    head = '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>'
    ch1 = (
        head
        + '<h1>One</h1><p><a href="ch2.xhtml#target">CROSSLINK</a></p>'
        + pad * 3
        + '<p><img src="../images/%C5%BElu%C5%A5.png" alt="png"/></p></body></html>'
    )
    ch2 = (
        head + "<h1>Two</h1>" + pad * 3 + '<p id="target">TARGET</p>'
        '<p><img src="../images/pic.gif" alt="gif"/></p><p><a href="ch1.xhtml">BACKLINK</a></p></body></html>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
        )
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/text/ch1.xhtml", ch1)
        zf.writestr("OEBPS/text/ch2.xhtml", ch2)
        zf.writestr("OEBPS/images/žluť.png", _image("PNG", COLORS["red"]))
        zf.writestr("OEBPS/images/pic.gif", _image("GIF", COLORS["blue"]))
        if quirks:
            zf.writestr("OEBPS/images/cover.jpg", _image("JPEG", COLORS["green"]))
            zf.writestr(
                "OEBPS/text/cover.xhtml",
                head + '<div><img src="../images/cover.jpg" alt="cover"/></div></body></html>',
            )


def _dominant_color(data):
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None
    px = img.getpixel((img.width // 2, img.height // 2))
    return min(COLORS, key=lambda name: sum((a - b) ** 2 for a, b in zip(COLORS[name], px)))


class TestLinksAndImagesRoundTrip(TempDirTestCase):
    quirks = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._epub = f"{cls._tmpdir}/links.epub"
        make_linked_epub(cls._epub, quirks=cls.quirks)

    def _roundtrip(self, fmt):
        out, back = self.tmp_path(f"out.{fmt}"), self.tmp_path(f"back_{fmt}.epub")
        convert(self._epub, out)
        convert(out, back)
        with zipfile.ZipFile(back) as zf:
            docs = {
                posixpath.basename(n): zf.read(n).decode("utf-8") for n in zf.namelist() if re.search(r"\.x?html?$", n)
            }
            images = {_dominant_color(zf.read(n)) for n in zf.namelist() if re.search(r"\.(png|jpe?g|gif)$", n)}
        return docs, images

    def _assert_links_and_images(self, fmt):
        docs, images = self._roundtrip(fmt)
        ids = {(name, i) for name, html in docs.items() for i in re.findall(r'\bid="([^"]+)"', html)}
        for label in ("CROSSLINK", "BACKLINK"):
            hrefs = [
                (name, href)
                for name, html in docs.items()
                for href in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(?:<[^>]+>)*' + label, html)
            ]
            self.assertTrue(hrefs, f"{fmt}: {label} lost its hyperlink")
            for name, href in hrefs:
                target, _, frag = href.partition("#")
                target = posixpath.basename(target) or name
                self.assertIn(target, docs, f"{fmt}: {label} -> {href} points to a missing file")
                if frag:
                    self.assertIn((target, frag), ids, f"{fmt}: {label} -> {href} points to a missing anchor")
        self.assertLessEqual(BOOK_COLORS, images, f"{fmt}: images lost")


def _roundtrip_test(fmt):
    def test(self):
        self._assert_links_and_images(fmt)

    test.__doc__ = f"EPUB -> {fmt.upper()} -> EPUB keeps links and images"
    return test


for _fmt in ("epub", "azw3", "mobi", "docx", "htmlz"):
    setattr(TestLinksAndImagesRoundTrip, f"test_roundtrip_{_fmt}", _roundtrip_test(_fmt))


class TestKindleWithPublisherQuirks(TestLinksAndImagesRoundTrip):
    """Real-world EPUB quirks that crashed EPUB -> MOBI/AZW3."""

    quirks = True

    def test_cover_is_kept(self):
        out = self.tmp_path("cover.azw3")
        back = self.tmp_path("cover_back.epub")
        convert(self._epub, out)
        convert(out, back)
        with zipfile.ZipFile(back) as zf:
            colors = {_dominant_color(zf.read(n)) for n in zf.namelist() if re.search(r"\.(png|jpe?g|gif)$", n)}
        self.assertIn("green", colors, "azw3: cover image lost")


for _name in [n for n in vars(TestLinksAndImagesRoundTrip) if n.startswith("test_roundtrip_")]:
    if _name not in ("test_roundtrip_azw3", "test_roundtrip_mobi"):
        setattr(TestKindleWithPublisherQuirks, _name, None)


class TestFb2Images(TempDirTestCase):
    def test_gif_is_embedded(self):
        out = self.tmp_path("out.fb2")
        epub = self.tmp_path("links.epub")
        make_linked_epub(epub)
        convert(epub, out)
        with open(out, encoding="utf-8") as fh:
            fb2 = fh.read()
        self.assertEqual(fb2.count("<binary "), 2, "fb2: an image was dropped")


if __name__ == "__main__":
    unittest.main()
