import ctypes
import html
import os
import re

from lxml import etree

from ebook_converter.ebooks import ConversionError

# Figure detection, in PDF points
PAD = 4.0
MERGE_GAP = 12.0
MIN_SIDE = 25.0
THIN = 2.0
LONG_RULE = 150.0


def pdftohtml(output_dir, pdf_path, no_images):
    '''
    Write the PDF text, embedded images and drawn figures into output_dir as
    index.html, with a p<N> anchor per page, and its outline as toc.ncx.
    '''
    import pypdfium2
    import pypdfium2.raw as pdfium_c

    document = pypdfium2.PdfDocument(pdf_path)
    parts = []
    for page_number, page in enumerate(document, 1):
        textpage = page.get_textpage()
        placed, figures = [], []
        if not no_images:
            figures = find_figures(page, textpage)
            for index, box in enumerate(figures):
                placed.append((box[3], render_figure(page, box, output_dir, 'fig-%d-%d' % (page_number, index))))
            for index, image in enumerate(page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE])):
                bounds = image.get_bounds()
                if not any(contains(box, centre(bounds)) for box in figures):
                    placed.append((bounds[3], save_image(image, output_dir, 'img-%d-%d' % (page_number, index))))
        if placed:
            pieces = text_and_images(textpage, placed, figures)
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


def text_and_images(textpage, placed, hidden):
    '''Page text split at the first character below the top edge of each
    placed (top, file name) image, with the file names in between. Characters
    inside the hidden boxes, such as figure labels, are dropped.'''
    chars = [textpage.get_charbox(i) for i in range(textpage.count_chars())]
    kept = [not any(contains(box, centre(char), slack=0) for box in hidden) for char in chars]
    splits = sorted((next((i for i, char in enumerate(chars) if kept[i] and below(char, top)), len(chars)), -top, name)
                    for top, name in placed)
    pieces, start = [], 0
    for split, _, name in splits:
        pieces += [kept_text(textpage, kept, start, split), name]
        start = split
    return pieces + [kept_text(textpage, kept, start, len(chars))]


def kept_text(textpage, kept, start, end):
    text, run = '', None
    for i in range(start, end + 1):
        if i < end and kept[i]:
            run = i if run is None else run
        elif run is not None:
            text += textpage.get_text_range(run, i - run)
            run = None
    return text


def below(charbox, top):
    left, bottom, right, char_top = charbox
    # spaces and generated line breaks have no height
    return char_top > bottom and char_top < top


def centre(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def contains(box, point, slack=2.0):
    return box[0] - slack <= point[0] <= box[2] + slack and box[1] - slack <= point[1] <= box[3] + slack


def find_figures(page, textpage):
    '''Boxes around vector drawings that are figures, not frames, rules or
    backgrounds of text.'''
    import pypdfium2.raw as pdfium_c

    chunks = []
    for index in range(textpage.count_rects()):
        rect = textpage.get_rect(index)
        chunks.append((textpage.get_text_bounded(*rect), rect))
    drawings = []
    for path in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH]):
        box = path.get_bounds()
        width, height = box[2] - box[0], box[3] - box[1]
        if min(width, height) <= THIN and max(width, height) >= LONG_RULE:
            continue
        # thin rectangles (rules, fraction bars) cannot hold text, so skip the costly scan
        if min(width, height) > THIN and is_rect(path) and any(
                contains(box, centre(rect), slack=0) for text, rect in chunks if text.strip()):
            continue
        drawings.append(box)
    figures = []
    page_width, page_height = page.get_size()
    # shortcut: quadratic clustering, slow on pages with thousands of separate paths; switch to a grid if that shows up
    for box, members in clusters(drawings):
        if is_frame(box, members):
            continue
        if box[0] >= page_width or box[1] >= page_height or box[2] <= 0 or box[3] <= 0:
            continue  # off the page, nothing to render
        box = grow_over_labels(box, chunks)
        if box[2] - box[0] < MIN_SIDE or box[3] - box[1] < MIN_SIDE:
            continue
        inner = [text for text, rect in chunks if contains(box, centre(rect))]
        if sum(len(text.strip()) for text in inner) > 120:
            continue  # framed text, not a figure
        if sum(len(word) >= 3 and word.isalpha() for text in inner for word in text.split()) > 8:
            continue  # prose inside, e.g. highlighted lines
        figures.append((box[0] - PAD, box[1] - PAD, box[2] + PAD, box[3] + PAD))
    return figures


def is_rect(path):
    import pypdfium2.raw as pdfium_c

    xs, ys = set(), set()
    for index in range(pdfium_c.FPDFPath_CountSegments(path.raw)):
        x, y = ctypes.c_float(), ctypes.c_float()
        pdfium_c.FPDFPathSegment_GetPoint(pdfium_c.FPDFPath_GetPathSegment(path.raw, index), x, y)
        xs.add(round(x.value))
        ys.add(round(y.value))
    return len(xs) <= 2 and len(ys) <= 2


def clusters(boxes):
    '''Group boxes closer than MERGE_GAP; returns [(bounding box, members)].'''
    groups = [(list(box), [box]) for box in boxes]
    changed = True
    while changed:
        changed = False
        merged = []
        for box, members in groups:
            for other, other_members in merged:
                if (box[0] <= other[2] + MERGE_GAP and other[0] <= box[2] + MERGE_GAP
                        and box[1] <= other[3] + MERGE_GAP and other[1] <= box[3] + MERGE_GAP):
                    other[:] = [min(box[0], other[0]), min(box[1], other[1]),
                                max(box[2], other[2]), max(box[3], other[3])]
                    other_members.extend(members)
                    changed = True
                    break
            else:
                merged.append((box, members))
        groups = merged
    return groups


def is_frame(box, members, edge=3.0):
    '''Only thin rules along the group's border (plus its fill): a frame.'''
    area = (box[2] - box[0]) * (box[3] - box[1])
    for member in members:
        width, height = member[2] - member[0], member[3] - member[1]
        if width * height >= 0.8 * area:
            continue
        if min(width, height) > THIN:
            return False
        if width > height:
            if not (abs(member[1] - box[1]) < edge or abs(member[3] - box[3]) < edge):
                return False
        elif not (abs(member[0] - box[0]) < edge or abs(member[2] - box[2]) < edge):
            return False
    return True


def is_label(text):
    '''Vertex or axis labels such as 'a', '16', '(3,2)'; a 3-letter word means prose.'''
    text = text.strip()
    return 0 < len(text) <= 6 and not re.search(r'[^\W\d_]{3}', text)


def grow_over_labels(box, chunks, gap=8.0):
    grown = list(box)
    for text, rect in chunks:
        if is_label(text) and (rect[0] <= box[2] + gap and box[0] <= rect[2] + gap
                               and rect[1] <= box[3] + gap and box[1] <= rect[3] + gap):
            grown = [min(grown[0], rect[0]), min(grown[1], rect[1]), max(grown[2], rect[2]), max(grown[3], rect[3])]
    return grown


def render_figure(page, box, output_dir, stem):
    width, height = page.get_size()
    # shortcut: assumes the page box starts at 0,0, offset it if PDFs with shifted crop boxes misplace figures
    crop = (max(box[0], 0), max(box[1], 0), max(width - box[2], 0), max(height - box[3], 0))
    page.render(scale=3, crop=crop).to_pil().save(os.path.join(output_dir, stem + '.png'))
    return stem + '.png'


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
