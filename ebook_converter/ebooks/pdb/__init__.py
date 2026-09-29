__license__ = 'GPL v3'
__copyright__ = '2009, John Schember <john@nachtimwald.com>'
__docformat__ = 'restructuredtext en'


class PDBError(Exception):
    pass


FORMAT_READERS = None


def _import_readers():
    global FORMAT_READERS
    from ebook_converter.ebooks.pdb.palmdoc.reader import Reader as palmdoc_reader
    from ebook_converter.ebooks.pdb.ztxt.reader import Reader as ztxt_reader
    from ebook_converter.ebooks.pdb.pdf.reader import Reader as pdf_reader
    from ebook_converter.ebooks.pdb.haodoo.reader import Reader as haodoo_reader

    # eReader and Plucker are listed in IDENTITY_TO_NAME but have no reader, so
    # they raise PDBError naming the format instead of failing on an import.
    FORMAT_READERS = {
        'zTXTGPlm': ztxt_reader,
        'TEXtREAd': palmdoc_reader,
        '.pdfADBE': pdf_reader,
        'BOOKMTIT': haodoo_reader,
        'BOOKMTIU': haodoo_reader,
    }


IDENTITY_TO_NAME = {
    'PNPdPPrs': 'eReader',
    'PNRdPPrs': 'eReader',
    'zTXTGPlm': 'zTXT',
    'TEXtREAd': 'PalmDOC',
    '.pdfADBE': 'Adobe Reader',
    'DataPlkr': 'Plucker',
    'BOOKMTIT': 'Haodoo.net',
    'BOOKMTIU': 'Haodoo.net',

    'BVokBDIC': 'BDicty',
    'DB99DBOS': 'DB (Database program)',
    'vIMGView': 'FireViewer (ImageViewer)',
    'PmDBPmDB': 'HanDBase',
    'InfoINDB': 'InfoView',
    'ToGoToGo': 'iSilo',
    'SDocSilX': 'iSilo 3',
    'JbDbJBas': 'JFile',
    'JfDbJFil': 'JFile Pro',
    'DATALSdb': 'LIST',
    'Mdb1Mdb1': 'MobileDB',
    'BOOKMOBI': 'MobiPocket',
    'DataSprd': 'QuickSheet',
    'SM01SMem': 'SuperMemo',
    'TEXtTlDc': 'TealDoc',
    'InfoTlIf': 'TealInfo',
    'DataTlMl': 'TealMeal',
    'DataTlPt': 'TealPaint',
    'dataTDBP': 'ThinkDB',
    'TdatTide': 'Tides',
    'ToRaTRPW': 'TomeRaider',
    'BDOCWrdS': 'WordSmith',
}


def get_reader(identity):
    '''
    Returns None if no reader is found for the identity.
    '''
    global FORMAT_READERS
    if FORMAT_READERS is None:
        _import_readers()
    return FORMAT_READERS.get(identity, None)
