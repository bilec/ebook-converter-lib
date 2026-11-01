import os
import re
import shutil
import tempfile
import traceback
from pathlib import Path


def _parse_extra_args(extra_args):
    options = {}
    index = 0
    while index < len(extra_args):
        argument = extra_args[index]
        if not argument.startswith("--"):
            raise ValueError(f"Unexpected argument {argument!r}: values with spaces must be one argument")
        name = argument[2:].replace("-", "_")
        if index + 1 >= len(extra_args) or extra_args[index + 1].startswith("--"):
            options[name] = True
        else:
            options[name] = extra_args[index + 1]
            index += 1
        index += 1
    remove_text = options.pop("remove_text", "")
    if remove_text:
        sequences = [text for text in remove_text.splitlines() if text]
        if sequences:
            pattern = "(?:" + "|".join(sequences) + ")"
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"Invalid --remove-text pattern {pattern!r}: {error}") from None
            options.setdefault("sr1_search", pattern)
            options.setdefault("sr1_replace", "")
    return options


def check_deps_str():
    try:
        from ebook_converter.ebooks.conversion.plumber import Plumber  # noqa: F401
    except ModuleNotFoundError as error:
        return f"Missing dependency: {error.name}"
    except Exception as error:
        return f"Dependency check failed: {type(error).__name__}: {error}"
    return "Dependencies available."


def read_metadata(input_path):
    try:
        source = Path(input_path)
        if source.suffix.lower() == ".epub":
            from ebook_converter.ebooks.metadata.epub import get_metadata
        elif source.suffix.lower() in (".azw3", ".mobi"):
            from ebook_converter.ebooks.metadata.mobi import get_metadata
        else:
            raise ValueError("Metadata reading supports EPUB, AZW3 and MOBI files only")
        with source.open("rb") as stream:
            metadata = get_metadata(stream)
        return {"success": True, "message": f"Read metadata from {input_path}", "metadata": metadata}
    except Exception as error:
        return {
            "success": False,
            "message": f"{type(error).__name__}: {error}\n{traceback.format_exc()}",
            "metadata": None,
        }


def update_metadata(input_path, output_path, *, title=None, authors=None, publisher=None, comments=None):
    temporary_path = None
    try:
        source, output = Path(input_path), Path(output_path)
        extension = source.suffix.lower()
        if extension not in (".epub", ".azw3", ".mobi") or output.suffix.lower() != extension:
            raise ValueError("Metadata updates require matching EPUB, AZW3 or MOBI file extensions")
        if extension == ".epub":
            from ebook_converter.ebooks.metadata.epub import set_metadata
        else:
            from ebook_converter.ebooks.metadata.mobi import set_metadata
        if source.resolve() == output.resolve() or (output.exists() and source.samefile(output)):
            raise ValueError("Output must be a different file from the source")
        fields = {"title": title, "authors": authors, "publisher": publisher, "comments": comments}
        fields = {field: value for field, value in fields.items() if value is not None}
        for field, value in fields.items():
            if field == "authors":
                if not isinstance(value, (list, tuple)) or not value:
                    raise ValueError("authors must be a non-empty list of names")
                if any(not isinstance(author, str) or not author.strip() for author in value):
                    raise ValueError("authors must contain non-blank strings")
            elif not isinstance(value, str) or (field == "title" and not value.strip()):
                raise ValueError(f"{field} must be a string" + (" with a non-blank value" if field == "title" else ""))
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=extension, delete=False) as temporary:
            temporary_path = temporary.name
            with source.open("rb") as original:
                shutil.copyfileobj(original, temporary)
            temporary.flush()
            set_metadata(temporary, fields)
        os.replace(temporary_path, output)
        temporary_path = None
        return {"success": True, "message": f"Updated metadata in {output_path}"}
    except Exception as error:
        return {"success": False, "message": f"{type(error).__name__}: {error}\n{traceback.format_exc()}"}
    finally:
        if temporary_path is not None:
            os.unlink(temporary_path)


def convert(input_path, output_path, *extra_args):
    try:
        from ebook_converter import logging
        from ebook_converter.customize.conversion import OptionRecommendation
        from ebook_converter.ebooks.conversion.plumber import Plumber

        plumber = Plumber(input_path, output_path, logging.default_log)
        if extra_args:
            options = _parse_extra_args(extra_args)
            unknown = sorted("--" + name.replace("_", "-") for name in options if not plumber.get_option_by_name(name))
            if unknown:
                raise ValueError(f"Unknown option(s): {', '.join(unknown)}")
            plumber.merge_ui_recommendations(
                [(name, value, OptionRecommendation.HIGH) for name, value in options.items()]
            )
        plumber.run()
        return {"success": True, "message": f"Converted to {output_path}"}
    except Exception as error:
        return {"success": False, "message": f"{type(error).__name__}: {error}\n{traceback.format_exc()}"}
    finally:
        from ebook_converter.ptempfile import base_dir

        # Android kills the process, so ptempfile's atexit cleanup never runs
        shutil.rmtree(base_dir(), ignore_errors=True)
