# ebook-converter-lib

`ebook-converter-lib` is a Python library and command-line tool for converting
ebooks between common formats. Licensed under GPL-3.0-or-later.

## Install

```shell
python -m pip install ebook-converter-lib
```

Python 3.11 or newer is required. PDF input uses PDFium through `pypdfium2`
(installed automatically); no external tools are needed. Text, embedded images,
the outline as table of contents, title, author and a first-page cover are
taken from the PDF. Figures drawn with lines and curves (graphs, diagrams,
tables) are detected and rendered as images in place.

## Use as a library

```python
from ebook_converter_lib import convert

result = convert("book.docx", "book.epub")
if not result["success"]:
    raise RuntimeError(result["message"])
```

`convert()` returns a dictionary with `success` and `message` keys. Use
`check_deps_str()` to verify that conversion dependencies can load in an
embedded Python runtime.

### Options

Extra arguments use the command-line option format:

```python
convert("book.epub", "book.mobi", "--base-font-size", "12")
```

- `--remove-text`: one regular expression per line, every match is deleted.
  Escape special characters for literal text, e.g. `C\+\+`.
- Unknown options, stray values and invalid regular expressions fail the
  conversion.

### EPUB metadata

```python
from ebook_converter_lib import read_metadata, update_metadata

book = read_metadata("book.epub")
result = update_metadata("book.epub", "updated.epub", title="New title")
```

EPUB 2/3, default rendition only; no conversion. Check `success` and `message`.
`book["metadata"]` contains `title`, `authors` (list), `publisher`, `comments`;
missing fields are `""`/`[]`, and failures return `None`. Updates accept these
fields as keywords: omitted/`None` preserves, empty publisher/comments clears.
Title and author names must be non-blank; the author list must be non-empty.
The source stays untouched; a different output is replaced only on success.
Book content is preserved, malformed XML fails, and cover changes are unsupported.

## Command line

```shell
ebook-converter book.docx book.epub
```

## Supported formats

Input: `azw`, `azw3`, `docm`, `docx`, `epub`, `fb2`, `fbz`, `htm`, `html`,
`htmlz`, `lrf`, `markdown`, `md`, `mobi`, `odt`, `opf`, `pdb`, `pdf`, `pobi`,
`prc`, `rtf`, `shtm`, `shtml`, `text`, `textile`, `txt`, `txtz`, `updb`,
`xhtm`, `xhtml`.

Output: `azw3`, `docx`, `epub`, `fb2`, `html`, `htmlz`, `lrf`, `mobi`, `oeb`,
`txt`, `txtz`.

The output format is chosen from the output file extension.

## Development

```shell
uv sync --group dev
uv run pytest
```

## Credits

- [ebook-converter](https://github.com/gryf/ebook-converter) by gryf, the original
  converter this library forks.
- [Calibre](https://github.com/kovidgoyal/calibre) by Kovid Goyal (GPL v3), for
  conversion and EPUB metadata code.
- [PDFium](https://pdfium.googlesource.com/pdfium/) and
  [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) for PDF input.
