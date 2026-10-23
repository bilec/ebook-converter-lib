import html
import os

from lxml import etree

from ebook_converter.ebooks import ConversionError


def pdftohtml(output_dir, pdf_path, no_images):
    '''
    Write the PDF text and embedded images into output_dir as index.html, with
    a p<N> anchor per page, and its outline as toc.ncx.
    '''
    import pypdfium2
    import pypdfium2.raw as pdfium_c

    document = pypdfium2.PdfDocument(pdf_path)
    parts = []
    for page_number, page in enumerate(document, 1):
        textpage = page.get_textpage()
        images = [] if no_images else list(page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]))
        if images:
            pieces = text_and_images(textpage, images, output_dir, page_number)
        else:
            pieces = [textpage.get_text_bounded()]
        body = ''
        for index, piece in enumerate(pieces):
            # pieces alternate text, image file, text, ...
            if index % 2:
                body += '<p><img src="{}" alt=""/></p>'.format(piece)
            elif piece.strip():
                body += '<p>{}</p>'.format(html.escape(piece.replace('\r\n', '\n')).replace('\n', '<br>\n'))
        if body:
            parts.append('<a id="p{}"></a>{}'.format(page_number, body))

    if not parts:
        raise ConversionError('Could not extract text from PDF')

    with open(os.path.join(output_dir, 'index.html'), 'w', encoding='utf-8') as index:
        index.write(
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"><title>PDF</title>'
            '</head><body>{}</body></html>'.format(''.join(parts))
        )
    write_outline(document, output_dir)


def text_and_images(textpage, images, output_dir, page_number):
    '''Page text split at the first character below each image's top edge,
    with the saved image file names in between.'''
    count = textpage.count_chars()
    placed = []
    for index, image in enumerate(images):
        top = image.get_bounds()[3]
        split = next((i for i in range(count) if below(textpage.get_charbox(i), top)), count)
        placed.append((split, -top, save_image(image, output_dir, 'img-%d-%d' % (page_number, index))))
    pieces, start = [], 0
    for split, _, name in sorted(placed):
        pieces += [textpage.get_text_range(start, split - start), name]
        start = split
    return pieces + [textpage.get_text_range(start)]


def below(charbox, top):
    left, bottom, right, char_top = charbox
    # spaces and generated line breaks have no height
    return char_top > bottom and char_top < top


def save_image(image, output_dir, stem):
    if image.get_filters(skip_simple=True) == ['DCTDecode']:
        # shortcut: a JPEG's soft mask (alpha) is dropped, render it like PNGs if transparent JPEGs show up
        with open(os.path.join(output_dir, stem + '.jpg'), 'wb') as jpeg:
            image.extract(jpeg)
        return stem + '.jpg'
    # Rendering applies masks and decodes formats readers lack, such as JPEG 2000
    image.get_bitmap(render=True).to_pil().save(os.path.join(output_dir, stem + '.png'))
    return stem + '.png'


def write_outline(document, output_dir):
    from ebook_converter.ebooks.oeb.polish.toc import TOC, create_ncx

    toc = TOC()
    parents = [toc]
    count = 0
    for item in document.get_toc():
        dest = item.get_dest()
        index = dest.get_index() if dest else None
        title = item.get_title()
        if index is None or not title:
            continue
        del parents[item.level + 1:]
        parents.append(parents[-1].add(title, 'index.html', 'p%d' % (index + 1)))
        count += 1
    if count > 2:
        root = create_ncx(toc, (lambda x: x), 'pdftohtml', 'en', 'pdftohtml')
        with open(os.path.join(output_dir, 'toc.ncx'), 'wb') as f:
            f.write(etree.tostring(root, pretty_print=True, with_tail=False,
                                   encoding='utf-8', xml_declaration=True))
