import os
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


@pytest.mark.parametrize("extension", [".mobi", ".pdf"])
def test_update_metadata_rejects_non_epub_formats(tmp_path, extension):
    from ebook_converter_lib import update_metadata

    source, output = tmp_path / ("in" + extension), tmp_path / "out.epub"
    source.write_bytes(b"unsupported book")
    result = update_metadata(source, output, title="Changed")

    assert not result["success"]
    assert "EPUB files only" in result["message"]
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
