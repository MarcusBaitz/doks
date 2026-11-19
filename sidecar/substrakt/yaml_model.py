"""Read a human-written YAML file into a validated Pydantic model.

Document kinds and pipeline profiles are both one file per name, bundled
with the package and replaceable by a file of the same name in the data
directory. This module holds what the two share, so that an invalid file of
either sort is reported the same way: file name and position, never content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from substrakt.errors import SubstraktError

EXTENSION = ".yml"


def state(path: Path) -> tuple[int, int]:
    """Identify a file revision; size disambiguates coarse timestamps."""
    info = path.stat()
    return info.st_mtime_ns, info.st_size


def files(directory: Path | None) -> dict[str, Path]:
    """Map the name of every description in a directory to its file."""
    if directory is None or not directory.is_dir():
        return {}
    return {p.stem: p for p in sorted(directory.glob(f"*{EXTENSION}")) if p.is_file()}


def sources(builtin: Path, custom: Path | None) -> dict[str, Path]:
    """A custom file replaces the bundled file of the same name completely."""
    return {**files(builtin), **files(custom)}


def _location(error: dict[str, Any]) -> str:
    return ".".join(str(part) for part in error["loc"]) or "(file)"


def schema_text(model: type[BaseModel]) -> str:
    """Generate the schema file of a model; the model stays the authority."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": (
            f"Generated from {model.__module__}.{model.__name__} with "
            "write_schema(); do not edit by hand."
        ),
        **model.model_json_schema(),
    }
    return json.dumps(schema, ensure_ascii=False, indent=2) + "\n"


def read[M: BaseModel](path: Path, model: type[M], invalid: type[SubstraktError]) -> M:
    """Read and validate one file; every failure is raised as ``invalid``."""

    def fail(summary: str, error: list[dict[str, str]]) -> SubstraktError:
        return invalid(f"{path.name}: {summary}", file=path.name, error=error)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        message = str(exc).splitlines()[0] if str(exc) else ""
        raise fail(
            f"unreadable YAML ({type(exc).__name__})",
            [{"location": "(file)", "message": message}],
        ) from None
    if not isinstance(raw, dict):
        raise fail("expected a mapping", [{"location": "(file)", "message": "not a mapping"}])
    try:
        loaded = model.model_validate(raw)
    except ValidationError as exc:
        error = [
            {"location": _location(f), "message": f["msg"].removeprefix("Value error, ")}
            for f in exc.errors(include_input=False, include_url=False)
        ]
        summary = "; ".join(f"{f['location']}: {f['message']}" for f in error)
        raise fail(summary, error) from None
    if getattr(loaded, "name", path.stem) != path.stem:
        raise fail(
            "name must match the file name",
            [{"location": "name", "message": "does not match the file name"}],
        )
    return loaded
