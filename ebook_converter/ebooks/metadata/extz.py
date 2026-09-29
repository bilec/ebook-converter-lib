"""
Read meta information from extZ (TXTZ, HTMLZ...) files.
"""
import os

from ebook_converter.ebooks.metadata import MetaInformation
from ebook_converter.ebooks.metadata.opf2 import OPF
from ebook_converter.utils.zipfile import ZipFile


__license__ = 'GPL v3'
__copyright__ = '2011, John Schember <john@nachtimwald.com>'


def get_first_opf_name(zf):
    opfs = sorted(name for name in zf.namelist()
                  if name.endswith('.opf') and '/' not in name)
    if not opfs:
        raise Exception('No OPF found')
    return opfs[0]


def _cover_href(opf):
    cover_href = opf.raster_cover or opf.guide_raster_cover
    if cover_href:
        return cover_href
    for meta in opf.metadata.xpath('//*[local-name()="meta" and '
                                   '@name="cover"]'):
        val = meta.get('content')
        if val.rpartition('.')[2].lower() in {'jpeg', 'jpg', 'png'}:
            return val
    # A guide cover is not required to be present in the manifest.
    for val in opf.guide_cover_path(opf.root):
        if val.rpartition('.')[2].lower() in {'jpeg', 'jpg', 'png'}:
            return val
    # TXTZ files use a dedicated element for the cover.
    for cpath in opf.root.xpath('//cover-relpath-from-base'):
        if cpath.text:
            return cpath.text
    return None


def get_metadata(stream, extract_cover=True):
    """
    Return metadata as a L{MetaInfo} object
    """
    mi = MetaInformation('Unknown', ['Unknown'])
    stream.seek(0)
    try:
        with ZipFile(stream) as zf:
            with zf.open(get_first_opf_name(zf)) as opf_stream:
                opf = OPF(opf_stream)
            mi = opf.to_book_metadata()
            if extract_cover:
                cover_href = _cover_href(opf)
                if cover_href:
                    try:
                        mi.cover_data = (os.path.splitext(cover_href)[1],
                                         zf.read(cover_href))
                    except Exception:
                        pass
    except Exception:
        return mi
    return mi
