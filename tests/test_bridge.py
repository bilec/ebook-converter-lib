import io
import os
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from lxml import etree

from ebook_converter_lib import check_deps_str, convert
from ebook_converter_lib.bridge import _parse_extra_args


def _make_metadata_epub(source, version):
    from tests.support import make_minimal_epub

    make_minimal_epub(source)
    with ZipFile(source) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(source, "w") as archive:
        for info, data in entries:
            if info.filename == "content.opf":
                root = etree.fromstring(data)
                root.set("version", version)
                metadata = root.find("{http://www.idpf.org/2007/opf}metadata")
                etree.SubElement(metadata, "{http://www.idpf.org/2007/opf}meta", name="custom:keep", content="original")
                etree.SubElement(metadata, "{http://purl.org/dc/elements/1.1/}publisher").text = "Original publisher"
                etree.SubElement(
                    metadata,
                    "{http://purl.org/dc/elements/1.1/}description",
                ).text = "Original description"
                if version == "3.0":
                    creator = metadata.find("{http://purl.org/dc/elements/1.1/}creator")
                    creator.set("id", "original-author")
                    etree.SubElement(
                        metadata,
                        "{http://www.idpf.org/2007/opf}meta",
                        refines="#original-author",
                        property="role",
                        scheme="marc:relators",
                    ).text = "aut"
                    etree.SubElement(
                        metadata,
                        "{http://purl.org/dc/elements/1.1/}contributor",
                        id="translator",
                    ).text = "Original translator"
                    etree.SubElement(
                        metadata,
                        "{http://www.idpf.org/2007/opf}meta",
                        refines="#translator",
                        property="role",
                        scheme="marc:relators",
                    ).text = "trl"
                data = etree.tostring(root)
            archive.writestr(info, data)


def test_public_convert_is_bridge_function():
    assert convert.__module__ == "ebook_converter_lib.bridge"


@pytest.mark.parametrize("text", ["Plain text", "\u010cesk\u00fd text", "Let \U0001d434 be a set \U0001f4d6"])
def test_markdown_to_txt_without_libxml2_ucs4(tmp_path, monkeypatch, text):
    fromstring = etree.fromstring

    def chaquopy_fromstring(content, *args, **kwargs):
        if isinstance(content, str) and any(ord(char) > 0xFFFF for char in content):
            raise etree.XMLSyntaxError("Char 0x0 out of allowed range", 9, 1, 2, "<string>")
        return fromstring(content, *args, **kwargs)

    source, output = tmp_path / "book.md", tmp_path / "book.txt"
    source.write_text(f"# Heading\n\n{text}\n", encoding="utf-8")
    monkeypatch.setattr(etree, "fromstring", chaquopy_fromstring)
    result = convert(source, output)
    assert result["success"], result["message"]
    assert text in output.read_text(encoding="utf-8")


@pytest.fixture(params=["azw3", "old", "both"])
def kindle_book(tmp_path, request):
    from PIL import Image

    kind = request.param
    epub = tmp_path / "book.epub"
    _make_metadata_epub(epub, "2.0")
    image = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(image, "PNG")
    with ZipFile(epub) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(epub, "w") as archive:
        for info, data in entries:
            if info.filename == "content.opf":
                root = etree.fromstring(data)
                manifest = root.find("{http://www.idpf.org/2007/opf}manifest")
                etree.SubElement(
                    manifest,
                    "{http://www.idpf.org/2007/opf}item",
                    id="image",
                    href="image.png",
                    **{"media-type": "image/png"},
                )
                data = etree.tostring(root)
            elif info.filename == "chapter1.xhtml":
                root = etree.fromstring(data)
                body = root.find("{http://www.w3.org/1999/xhtml}body")
                etree.SubElement(body, "{http://www.w3.org/1999/xhtml}img", src="image.png", alt="Red square")
                data = etree.tostring(root)
            archive.writestr(info, data)
        archive.writestr("image.png", image.getvalue())
    extension = "azw3" if kind == "azw3" else "mobi"
    source, output = tmp_path / f"in.{extension}", tmp_path / f"out.{extension}"
    args = () if kind == "azw3" else ("--mobi-file-type", kind)
    conversion = convert(epub, source, *args)
    assert conversion["success"], conversion["message"]
    return source, output


def _palm_records(data):
    count = struct.unpack_from(">H", data, 76)[0]
    offsets = [struct.unpack_from(">I", data, 78 + index * 8)[0] for index in range(count)]
    return [data[start:stop] for start, stop in zip(offsets, offsets[1:] + [len(data)])]


def test_kindle_metadata_round_trip_preserves_source(kindle_book, monkeypatch):
    from ebook_converter.ebooks.conversion.plumber import Plumber
    from ebook_converter.ebooks.mobi.reader.headers import BookHeader, MetadataHeader
    from ebook_converter.logging import default_log
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = kindle_book
    monkeypatch.setattr(Plumber, "run", lambda self: pytest.fail("Metadata updates must not convert"))
    original = source.read_bytes()
    before = read_metadata(source)
    assert before["success"], before["message"]
    assert before["metadata"]["title"] == "Test Book"
    result = update_metadata(source, output, title="New & title", authors=["First Author", "Second Author"])
    assert result["success"], result["message"]
    assert source.read_bytes() == original
    after = read_metadata(output)
    assert after["success"], after["message"]
    assert after["metadata"] == {
        "title": "New & title",
        "authors": ["First Author", "Second Author"],
        "publisher": "Original publisher",
        "comments": "Original description",
    }
    before_records, after_records = _palm_records(original), _palm_records(output.read_bytes())
    assert len(before_records) == len(after_records)
    assert any(record.startswith(b"\x89PNG") or record.startswith(b"\xff\xd8") for record in before_records)
    metadata_sections = {0}
    with source.open("rb") as stream:
        header = MetadataHeader(stream, default_log)
        if header.kf8_type == "joint":
            metadata_sections.add(header.exth.kf8_header)
    for index, (before_record, after_record) in enumerate(zip(before_records, after_records)):
        if index not in metadata_sections:
            assert before_record == after_record
        else:
            header = BookHeader(after_record, b"BOOKMOBI", None, default_log)
            assert header.title == "New & title"
            assert header.exth.mi.authors == ["First Author", "Second Author"]


def test_kindle_metadata_clears_only_requested_fields(kindle_book):
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = kindle_book
    result = update_metadata(source, output, publisher="", comments="")
    assert result["success"], result["message"]
    assert read_metadata(output)["metadata"] == {
        "title": "Test Book",
        "authors": ["Test Author"],
        "publisher": "",
        "comments": "",
    }
    repeated = update_metadata(output, source.with_name("again" + source.suffix), title="Longer title" * 50)
    assert repeated["success"], repeated["message"]


def test_kindle_metadata_noop_is_identical(kindle_book):
    from ebook_converter_lib import update_metadata

    source, output = kindle_book
    result = update_metadata(source, output)
    assert result["success"], result["message"]
    assert source.read_bytes() == output.read_bytes()


def test_kindle_metadata_unicode_round_trip(kindle_book):
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = kindle_book
    fields = {
        "title": "\u010cesk\u00fd title \U0001f4d6",
        "authors": ["Jos\u00e9", "\u674e"],
        "comments": "<p>New & text</p>",
    }
    result = update_metadata(source, output, **fields)
    assert result["success"], result["message"]
    assert read_metadata(output)["metadata"] == {**fields, "publisher": "Original publisher"}


@pytest.mark.parametrize("title, success", [("Jos\u00e9's book", True), ("\u674e's book", False)])
def test_kindle_metadata_respects_windows_1252_encoding(kindle_book, title, success):
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = kindle_book
    data = bytearray(source.read_bytes())
    first = struct.unpack_from(">I", data, 78)[0]
    struct.pack_into(">I", data, first + 28, 1252)
    source.write_bytes(data)
    output.write_bytes(b"Existing output")
    result = update_metadata(source, output, title=title)
    assert result["success"] is success, result["message"]
    assert source.read_bytes() == data
    if success:
        assert read_metadata(output)["metadata"]["title"] == title
    else:
        assert output.read_bytes() == b"Existing output"


def test_kindle_metadata_creates_missing_exth(kindle_book):
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = kindle_book
    data = bytearray(source.read_bytes())
    first = struct.unpack_from(">I", data, 78)[0]
    flags = struct.unpack_from(">I", data, first + 128)[0]
    struct.pack_into(">I", data, first + 128, flags & ~0x40)
    source.write_bytes(data)
    result = update_metadata(source, output, title="Added metadata", authors=["New Author"])
    assert result["success"], result["message"]
    assert read_metadata(output)["metadata"] == {
        "title": "Added metadata",
        "authors": ["New Author"],
        "publisher": "",
        "comments": "",
    }


def test_kindle_metadata_preserves_unknown_and_repeated_exth(kindle_book):
    from ebook_converter_lib import update_metadata

    source, output = kindle_book
    data = bytearray(source.read_bytes())
    first = struct.unpack_from(">I", data, 78)[0]
    length = struct.unpack_from(">I", data, first + 20)[0]
    position = first + 16 + length + 12
    count = struct.unpack_from(">I", data, first + 16 + length + 8)[0]
    preserved = []
    for index in range(count):
        code, size = struct.unpack_from(">II", data, position)
        if code in (101, 103):
            struct.pack_into(">I", data, position, 999)
            preserved.append(bytes(data[position : position + size]))
        position += size
    assert len(preserved) == 2
    source.write_bytes(data)
    result = update_metadata(source, output, title="Only title changes")
    assert result["success"], result["message"]
    for record in preserved:
        assert record in _palm_records(output.read_bytes())[0]


@pytest.mark.parametrize("damage", ["drm", "offsets", "exth", "truncated", "identity"])
def test_kindle_metadata_rejects_invalid_input_without_overwriting(kindle_book, damage):
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = kindle_book
    data = bytearray(source.read_bytes())
    first = struct.unpack_from(">I", data, 78)[0]
    if damage == "drm":
        struct.pack_into(">H", data, first + 12, 1)
    elif damage == "offsets":
        struct.pack_into(">I", data, 86, len(data) + 1)
    elif damage == "exth":
        length = struct.unpack_from(">I", data, first + 20)[0]
        struct.pack_into(">I", data, first + 16 + length + 16, 0)
    elif damage == "truncated":
        data = data[: first + 20]
    else:
        data[60:68] = b"TEXtREAd"
    source.write_bytes(data)
    output.write_bytes(b"Existing output")
    result = update_metadata(source, output, title="New title")
    assert not result["success"]
    assert read_metadata(source)["metadata"] is None
    assert source.read_bytes() == data
    assert output.read_bytes() == b"Existing output"
    assert set(source.parent.iterdir()) == {source, output, source.with_name("book.epub")}


@pytest.mark.parametrize("kind", ["same", "symlink", "hardlink", "different-extension", "invalid-authors"])
def test_kindle_metadata_preserves_files_on_invalid_request(kindle_book, kind):
    from ebook_converter_lib import update_metadata

    source, output = kindle_book
    fields = {"title": "New title"}
    if kind == "same":
        output = source
    elif kind == "symlink":
        output.symlink_to(source)
    elif kind == "hardlink":
        os.link(source, output)
    else:
        if kind == "different-extension":
            output = output.with_suffix(".epub")
        else:
            fields = {"authors": []}
        output.write_bytes(b"Existing output")
    original, existing = source.read_bytes(), output.read_bytes()
    result = update_metadata(source, output, **fields)
    assert not result["success"]
    assert source.read_bytes() == original
    assert output.read_bytes() == existing


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_read_metadata_returns_prefill_fields_without_modifying_epub(tmp_path, version):
    from ebook_converter_lib import read_metadata

    source = tmp_path / "book.epub"
    _make_metadata_epub(source, version)
    original = source.read_bytes()

    result = read_metadata(source)

    assert result["success"], result["message"]
    assert result["metadata"] == {
        "title": "Test Book",
        "authors": ["Test Author"],
        "publisher": "Original publisher",
        "comments": "Original description",
    }
    assert source.read_bytes() == original


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_read_metadata_matches_updated_fields(tmp_path, version):
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = tmp_path / "in.epub", tmp_path / "out.epub"
    _make_metadata_epub(source, version)
    update = update_metadata(
        source,
        output,
        title="New & title",
        authors=["Research & Development", "Second Author"],
        comments="",
    )
    assert update["success"], update["message"]

    result = read_metadata(output)

    assert result["success"], result["message"]
    assert result["metadata"] == {
        "title": "New & title",
        "authors": ["Research & Development", "Second Author"],
        "publisher": "Original publisher",
        "comments": "",
    }


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_metadata_uses_default_rendition_without_changing_alternate(tmp_path, version):
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = tmp_path / "in.epub", tmp_path / "out.epub"
    _make_metadata_epub(source, version)
    with ZipFile(source) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
        alternate = etree.fromstring(archive.read("content.opf"))
    alternate.find(".//{http://purl.org/dc/elements/1.1/}title").text = "Alternate title"
    alternate_bytes = etree.tostring(alternate)
    with ZipFile(source, "w") as archive:
        for info, payload in entries:
            if info.filename == "META-INF/container.xml":
                container = etree.fromstring(payload)
                rootfiles = container.find("{urn:oasis:names:tc:opendocument:xmlns:container}rootfiles")
                etree.SubElement(
                    rootfiles,
                    "{urn:oasis:names:tc:opendocument:xmlns:container}rootfile",
                    **{"full-path": "alternate.opf", "media-type": "application/oebps-package+xml"},
                )
                payload = etree.tostring(container)
            archive.writestr(info, payload)
        archive.writestr("alternate.opf", alternate_bytes)
    original = source.read_bytes()

    read = read_metadata(source)
    update = update_metadata(source, output, title="Updated default")

    assert read["success"], read["message"]
    assert read["metadata"]["title"] == "Test Book"
    assert update["success"], update["message"]
    assert source.read_bytes() == original
    assert read_metadata(output)["metadata"]["title"] == "Updated default"
    with ZipFile(output) as archive:
        default = etree.fromstring(archive.read("content.opf"))
        assert default.find(".//{http://purl.org/dc/elements/1.1/}title").text == "Updated default"
        assert archive.read("alternate.opf") == alternate_bytes


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_read_metadata_returns_empty_values_for_missing_fields(tmp_path, version):
    from ebook_converter_lib import read_metadata

    source = tmp_path / "book.epub"
    _make_metadata_epub(source, version)
    with ZipFile(source) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(source, "w") as archive:
        for info, data in entries:
            if info.filename == "content.opf":
                root = etree.fromstring(data)
                metadata = root.find("{http://www.idpf.org/2007/opf}metadata")
                for node in list(metadata):
                    if etree.QName(node).localname not in ("language", "identifier"):
                        metadata.remove(node)
                data = etree.tostring(root)
            archive.writestr(info, data)
    original = source.read_bytes()

    result = read_metadata(source)

    assert result["success"], result["message"]
    assert result["metadata"] == {"title": "", "authors": [], "publisher": "", "comments": ""}
    assert source.read_bytes() == original


@pytest.mark.parametrize("kind", ["missing", "invalid", "unsupported"])
def test_read_metadata_reports_failure_without_prefill_data(tmp_path, kind):
    from ebook_converter_lib import read_metadata

    source = tmp_path / ("book.pdf" if kind == "unsupported" else "book.epub")
    if kind != "missing":
        source.write_bytes(b"not an EPUB")

    result = read_metadata(source)

    assert not result["success"]
    assert result["message"]
    assert result["metadata"] is None
    if source.exists():
        assert source.read_bytes() == b"not an EPUB"


@pytest.mark.parametrize("version", ["2.0", "3.0"])
@pytest.mark.parametrize("entry", ["META-INF/container.xml", "content.opf"])
def test_metadata_rejects_malformed_xml_without_repairing_or_overwriting(tmp_path, version, entry):
    from ebook_converter_lib import read_metadata, update_metadata

    source, output = tmp_path / "in.epub", tmp_path / "out.epub"
    _make_metadata_epub(source, version)
    with ZipFile(source) as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(source, "w") as archive:
        for info, payload in entries:
            if info.filename == entry:
                payload = payload[: payload.rfind(b"</")]
            archive.writestr(info, payload)
    original = source.read_bytes()
    output.write_bytes(b"existing output")

    read = read_metadata(source)
    update = update_metadata(source, output, title="Changed")

    assert not read["success"]
    assert read["metadata"] is None
    assert not update["success"]
    assert source.read_bytes() == original
    assert output.read_bytes() == b"existing output"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["in.epub", "out.epub"]


def test_update_metadata_preserves_zip_archive_comment(tmp_path):
    from ebook_converter_lib import update_metadata

    source, output = tmp_path / "in.epub", tmp_path / "out.epub"
    _make_metadata_epub(source, "3.0")
    with ZipFile(source, "a") as archive:
        archive.comment = b"Preserve this archive comment"
    original = source.read_bytes()

    result = update_metadata(source, output, title="Changed")

    assert result["success"], result["message"]
    assert source.read_bytes() == original
    with ZipFile(output) as archive:
        assert archive.comment == b"Preserve this archive comment"


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_update_metadata_preserves_source_and_epub_content(tmp_path, version):
    from zipfile import ZIP_STORED

    from ebook_converter_lib import update_metadata

    source = tmp_path / "in.epub"
    output = tmp_path / "out.epub"
    _make_metadata_epub(source, version)
    original = source.read_bytes()

    result = update_metadata(
        source,
        output,
        title="New & title",
        authors=["First Author", "Second Author"],
        publisher="New publisher",
        comments="New description",
    )

    assert result["success"], result["message"]
    assert source.read_bytes() == original
    with ZipFile(source) as before, ZipFile(output) as after:
        assert after.namelist() == before.namelist()
        assert after.getinfo("mimetype").compress_type == ZIP_STORED
        for name in before.namelist():
            if name != "content.opf":
                assert after.read(name) == before.read(name)
        root = etree.fromstring(after.read("content.opf"))
    namespaces = {"dc": "http://purl.org/dc/elements/1.1/"}
    assert root.xpath("//dc:title/text()", namespaces=namespaces) == ["New & title"]
    assert root.xpath("//dc:creator/text()", namespaces=namespaces) == ["First Author", "Second Author"]
    assert root.xpath("//dc:publisher/text()", namespaces=namespaces) == ["New publisher"]
    assert root.xpath("//dc:description/text()", namespaces=namespaces) == ["New description"]
    assert root.xpath("//dc:identifier/text()", namespaces=namespaces) == ["test-book-001"]
    assert root.xpath("//dc:language/text()", namespaces=namespaces) == ["en"]
    assert root.xpath('//*[local-name()="meta"][@name="custom:keep"]/@content') == ["original"]
    assert root.get("version") == version
    if version == "3.0":
        assert root.xpath('//*[local-name()="meta"][@property="dcterms:modified"]/text()')
        assert root.xpath("//dc:contributor/text()", namespaces=namespaces) == ["Original translator"]
        assert root.xpath('//*[local-name()="meta"][@refines="#translator"]/text()') == ["trl"]
        assert not root.xpath('//*[local-name()="meta"][@refines="#original-author"]')


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_update_metadata_can_clear_publisher_and_comments_without_changing_authors(tmp_path, version):
    from ebook_converter_lib import update_metadata

    source, output = tmp_path / "in.epub", tmp_path / "out.epub"
    _make_metadata_epub(source, version)
    result = update_metadata(source, output, publisher="", comments="")

    assert result["success"], result["message"]
    with ZipFile(output) as archive:
        root = etree.fromstring(archive.read("content.opf"))
    namespaces = {"dc": "http://purl.org/dc/elements/1.1/"}
    assert not root.xpath("//dc:publisher/text()", namespaces=namespaces)
    assert not root.xpath("//dc:description/text()", namespaces=namespaces)
    assert root.xpath("//dc:creator/text()", namespaces=namespaces) == ["Test Author"]
    assert root.xpath("//dc:title/text()", namespaces=namespaces) == ["Test Book"]
    if version == "3.0":
        assert root.xpath('//*[local-name()="meta"][@refines="#original-author"]/text()') == ["aut"]


def test_update_metadata_changes_only_requested_field_in_real_epub(tmp_path):
    from ebook_converter_lib import update_metadata
    from tests.support import SEED_EPUB

    source = tmp_path / "in.epub"
    output = tmp_path / "out.epub"
    source.write_bytes(Path(SEED_EPUB).read_bytes())
    original = source.read_bytes()
    result = update_metadata(source, output, title="Updated title")

    assert result["success"], result["message"]
    assert source.read_bytes() == original
    with ZipFile(source) as before, ZipFile(output) as after:
        container = etree.fromstring(before.read("META-INF/container.xml"))
        opf_path = container.xpath('//*[local-name()="rootfile"]/@full-path')[0]
        assert after.namelist() == before.namelist()
        for name in before.namelist():
            if name != opf_path:
                assert after.read(name) == before.read(name)
        old_root = etree.fromstring(before.read(opf_path))
        new_root = etree.fromstring(after.read(opf_path))
    namespaces = {"dc": "http://purl.org/dc/elements/1.1/"}
    for name in ("creator", "publisher", "description", "identifier", "language", "subject"):
        assert new_root.xpath(f"//dc:{name}/text()", namespaces=namespaces) == old_root.xpath(
            f"//dc:{name}/text()",
            namespaces=namespaces,
        )
    for name in ("manifest", "spine", "guide"):
        assert [etree.tostring(node) for node in new_root.xpath(f'//*[local-name()="{name}"]')] == [
            etree.tostring(node) for node in old_root.xpath(f'//*[local-name()="{name}"]')
        ]


def test_update_metadata_without_fields_copies_epub_unchanged(tmp_path):
    from ebook_converter_lib import update_metadata
    from tests.support import make_minimal_epub

    source, output = tmp_path / "in.epub", tmp_path / "out.epub"
    make_minimal_epub(source)
    result = update_metadata(source, output)

    assert result["success"], result["message"]
    assert output.read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    "field,value",
    [("title", ""), ("authors", []), ("authors", "Author"), ("authors", [""]), ("publisher", 1)],
)
def test_update_metadata_rejects_invalid_fields_without_overwriting_output(tmp_path, field, value):
    from ebook_converter_lib import update_metadata
    from tests.support import make_minimal_epub

    source, output = tmp_path / "in.epub", tmp_path / "out.epub"
    make_minimal_epub(source)
    output.write_bytes(b"existing output")
    original = source.read_bytes()
    result = update_metadata(source, output, **{field: value})

    assert not result["success"]
    assert source.read_bytes() == original
    assert output.read_bytes() == b"existing output"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["in.epub", "out.epub"]


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_update_metadata_rejects_source_as_output(tmp_path, alias):
    from ebook_converter_lib import update_metadata
    from tests.support import make_minimal_epub

    source = tmp_path / "in.epub"
    make_minimal_epub(source)
    output = source if alias == "same" else tmp_path / "out.epub"
    if alias == "symlink":
        output.symlink_to(source)
    elif alias == "hardlink":
        output.hardlink_to(source)
    original = source.read_bytes()
    result = update_metadata(source, output, title="Changed")

    assert not result["success"]
    assert "different file" in result["message"]
    assert source.read_bytes() == original


def test_update_metadata_invalid_epub_preserves_output_and_removes_temporary_files(tmp_path):
    from ebook_converter_lib import update_metadata

    source, output = tmp_path / "in.epub", tmp_path / "out.epub"
    source.write_bytes(b"not an EPUB")
    output.write_bytes(b"existing output")
    result = update_metadata(source, output, title="Changed")

    assert not result["success"]
    assert source.read_bytes() == b"not an EPUB"
    assert output.read_bytes() == b"existing output"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["in.epub", "out.epub"]


def test_epub_metadata_writer_is_registered():
    from ebook_converter.customize.ui import can_set_metadata

    assert can_set_metadata("epub")


def test_epub_metadata_plugin_updates_through_dispatcher(tmp_path):
    from ebook_converter.customize.ui import set_file_type_metadata
    from ebook_converter.ebooks.metadata.book.base import Metadata
    from tests.support import make_minimal_epub

    path = tmp_path / "book.epub"
    make_minimal_epub(path)
    metadata = Metadata("Plugin title", [])
    with path.open("r+b") as stream:
        set_file_type_metadata(stream, metadata, "epub")
    with ZipFile(path) as archive:
        root = etree.fromstring(archive.read("content.opf"))
    namespaces = {"dc": "http://purl.org/dc/elements/1.1/"}
    assert root.xpath("//dc:title/text()", namespaces=namespaces) == ["Plugin title"]
    assert root.xpath("//dc:creator/text()", namespaces=namespaces) == ["Test Author"]


@pytest.mark.parametrize("version", ["2.0", "3.0"])
@pytest.mark.parametrize("clear", [False, True])
def test_epub_metadata_plugin_clears_optional_fields_only_when_requested(tmp_path, version, clear):
    from contextlib import nullcontext

    from ebook_converter.customize.ui import apply_null_metadata, set_file_type_metadata
    from ebook_converter.ebooks.metadata.book.base import Metadata
    from ebook_converter_lib import read_metadata

    source = tmp_path / "book.epub"
    _make_metadata_epub(source, version)
    metadata = Metadata(None, [])
    metadata.publisher = ""
    metadata.comments = ""
    errors = []
    with source.open("r+b") as stream, apply_null_metadata if clear else nullcontext():
        set_file_type_metadata(stream, metadata, "epub", report_error=lambda *args: errors.append(args))

    assert not errors
    result = read_metadata(source)
    assert result["success"], result["message"]
    assert result["metadata"] == {
        "title": "Test Book",
        "authors": ["Test Author"],
        "publisher": "" if clear else "Original publisher",
        "comments": "" if clear else "Original description",
    }


@pytest.mark.parametrize("extension, output_extension", [(".mobi", ".epub"), (".pdf", ".pdf"), (".epub", ".azw3")])
def test_update_metadata_rejects_unsupported_or_mismatched_formats(tmp_path, extension, output_extension):
    from ebook_converter_lib import update_metadata

    source, output = tmp_path / ("in" + extension), tmp_path / ("out" + output_extension)
    source.write_bytes(b"unsupported book")
    result = update_metadata(source, output, title="Changed")

    assert not result["success"]
    assert "matching EPUB, AZW3 or MOBI file extensions" in result["message"]
    assert not output.exists()


def test_dependency_check_reports_a_string():
    assert isinstance(check_deps_str(), str)


def test_remove_text_lines_become_search_pattern():
    options = _parse_extra_args(("--remove-text", "-a II E-\nChapter \\d+"))

    assert options["sr1_search"] == r"(?:-a II E-|Chapter \d+)"
    assert options["sr1_replace"] == ""


def test_parse_extra_args_preserves_string_and_boolean_values():
    assert _parse_extra_args(("--base-font-size", "12", "--enable-heuristics")) == {
        "base_font_size": "12",
        "enable_heuristics": True,
    }


def _convert_minimal(tmp_path, *extra_args):
    from tests.support import make_minimal_epub

    src = str(tmp_path / "in.epub")
    make_minimal_epub(src)
    return convert(src, str(tmp_path / "out.epub"), *extra_args)


def test_convert_leaves_no_temp_files(tmp_path):
    from ebook_converter.ptempfile import base_dir

    assert _convert_minimal(tmp_path)["success"]
    assert os.listdir(base_dir()) == []


def test_invalid_remove_text_pattern_fails_instead_of_being_ignored(tmp_path):
    result = _convert_minimal(tmp_path, "--remove-text", "Chapter 1\nNote (draft")

    assert not result["success"]
    assert "Note (draft" in result["message"]


def test_remove_text_lines_valid_alone_but_not_joined_fail(tmp_path):
    result = _convert_minimal(tmp_path, "--remove-text", "Chapter 1\n(?i)note")

    assert not result["success"]
    assert "(?i)note" in result["message"]


def test_unknown_option_fails_instead_of_being_ignored(tmp_path):
    result = _convert_minimal(tmp_path, "--marign-top", "5")

    assert not result["success"]
    assert "--marign-top" in result["message"]


def test_stray_argument_fails_instead_of_being_ignored(tmp_path):
    result = _convert_minimal(tmp_path, "--title", "My", "Book")

    assert not result["success"]
    assert "Book" in result["message"]


def test_encoding_detection_normalizes_missing_confidence(monkeypatch):
    from ebook_converter.ebooks.chardet import detect

    monkeypatch.setitem(
        sys.modules,
        "chardet",
        SimpleNamespace(detect=lambda _: {"encoding": "utf-8", "confidence": None}),
    )

    assert detect(b"plain text")["confidence"] == 0.0
