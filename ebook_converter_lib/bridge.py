import re
import shutil
import traceback


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
