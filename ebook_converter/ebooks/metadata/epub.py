import io

from lxml import etree

from ebook_converter.ebooks.metadata import opf3
from ebook_converter.ebooks.metadata.opf2 import OPF
from ebook_converter.utils.xml_parse import safe_xml_fromstring
from ebook_converter.utils.zipfile import ZipFile, safe_replace

__license__ = 'GPL v3'
__copyright__ = '2008, Kovid Goyal <kovid at kovidgoyal.net>'


class EPubException(ValueError):
    pass


class Container(dict):

    def __init__(self, stream):
        super().__init__()
        container = safe_xml_fromstring(stream.read(), recover=False)
        if container is None:
            raise EPubException('invalid container XML')
        if container.get('version') != '1.0':
            raise EPubException('unsupported version of OCF')
        rootfiles = container.xpath('./*[local-name()="rootfiles"]')
        if not rootfiles:
            raise EPubException('<rootfiles/> element missing')
        for rootfile in rootfiles[0].xpath('./*[local-name()="rootfile"]'):
            media_type, full_path = rootfile.get('media-type'), rootfile.get('full-path')
            if not media_type or not full_path:
                raise EPubException('<rootfile/> element malformed')
            self.setdefault(media_type, full_path)


def _read_package(stream):
    stream.seek(0)
    with ZipFile(stream, 'r') as archive:
        if archive.read('mimetype').strip() != b'application/epub+zip':
            raise EPubException('not an EPUB container')
        container = Container(io.BytesIO(archive.read('META-INF/container.xml')))
        opf_path = container.get(OPF.MIMETYPE)
        if not opf_path:
            raise EPubException('missing OPF package file entry in container')
        root = safe_xml_fromstring(archive.read(opf_path), recover=False)
    if root is None:
        raise EPubException('invalid OPF XML')
    if root.tag != '{http://www.idpf.org/2007/opf}package':
        raise EPubException('invalid OPF package')
    version = root.get('version')
    if version not in ('2.0', '3.0'):
        raise EPubException('unsupported OPF package version')
    if root.find('{http://www.idpf.org/2007/opf}metadata') is None:
        raise EPubException('missing OPF metadata')
    return opf_path, root


def get_metadata(stream):
    opf_path, root = _read_package(stream)
    if root.get('version') == '3.0':
        prefixes, refines = opf3.read_prefixes(root), opf3.read_refines(root)
        fields = {
            field: getattr(opf3, 'read_' + field)(root, prefixes, refines) or ''
            for field in ('title', 'publisher', 'comments')
        }
        fields['authors'] = [author.name for author in opf3.read_authors(root, prefixes, refines)]
    else:
        opf = OPF(
            None, preparsed_opf=root, populate_spine=False,
            try_to_guess_cover=False, unquote_urls=False,
        )
        fields = {field: getattr(opf, field) or '' for field in ('title', 'publisher', 'comments')}
        fields['authors'] = [
            author for element in opf.authors_path(opf.metadata)
            if (author := (opf.get_text(element) or '').strip())
        ]
    return fields


def set_metadata(stream, fields):
    opf_path, root = _read_package(stream)
    if not fields:
        return
    if root.get('version') == '3.0':
        prefixes, refines = opf3.read_prefixes(root), opf3.read_refines(root)
        for field, value in fields.items():
            if field == 'authors':
                value = [opf3.Author(author, None) for author in value]
            getattr(opf3, 'set_' + field)(root, prefixes, refines, value)
        opf3.set_last_modified(root, prefixes, refines)
    else:
        opf = OPF(
            None, preparsed_opf=root, populate_spine=False,
            try_to_guess_cover=False, unquote_urls=False,
        )
        for field, value in fields.items():
            setattr(opf, field, value)
    opf_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    safe_replace(stream, opf_path, opf_bytes)