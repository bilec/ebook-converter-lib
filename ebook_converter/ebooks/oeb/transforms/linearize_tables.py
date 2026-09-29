"""
Replace table markup with divs, for readers that cannot lay out tables.
"""
from ebook_converter.ebooks.oeb.base import OEB_DOCS, XHTML, XPath


__license__ = 'GPL v3'
__copyright__ = '2009, Kovid Goyal <kovid@kovidgoyal.net>'


class LinearizeTables:
    def linearize(self, root):
        for x in XPath('//h:table|//h:td|//h:tr|//h:th|//h:caption|//h:tbody|//h:tfoot|//h:thead|//h:colgroup|//h:col')(root):
            x.tag = XHTML('div')
            for attr in (
                'style',
                'font',
                'valign',
                'colspan',
                'width',
                'height',
                'rowspan',
                'summary',
                'align',
                'cellspacing',
                'cellpadding',
                'frames',
                'rules',
                'border',
            ):
                if attr in x.attrib:
                    del x.attrib[attr]

    def __call__(self, oeb, context):
        for x in oeb.manifest.items:
            if x.media_type in OEB_DOCS:
                self.linearize(x.data)
