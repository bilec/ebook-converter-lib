"""
Read meta information from PDF files
"""
import functools
import os
import shutil

from ebook_converter.ptempfile import TemporaryDirectory
from ebook_converter.ebooks.metadata import (
    MetaInformation, string_to_authors, check_isbn, check_doi)


def read_info(outputdir, get_cover):
    ''' Read the info dict of src.pdf in outputdir and, if get_cover, render
    its first page into outputdir as cover.jpg.'''
    import pypdfium2

    document = pypdfium2.PdfDocument(os.path.join(outputdir, 'src.pdf'))
    ans = {key: value for key, value in document.get_metadata_dict().items() if value}
    if get_cover and len(document):
        image = document[0].render(scale=2).to_pil().convert('RGB')
        image.save(os.path.join(outputdir, 'cover.jpg'), quality=90)
    return ans


def get_metadata(stream, cover=True):
    with TemporaryDirectory('_pdf_metadata_read') as pdfpath:
        stream.seek(0)
        with open(os.path.join(pdfpath, 'src.pdf'), 'wb') as f:
            shutil.copyfileobj(stream, f)
        info = read_info(pdfpath, bool(cover))
        if info is None:
            raise ValueError('Could not read info dict from PDF')
        covpath = os.path.join(pdfpath, 'cover.jpg')
        cdata = None
        if cover and os.path.exists(covpath):
            with open(covpath, 'rb') as f:
                cdata = f.read()

    title = info.get('Title', None) or 'Unknown'
    au = info.get('Author', None)
    if au is None:
        au = ['Unknown']
    else:
        au = string_to_authors(au)
    mi = MetaInformation(title, au)

    creator = info.get('Creator', None)
    if creator:
        mi.book_producer = creator

    keywords = info.get('Keywords', None)
    mi.tags = []
    if keywords:
        mi.tags = [x.strip() for x in keywords.split(',')]
        isbn = [check_isbn(x) for x in mi.tags if check_isbn(x)]
        if isbn:
            mi.isbn = isbn = isbn[0]
        mi.tags = [x for x in mi.tags if check_isbn(x) != isbn]

    subject = info.get('Subject', None)
    if subject:
        mi.tags.insert(0, subject)

    if 'xmp_metadata' in info:
        from ebook_converter.ebooks.metadata.xmp import consolidate_metadata
        mi = consolidate_metadata(mi, info)

    # Look for recognizable identifiers in the info dict, if they were not
    # found in the XMP metadata
    for scheme, check_func in {'doi': check_doi, 'isbn': check_isbn}.items():
        if scheme not in mi.get_identifiers():
            for k, v in info.items():
                if k != 'xmp_metadata':
                    val = check_func(v)
                    if val:
                        mi.set_identifier(scheme, val)
                        break

    if cdata:
        mi.cover_data = ('jpeg', cdata)
    return mi


get_quick_metadata = functools.partial(get_metadata, cover=False)


def set_metadata(stream, mi):
    return None
