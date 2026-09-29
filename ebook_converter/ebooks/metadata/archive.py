import os
from contextlib import closing

from ebook_converter.customize import FileTypePlugin
from ebook_converter.utils.localization import canonicalize_lang


__license__ = 'GPL v3'
__copyright__ = '2010, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'


def is_comic(list_of_names):
    extensions = {x.rpartition('.')[-1].lower() for x in list_of_names
                      if '.' in x and x.lower().rpartition('/')[-1] != 'thumbs.db'}
    comic_extensions = {'jpg', 'jpeg', 'png'}
    return len(extensions - comic_extensions) == 0


def archive_type(stream):
    from ebook_converter.utils.zipfile import stringFileHeader
    try:
        pos = stream.tell()
    except:
        pos = 0
    id_ = stream.read(4)
    ans = None
    if id_ == stringFileHeader:
        ans = 'zip'
    elif id_.startswith(b'Rar'):
        ans = 'rar'
    try:
        stream.seek(pos)
    except Exception:
        pass
    return ans


class KPFExtract(FileTypePlugin):

    name = 'KPF Extract'
    author = 'Kovid Goyal'
    description = ('Extract the source DOCX file from Amazon Kindle Create '
                   'KPF files. Note this will not contain any edits made in '
                   'the Kindle Create program itself.')
    file_types = {'kpf'}
    supported_platforms = ['osx', 'linux']
    on_import = True

    def run(self, archive):
        from ebook_converter.utils.zipfile import ZipFile
        with ZipFile(archive, 'r') as zf:
            fnames = zf.namelist()
            candidates = [x for x in fnames if x.lower().endswith('.docx')]
            if not candidates:
                return archive
            of = self.temporary_file('_kpf_extract.docx')
            with closing(of):
                of.write(zf.read(candidates[0]))
        return of.name


class ArchiveExtract(FileTypePlugin):
    name = 'Archive Extract'
    author = 'Kovid Goyal'
    description = 'Extract common e-book formats from ZIP archives'
    file_types = {'zip'}
    supported_platforms = ['osx', 'linux']
    on_import = True

    def run(self, archive):
        from ebook_converter.utils.zipfile import ZipFile
        zf = ZipFile(archive, 'r')
        fnames = zf.namelist()

        def fname_ok(fname):
            bn = os.path.basename(fname).lower()
            if bn == 'thumbs.db':
                return False
            if '.' not in bn:
                return False
            if bn.rpartition('.')[-1] in {'diz', 'nfo'}:
                return False
            if '__MACOSX' in fname.split('/'):
                return False
            return True

        fnames = list(filter(fname_ok, fnames))
        if len(fnames) > 1 or not fnames:
            return archive
        fname = fnames[0]
        ext = os.path.splitext(fname)[1][1:]
        if ext.lower() not in {
                'lit', 'epub', 'mobi', 'prc', 'rtf', 'pdf', 'mp3', 'pdb',
                'azw', 'azw1', 'azw3', 'fb2', 'docx', 'doc', 'odt'}:
            return archive

        of = self.temporary_file('_archive_extract.'+ext)
        with closing(of):
            of.write(zf.read(fname))
        return of.name


def get_comic_book_info(d, mi, series_index='volume'):
    # See http://code.google.com/p/comicbookinfo/wiki/Example
    series = d.get('series', '')
    if series.strip():
        mi.series = series
        si = d.get(series_index, None)
        if si is None:
            si = d.get('issue' if series_index == 'volume' else 'volume', None)
        if si is not None:
            try:
                mi.series_index = float(si)
            except Exception:
                mi.series_index = 1
    if d.get('language', None):
        lang = canonicalize_lang(d.get('lang'))
        if lang:
            mi.languages = [lang]
    if d.get('rating', -1) > -1:
        mi.rating = d['rating']
    for x in ('title', 'publisher'):
        y = d.get(x, '').strip()
        if y:
            setattr(mi, x, y)
    tags = d.get('tags', [])
    if tags:
        mi.tags = tags
    authors = []
    for credit in d.get('credits', []):
        if credit.get('role', '') in ('Writer', 'Artist', 'Cartoonist',
                'Creator'):
            x = credit.get('person', '')
            if x:
                x = ' '.join((reversed(x.split(', '))))
                authors.append(x)
    if authors:
        mi.authors = authors
    comments = d.get('comments', '')
    if comments and comments.strip():
        mi.comments = comments.strip()
    pubm, puby = d.get('publicationMonth', None), d.get('publicationYear', None)
    if puby is not None:
        from ebook_converter.utils.date import parse_only_date
        from datetime import date
        try:
            dt = date(puby, 6 if pubm is None else pubm, 15)
            dt = parse_only_date(str(dt))
            mi.pubdate = dt
        except Exception:
            pass


def parse_comic_comment(comment, series_index='volume'):
    # See http://code.google.com/p/comicbookinfo/wiki/Example
    from ebook_converter.ebooks.metadata import MetaInformation
    import json
    mi = MetaInformation(None, None)
    m = json.loads(comment)
    if isinstance(m, dict):
        for cat in m:
            if cat.startswith('ComicBookInfo'):
                get_comic_book_info(m[cat], mi, series_index=series_index)
                break
    return mi
