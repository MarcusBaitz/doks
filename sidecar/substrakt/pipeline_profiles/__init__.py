"""Pipeline profiles: what a watched folder means and where its values go.

A profile is one YAML file. It names at which folder level the customer
stands, which document kinds are read, which values are expected per kind
under which name in the target application, and the target. Everything
specific to one target application and one customer lives in such a file;
the core knows no folder rule and no application name. Bundled files may be
replaced, but not merged, by a same-named file in the user data directory,
exactly like document kinds.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrakt import document_kinds, yaml_model
from substrakt.errors import DocumentKindUnknown, PipelineProfileInvalid, PipelineProfileUnknown

BUILTIN = Path(__file__).parent
SCHEMA_FILE = BUILTIN / "pipeline_profile.schema.json"

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

# Configured by app.py so that user files override bundled ones.
_custom: Path | None = None


class ExpectedValues(BaseModel):
    """The values one document kind must deliver for the target."""

    model_config = ConfigDict(extra="forbid")

    values: dict[str, str] = Field(
        min_length=1,
        description="Value name in the document kind mapped to its name in the target",
    )
    optional: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Values in the same form that are handed over when they were read "
            "unambiguously and do not block an approval when they were not"
        ),
    )

    @model_validator(mode="after")
    def _listed_once(self) -> ExpectedValues:
        twice = sorted(set(self.values) & set(self.optional))
        if twice:
            raise ValueError(f"listed as required and as optional: {', '.join(twice)}")
        return self


class PipelineProfile(BaseModel):
    """A complete pipeline profile from YAML."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Must equal the file name without its extension")
    title: str = Field(description="Display name for the interface")
    target: str = Field(description="Target the approved values are handed over to")
    customer_folder_level: int | None = Field(
        ge=1,
        description=(
            "Folder level below the watched folder that names the customer; "
            "1 is the first subfolder, null means folders name no customer"
        ),
    )
    kinds: dict[str, ExpectedValues] = Field(
        min_length=1,
        description="Document kinds this profile reads, by file name without extension",
    )
    overview_columns: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Values shown as columns of the overview, in order, as value name "
            "mapped to the column heading"
        ),
    )
    # Passed through unchecked: only the writer of the target's format knows
    # these settings, and it validates them with its own model.
    hand_over: dict[str, Any] | None = Field(
        default=None,
        description="Settings of the hand-over format; checked by the writer of the target",
    )

    @model_validator(mode="after")
    def _names(self) -> PipelineProfile:
        for label, value in (("name", self.name), ("target", self.target)):
            if not _NAME.match(value):
                raise ValueError(
                    f"{label} {value!r}: use lowercase letters, digits and underscores"
                )
        return self

    def customer_of(self, file: Path, folder: Path) -> str | None:
        """Name the customer a file belongs to, or ``None`` outside a customer folder."""
        subfolders = file.relative_to(folder).parts[:-1]
        level = self.customer_folder_level
        if level is None or len(subfolders) < level:
            return None
        return subfolders[level - 1]


class DescribedValue(BaseModel):
    name: str
    # The label of the value in its kind file.
    label: str
    # The name of the value in the target.
    target_name: str
    required: bool


class DescribedKind(BaseModel):
    name: str
    title: str
    values: list[DescribedValue]


class ProfileDescription(BaseModel):
    """A profile with the titles and labels of its kinds, for the interface."""

    name: str
    title: str
    target: str
    customer_folder_level: int | None
    kinds: list[DescribedKind]
    overview_columns: dict[str, str]


def describe(name: str) -> ProfileDescription:
    """Load a profile and add what its kind files say about each value."""
    profile = load(name)
    kinds = []
    for kind_name, expected in profile.kinds.items():
        kind = document_kinds.load(kind_name)
        labels = {field.name: field.label for field in kind.fields}
        listed = [(n, t, True) for n, t in expected.values.items()]
        listed += [(n, t, False) for n, t in expected.optional.items()]
        kinds.append(
            DescribedKind(
                name=kind_name,
                title=kind.title,
                values=[
                    DescribedValue(name=n, label=labels[n], target_name=t, required=r)
                    for n, t, r in listed
                ],
            )
        )
    return ProfileDescription(
        name=profile.name,
        title=profile.title,
        target=profile.target,
        customer_folder_level=profile.customer_folder_level,
        kinds=kinds,
        overview_columns=profile.overview_columns,
    )


def configure(custom: Path | None) -> None:
    """Set the user override directory during application startup."""
    global _custom
    _custom = custom


def custom_directory() -> Path | None:
    return _custom


@lru_cache(maxsize=16)
def _read(path: Path, _revision: tuple[int, int]) -> PipelineProfile:
    """Read and validate a file; ``_revision`` invalidates the cache."""
    return yaml_model.read(path, PipelineProfile, PipelineProfileInvalid)


def _check_kinds(profile: PipelineProfile, file: str) -> None:
    """Reject a kind without a description and a value the kind does not read."""
    error = []
    for kind_name, expected in profile.kinds.items():
        try:
            known = {field.name for field in document_kinds.load(kind_name).fields}
        except DocumentKindUnknown:
            error.append({"location": f"kinds.{kind_name}", "message": "no such document kind"})
            continue
        error += [
            {"location": f"kinds.{kind_name}.{key}.{value}", "message": "not a value of the kind"}
            for key, listed in (("values", expected.values), ("optional", expected.optional))
            for value in listed
            if value not in known
        ]
    read = {value for expected in profile.kinds.values() for value in [*expected.values, *expected.optional]}
    error += [
        {"location": f"overview_columns.{value}", "message": "no kind of the profile reads it"}
        for value in profile.overview_columns
        if value not in read
    ]
    if error:
        summary = "; ".join(f"{e['location']}: {e['message']}" for e in error)
        raise PipelineProfileInvalid(f"{file}: {summary}", file=file, error=error)


def titles() -> dict[str, str]:
    """Name and display title of every profile, without checking its kinds."""
    found = sorted(yaml_model.sources(BUILTIN, _custom).items())
    return {name: _read(path, yaml_model.state(path)).title for name, path in found}


def load(name: str) -> PipelineProfile:
    """Load one profile and check it against the document kinds it names."""
    path = yaml_model.sources(BUILTIN, _custom).get(name)
    if path is None:
        raise PipelineProfileUnknown(
            f"No file named {name}{yaml_model.EXTENSION}", profile=name
        )
    profile = _read(path, yaml_model.state(path))
    _check_kinds(profile, path.name)
    return profile


def active(chosen: str | None) -> PipelineProfile:
    """Return the chosen profile, or the only one there is.

    No profile name is a default in code: which application a pipeline feeds
    is knowledge of the profile files.
    """
    available = sorted(yaml_model.sources(BUILTIN, _custom))
    if chosen is None and len(available) == 1:
        chosen = available[0]
    if chosen is None:
        raise PipelineProfileUnknown("No pipeline profile is chosen.")
    return load(chosen)


def schema_text() -> str:
    """Generate the editor schema from the authoritative Pydantic model."""
    return yaml_model.schema_text(PipelineProfile)


def write_schema(target: Path = SCHEMA_FILE) -> None:
    target.write_text(schema_text(), encoding="utf-8")


def schema_is_current(file: Path = SCHEMA_FILE) -> bool:
    return file.is_file() and file.read_text(encoding="utf-8") == schema_text()
