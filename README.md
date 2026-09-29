# ebook-converter-lib

`ebook-converter-lib` is a Python library and command-line tool for converting
ebooks between common formats. It is a modified fork of
[ebook-converter](https://github.com/gryf/ebook-converter) by gryf, which is
itself derived from the conversion components of
[Calibre](https://calibre-ebook.com/). Licensed under GPL-3.0-or-later.

## Install

```shell
python -m pip install ebook-converter-lib
```

Python 3.11 or newer is required. PDF conversion also requires Poppler tools
(`pdftohtml`, `pdfinfo`, and `pdftoppm`) available on `PATH`.

## Use as a library

```python
from ebook_converter_lib import convert

result = convert("book.docx", "book.epub")
if not result["success"]:
    raise RuntimeError(result["message"])
```

`convert()` returns a dictionary with `success` and `message` keys. Additional
arguments use the command-line option format:

```python
convert("book.epub", "book.mobi", "--base-font-size", "12")
```

Use `check_deps_str()` to verify that conversion dependencies can load in an
embedded Python runtime.

## Command line

```shell
ebook-converter book.docx book.epub
```

## Supported formats

Input includes DOCX, EPUB, ODT, TXT, PDB, RTF, MOBI, AZW, FB2, HTML, PDF, and
LRF. Output includes EPUB, MOBI, DOCX, HTMLZ, TXT, and LRF.

## Development

```shell
uv sync --group dev
uv run pytest
```

See [PYPI_RELEASE.md](PYPI_RELEASE.md) for the release procedure.
