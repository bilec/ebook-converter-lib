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
