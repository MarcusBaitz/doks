"""Mapping tables for what a paper document does not print.

A GDV record identifies the insurer by a number, the line of business by a
three-digit code and the payment mode by one character. None of them stands
on a policy, so they come from one YAML file per table, bundled under
``tables/`` and replaceable by a file of the same name in
``<data dir>/gdv/``. A name without an entry yields nothing: the caller
names the missing item and the contract waits, because a guessed code would
file a contract under the wrong insurer or line.

Sources of the codes are named in each file; the code shapes below are the
field lengths of the record tables, release 01.12.2023 (key fields 2 and 4,
record 0200 field 12).

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrakt import yaml_model
from substrakt.errors import HandOverTableInvalid

BUILTIN = Path(__file__).parent / "tables"

# Table name → shape of a code in it.
SHAPES = {
    "insurers": re.compile(r"[A-Za-z0-9]{1,5}"),
    "lines_of_business": re.compile(r"[0-9]{3}"),
    "payment_modes": re.compile(r"[0-9]"),
}

# Configured by app.py so that user files override bundled ones.
_custom: Path | None = None


def norm(key: str) -> str:
    """Spelling of a name for the lookup: case and spacing do not count."""
    return " ".join(str(key).split()).casefold()


class Table(BaseModel):
    """One mapping table from YAML."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Must equal the file name without its extension")
    source: str = Field(min_length=1, description="Where the codes come from")
    entries: dict[str, str] = Field(description="Approved value mapped to its code, as text")

    @model_validator(mode="after")
    def _codes(self) -> Table:
        shape = SHAPES.get(self.name)
        if shape is None:
            raise ValueError(f"name {self.name!r}: no such table")
        seen: set[str] = set()
        for key, code in self.entries.items():
            if not shape.fullmatch(code):
                raise ValueError(f"entries.{key}: code does not have the shape {shape.pattern}")
            if norm(key) in seen:
                raise ValueError(f"entries.{key}: listed twice")
            seen.add(norm(key))
        return self


def configure(custom: Path | None) -> None:
    """Set the user override directory during application startup."""
    global _custom
    _custom = custom
    _read.cache_clear()


@lru_cache(maxsize=8)
def _read(path: Path, _revision: tuple[int, int]) -> dict[str, str]:
    table = yaml_model.read(path, Table, HandOverTableInvalid)
    return {norm(key): code for key, code in table.entries.items()}


def load(name: str) -> dict[str, str]:
    """Return one table with normalised names as keys."""
    path = yaml_model.sources(BUILTIN, _custom).get(name)
    if name not in SHAPES or path is None:
        file = f"{name}{yaml_model.EXTENSION}"
        raise HandOverTableInvalid(
            f"{file}: missing", file=file, error=[{"location": "(file)", "message": "missing"}]
        )
    return _read(path, yaml_model.state(path))


def load_all() -> dict[str, dict[str, str]]:
    return {name: load(name) for name in SHAPES}
