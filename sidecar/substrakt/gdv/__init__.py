"""Hand approved jobs over as a GDV file, one file per customer.

``hand_over`` is the entry point a table of writers registers under a target
name. It takes the approved jobs of one customer as plain data, the pipeline
profile as plain data and a folder, and returns what happened to every job:

- ``written``: the job is in the file named by ``file``;
- ``waiting``: the job is not written and goes back to review, with the items
  that are missing (an insurer without a number in the mapping table, a value
  that does not fit its field); nothing is guessed to get a contract out;
- ``failed``: the file was written, read back by ``reader`` and differed from
  the approved values; the file is removed.

The file is written under a temporary name and gets its final name only
after the read-back, so nobody imports a file that was not checked. The
folder is the caller's: it must lie inside the read roots, in the customer
network. This module opens no connection.

What goes into which record and field, and what is still unknown, is in
``docs/gdv-hand-over.md``; the sources in the specification are named
in ``writer`` and ``reader``.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import codecs
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from substrakt.errors import PipelineProfileInvalid
from substrakt.gdv import reader, tables, writer

# The name of a file while it is written and read back. A crash can leave
# one behind, with contracts in it and no job that points to it.
PART = re.compile(r".+_\d{8}-\d{6}\.gdv\.part")


class Settings(BaseModel):
    """The block ``hand_over`` of a pipeline profile.

    The settings the file cannot do without have no default: the standard
    leaves encoding and record separator to the two parties, and the rest
    are facts of one broker.
    """

    model_config = ConfigDict(extra="forbid")

    format: Literal["gdv"] = Field(description="Names this format; it chooses the writer")
    encoding: str = Field(description="Codec of the file; one byte per character")
    record_separator: Literal["crlf", "none"] = Field(
        description="What follows every 256 bytes: CR LF or nothing"
    )
    broker_number: str = Field(min_length=1, max_length=10, pattern=r"^[A-Za-z0-9]+$")
    sender: str = Field(min_length=1, max_length=30)
    addressee: str = Field(min_length=1, max_length=30)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    # Codes of facts that are not on any paper. Each is decided by whoever
    # writes the profile and stays empty in the file when it is not named.
    sender_kind: Literal["1", "2", "3", "9"] | None = Field(
        default=None,
        description="Header field 54: 1 insurer, 2 broker, 3 insurer without GDV key, 9 other",
    )
    addressee_kind: Literal["1", "2", "3", "9"] | None = Field(
        default=None, description="Header field 55, same codes as sender_kind"
    )
    contract_status: (
        Literal["1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B", "C"] | None
    ) = Field(default=None, description="0200 field 13, annex 24; 1 is a contract in force")
    collection_kind: Literal["1", "2"] | None = Field(
        default=None,
        description="Field 8 of 0200 and 0400: 1 collection by the broker, 2 by the insurer",
    )
    debit_kind: str | None = Field(
        default=None,
        pattern=r"^[1-9][0-9]$",
        description="0400 field 9, annex 60; 30 is a renewal premium",
    )
    contract_kinds: list[str] = Field(description="Kinds written as address and contract part")
    collection_kinds: list[str] = Field(
        description="Kinds written as address, contract part and collection record"
    )

    @field_validator("encoding")
    @classmethod
    def _single_byte(cls, value: str) -> str:
        try:
            codecs.lookup(value)
            one_byte = len("A".encode(value)) == 1 and len("ä".encode(value)) == 1
        except (LookupError, UnicodeError):
            one_byte = False
        if not one_byte:
            raise ValueError("not a codec with one byte per character")
        return value


def _settings(profile: dict[str, Any]) -> dict[str, Any]:
    file = f"{profile.get('name', '')}.yml"
    try:
        return Settings.model_validate(profile.get("hand_over") or {}).model_dump()
    except ValidationError as exc:
        error = [
            {"location": ".".join(["hand_over", *map(str, f["loc"])]), "message": f["msg"]}
            for f in exc.errors(include_input=False, include_url=False)
        ]
        summary = "; ".join(f"{e['location']}: {e['message']}" for e in error)
        raise PipelineProfileInvalid(f"{file}: {summary}", file=file, error=error) from None


def check(job: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Name what keeps one approved document out of a file, before a job exists.

    This is the question an approval asks: an insurer without a number or a
    value that fits no field is better named while the document is in review
    than after a job failed. What only shows among several jobs (two policies
    with one number) is found by ``hand_over``. A profile whose settings are
    incomplete answers nothing here; the hand-over names the settings.
    """
    try:
        settings = _settings(profile)
    except PipelineProfileInvalid:
        return []
    names = {kind: spec["values"] for kind, spec in profile["kinds"].items()}
    _, _, waiting = writer.build([job], names, settings, tables.load_all(), datetime.now().date())
    return waiting.get(job["id"], [])


def simulate(jobs: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    """What ``hand_over`` would write for these jobs, without writing anything.

    The same build as the run: ``written`` are the jobs the file would hold,
    ``waiting`` the jobs it would leave out with their items, ``contracts``
    the written job ids, one list per policy number. Incomplete
    settings and a broken table raise as they do in the run.
    """
    settings = _settings(profile)
    names = {kind: spec["values"] for kind, spec in profile["kinds"].items()}
    _, written, waiting = writer.build(
        jobs, names, settings, tables.load_all(), datetime.now().date()
    )
    contracts: dict[str | None, list[str]] = {}
    for job in jobs:
        if job["id"] in written:
            contracts.setdefault(_policy(job, names), []).append(job["id"])
    return {"written": written, "waiting": waiting, "contracts": list(contracts.values())}


def _policy(job: dict[str, Any], names: dict[str, Any]) -> str | None:
    """The policy number of a job as the writer keys a contract by it."""
    value = job["values"].get(names[job["kind"]].get("policy_number", ""))
    if value is None:
        return None
    return writer.key_number(value["text"] if value["normalized"] is None else value["normalized"])


def _write_part(part: Path, data: bytes, read_back: Callable[[bytes], Any]) -> Any:
    """Write the file under its temporary name and read it back.

    The name stays only when the content was read back as written; a
    problem and any exception remove it, because it holds contracts.
    """
    # Opened before the try: a foreign file under this name raises
    # FileExistsError and is neither emptied nor removed.
    handle = part.open("xb")
    try:
        with handle as file:
            file.write(data)
        problem = read_back(part.read_bytes())
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if problem:
        part.unlink()
    return problem


def hand_over(
    jobs: list[dict[str, Any]],
    folder: Path,
    profile: dict[str, Any],
    *,
    customer: str,
    created: datetime | None = None,
) -> dict[str, Any]:
    """Write the approved jobs of one customer into one file in ``folder``.

    A job is ``{"id": ..., "kind": <document kind>, "values": {...}}`` with
    the values under the names the profile gives them for the target. A
    value is plain (a date as ISO text, an amount as a number or decimal
    text, a term in its canonical form) or the pair of ``text`` and
    ``normalized`` a job file carries; the normalised form is written.
    """
    if not customer or Path(customer).name != customer:
        raise ValueError("customer is not usable as a file name")
    settings = _settings(profile)
    names = {kind: spec["values"] for kind, spec in profile["kinds"].items()}
    codes = tables.load_all()
    created = created or datetime.now()

    data, written, waiting = writer.build(jobs, names, settings, codes, created.date())
    result: dict[str, Any] = {"file": None, "written": [], "waiting": waiting, "failed": {}}
    if not written:
        return result

    target = folder / f"{customer}_{created:%Y%m%d-%H%M%S}.gdv"
    part = target.with_name(target.name + ".part")
    if target.exists():
        problem = "a file of that name exists"
    else:
        handed = [j for j in jobs if j["id"] in written]
        problem = _write_part(
            part, data, lambda content: reader.check(content, handed, names, settings, codes)
        )
    if problem:
        result["failed"] = dict.fromkeys(written, problem)
        return result
    part.rename(target)
    result |= {"file": str(target), "written": written}
    return result
