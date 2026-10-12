"""
Shim for html5-parser using lxml.html.
html5-parser requires native compilation which Chaquopy can't do.
This provides the same parse() interface using lxml's HTML parser.
"""
# ponytail: shim replaces native html5-parser; upgrade if parsing edge cases appear
import re

from lxml import html

_BAD_NAME_CHARS = re.compile(r'[^\w.-]')


def _clean_name(name, declared):
    prefix, sep, local = name.partition(':')
    if sep and (prefix in declared or prefix == 'xmlns'):
        return name
    name = _BAD_NAME_CHARS.sub('_', name)
    return name if name[:1].isalpha() or name[:1] == '_' else '_' + name


def _sanitize_names(doc):
    # html5-parser's sanitize_names: undeclared prefixes ("<cache:x>") break later XML parsing
    for e in [e for e in doc.iter() if isinstance(e.tag, str)]:
        declared = set()
        if ':' in e.tag or any(':' in a for a in e.attrib):
            declared = {'xml'} | {a[6:] for anc in e.iterancestors() for a in anc.attrib if a.startswith('xmlns:')}
            declared |= {a[6:] for a in e.attrib if a.startswith('xmlns:')}
        e.tag = _clean_name(e.tag, declared)
        items = list(e.attrib.items())
        if any(_clean_name(a, declared) != a for a, _ in items):
            # pop() can't address names like '{id}' (lxml reads them as namespaces), so rebuild
            e.attrib.clear()
            for attr, value in items:
                e.set(_clean_name(attr, declared), value)
    return doc


def parse(markup, treebuilder='lxml', namespace_elements=False,
          maybe_xhtml=False, sanitize_names=True, stack_size=16384,
          fragment_context=None, **kwargs):
    """Parse HTML and return an lxml Element tree, matching html5_parser.parse() API."""
    if isinstance(markup, str):
        markup = markup.encode('utf-8')
    if fragment_context:
        return html.fragments_fromstring(markup.decode('utf-8'))
    doc = html.document_fromstring(markup)
    return _sanitize_names(doc) if sanitize_names else doc
