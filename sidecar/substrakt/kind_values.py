"""The values a document kind reads, as a person changes them in Templates.

A change never edits the shipped kind file. It is written as a file of the
same name into the user directory, which replaces the shipped one at the next
load, so the next document read uses the new set without a restart
(docs/harness/02-sidecar.md, section “Document kinds”).

A renamed value keeps its internal name and changes only its label, so a
profile, a waiting entry and a job still find it. A new value is named as it
stands in the document and becomes a label rule of the generic label search;
no knowledge of a kind enters this module. A removed value is also removed
from every profile that expects it, written the same way, so that the profile
stays valid and reading goes on; the target then no longer gets that value.
Values already stored with an entry are never rewritten.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from substrakt import document_kinds, pipeline_profiles, yaml_model
from substrakt.document_kinds import DocumentKind
from substrakt.errors import KindChangeRefused, PipelineProfileInvalid
from substrakt.extraction.fields import FieldSpec
from substrakt.extraction.labels import LabelRule

HEADER = (
    "# Written by Substrakt when a person changed the values in Templates.\n"
    "# It replaces the shipped file of the same name; delete it to go back.\n"
)


class ReadValue(BaseModel):
    name: str
    label: str


class KindValues(BaseModel):
    """A document kind with the values it reads, in its order."""

    name: str
    title: str
    values: list[ReadValue]


class ValueChange(BaseModel):
    # ``None`` is a new value; its label is how it stands in the document.
    name: str | None = None
    label: str


class ValuesChange(BaseModel):
    """The complete new list: a value left out is removed."""

    values: list[ValueChange]


def describe(kind: DocumentKind) -> KindValues:
    return KindValues(
        name=kind.name,
        title=kind.title,
        values=[ReadValue(name=f.name, label=f.label or f.name) for f in kind.fields],
    )


def all_kinds() -> list[KindValues]:
    return [describe(kind) for kind in document_kinds.load_all().values()]


def _refuse(reason: str) -> KindChangeRefused:
    return KindChangeRefused(f"The values were not changed: {reason}.", reason=reason)


def _free_name(label: str, taken: set[str]) -> str:
    """Derive an internal name from a label; it never reuses a name of the kind."""
    plain = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_")
    if not base[:1].isalpha():
        base = f"value_{base}".rstrip("_")
    name, number = base, 2
    while name in taken:
        name, number = f"{base}_{number}", number + 1
    return name


def _write(directory: Path, name: str, data: dict[str, Any]) -> None:
    """Write through a temporary name, so a file appears only whole."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{name}{yaml_model.EXTENSION}"
    temporary = directory / f".{name}{yaml_model.EXTENSION}.tmp"
    text = HEADER + "\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _profiles_without(kind: str, removed: set[str]) -> list[dict[str, Any]]:
    """Every profile that expects a removed value, as it reads without it."""
    changed = []
    sources = yaml_model.sources(pipeline_profiles.BUILTIN, pipeline_profiles.custom_directory())
    for path in sources.values():
        try:
            profile = yaml_model.read(
                path, pipeline_profiles.PipelineProfile, PipelineProfileInvalid
            )
        except PipelineProfileInvalid:
            continue  # A broken profile is reported when it is loaded, not here.
        expected = profile.kinds.get(kind)
        if expected is None or not removed & {*expected.values, *expected.optional}:
            continue
        data = profile.model_dump(mode="json")
        values = {n: t for n, t in expected.values.items() if n not in removed}
        if not values:
            raise _refuse("target-needs-a-value")
        data["kinds"][kind] = {
            "values": values,
            "optional": {n: t for n, t in expected.optional.items() if n not in removed},
        }
        read = {n for e in data["kinds"].values() for n in [*e["values"], *e["optional"]]}
        data["overview_columns"] = {
            n: heading for n, heading in profile.overview_columns.items() if n in read
        }
        pipeline_profiles.PipelineProfile.model_validate(data)
        changed.append(data)
    return changed


def _labels(change: ValuesChange, old: set[str]) -> list[str]:
    """The labels of a change, refused when one is empty, twice or names no value."""
    labels = [value.label.strip() for value in change.values]
    if not labels:
        raise _refuse("no-value-left")
    if not all(labels):
        raise _refuse("label-empty")
    if len({label.casefold() for label in labels}) < len(labels):
        raise _refuse("label-twice")
    named = [value.name for value in change.values if value.name is not None]
    if any(n not in old for n in named) or len(set(named)) < len(named):
        raise _refuse("value-unknown")
    return labels


def change(name: str, change: ValuesChange) -> KindValues:
    """Store the new list of values of a kind and return the kind as it now reads."""
    kind_directory = document_kinds.custom_directory()
    profile_directory = pipeline_profiles.custom_directory()
    if kind_directory is None or profile_directory is None:
        raise RuntimeError("The user directories are not configured.")
    kind = document_kinds.load(name)
    old = {field.name: field for field in kind.fields}
    labels = _labels(change, set(old))

    taken = set(old)
    fields: list[FieldSpec] = []
    for value, label in zip(change.values, labels, strict=True):
        if value.name is not None:
            fields.append(old[value.name].model_copy(update={"label": label}))
            continue
        new = _free_name(label, taken)
        taken.add(new)
        rule = LabelRule(patterns=[re.escape(label)], value="text")
        fields.append(FieldSpec(name=new, label=label, label_rule=rule))
    kept = {field.name for field in fields}

    data = kind.model_dump(mode="json", exclude_defaults=True)
    data["fields"] = [field.model_dump(mode="json", exclude_defaults=True) for field in fields]
    data["same_document"] = [n for n in kind.same_document if n in kept]
    try:
        # The file as it will be read back, checked before it gets its name.
        DocumentKind.model_validate(yaml.safe_load(yaml.safe_dump(data, allow_unicode=True)))
        profiles = _profiles_without(name, set(old) - kept)
    except ValidationError:
        raise _refuse("invalid") from None

    # Profiles first: one without the value is valid against the old kind too,
    # so a crash between the two writes leaves nothing invalid.
    for profile in profiles:
        _write(profile_directory, profile["name"], profile)
    _write(kind_directory, name, data)
    return describe(document_kinds.load(name))
