"""Read a written GDV file back and compare it with the approved values.

The writer and this module are two transcriptions of the same record tables
and share no code: this module imports nothing from the package and has its
own positions, its own date and amount conversion and its own control sums.
A slip in one of them shows as a mismatch instead of leaving the building.
Both were written by the same hand from the same source, so a misreading of
the specification itself is not caught here; that needs the import into the
target program.

Positions are Python slices, counted from 0, of the record tables of release
01.12.2023 at https://www.gdv-online.de/vuvm/bestand/rel2023/ (``ds0001.htm``,
``ds0100.htm``, ``ds0200.htm``, ``ds0400.htm``, ``ds9999.htm``).

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

SIZE = 256

# Fields 2, 4 and 5 of every record between header and trailer.
INSURER, LINE, POLICY = slice(4, 9), slice(10, 13), slice(13, 30)


def _day(iso: Any) -> str:
    """ISO date as the eight digits of a record; nothing as zeros."""
    if iso in (None, ""):
        return "00000000"
    year, month, day = str(iso).split("-")
    return day + month + year


def _cents(amount: Any) -> int:
    return 0 if amount in (None, "") else int(Decimal(str(amount)).scaleb(2))


def _number(text: str) -> int:
    """A numeric field is digits only; ``int`` alone would accept spaces."""
    if not (text.isascii() and text.isdigit()):
        raise ValueError("numeric field holds something else than digits")
    return int(text)


def _plain(text: Any) -> str:
    return " ".join(str(text).split())


def _key_form(number: Any) -> str:
    """Key field 5 holds digits and letters only; the printed form stands elsewhere."""
    return re.sub(r"[^0-9A-Za-z]", "", str(number))


def parse(data: bytes, encoding: str, separator: bytes) -> dict[tuple[str, str, str], dict]:
    """Return the contracts of a file by insurer number, policy number and line code.

    Raises ``ValueError`` when the structure is broken: a record of another
    length, a package without header or trailer, a wrong count or sum.
    """
    step = SIZE + len(separator)
    if not data or len(data) % step:
        raise ValueError("file length is no multiple of the record length")
    contracts: dict[tuple[str, str, str], dict] = {}
    package: list[str] | None = None
    header = ""
    for at in range(0, len(data), step):
        if data[at + SIZE : at + step] != separator:
            raise ValueError("record separator missing")
        line = data[at : at + SIZE].decode(encoding)
        if len(line) != SIZE:
            raise ValueError("record is not 256 characters")
        kind, part = line[0:4], line[255]
        if kind == "0001":
            if package:
                raise ValueError("header inside a package")
            package = []
            if part == "1":
                header = line
            elif line[:95] != header[:95]:
                raise ValueError("header parts differ")
        elif package is None:
            raise ValueError("record outside a package")
        elif kind == "9999":
            gross = sum(_number(r[138:149]) for r in package if r[0:4] == "0400" and r[255] == "1")
            net = sum(_number(r[115:127]) for r in package if r[0:4] == "0200" and r[255] == "1")
            if not package or _number(line[4:14]) != len(package):
                raise ValueError("trailer count differs from the records")
            if _number(line[24:39]) != net or _number(line[39:53]) != gross or line[53] != "+":
                raise ValueError("trailer sum differs from the records")
            if line[14:24] != header[85:95]:
                raise ValueError("trailer names another broker than the header")
            package = None
        else:
            if line[INSURER] != header[INSURER]:
                raise ValueError("record of another insurer than the header")
            package.append(line)
            key = (line[INSURER].strip(), line[POLICY].strip(), line[LINE])
            if not re.fullmatch(r" *[0-9A-Za-z]+", line[POLICY]):
                raise ValueError("key field of the policy number holds a special character")
            contract = contracts.setdefault(key, {
                "collections": [],
                "broker": line[32:42].strip(),
                # Header fields 54 and 55, and whether the header announces a 0400.
                "header": header[236:238],
                "announces_0400": header[212:215].strip() != "",
            })
            if (kind, part) == ("0100", "1"):
                contract["name"] = _plain(line[43:73] + " " + line[73:103] + " " + line[103:133])
                contract["role"] = line[236:238]
            elif (kind, part) == ("0200", "1"):
                contract["start"], contract["end"] = line[43:51], line[51:59]
                contract["payment"] = line[67].strip()
                contract["status"] = line[68].strip()
                contract["collection_kind"] = line[42].strip()
                contract["net"] = _number(line[115:127])
                contract["currency"] = line[112:115]
            elif (kind, part) == ("0200", "2"):
                contract["gross"] = _number(line[71:83])
                contract["printed"] = line[83:113].strip()
                contract["issued"] = line[146:154]
            elif (kind, part) == ("0400", "1"):
                contract["collections"].append({
                    "from": line[53:61],
                    "to": line[61:69],
                    "created": line[70:78],
                    "kinds": (line[42] + line[43:45]).rstrip(),
                    "payment": line[69].strip(),
                    "net": _number(line[109:120]),
                    "tax": _number(line[121:132]),
                    "gross": _number(line[138:149]),
                    "signs": line[120] + line[132] + line[149],
                })
            else:
                raise ValueError(f"unexpected record {kind}.{part}")
    if package is not None:
        raise ValueError("package without trailer")
    for contract in contracts.values():
        if contract["collections"] and not contract["announces_0400"]:
            raise ValueError("a 0400 stands in a package whose header does not announce it")
    return contracts


def check(
    data: bytes,
    jobs: list[dict[str, Any]],
    names: dict[str, dict[str, str]],
    settings: dict[str, Any],
    tables: dict[str, dict[str, str]],
) -> str | None:
    """Name the first difference between the file and the approved jobs, or nothing."""
    separator = b"\r\n" if settings["record_separator"] == "crlf" else b""
    try:
        contracts = parse(data, settings["encoding"], separator)
    except (ValueError, IndexError) as problem:
        return f"structure: {problem}"

    def approved(job: dict[str, Any], name: str) -> Any:
        found = job["values"].get(names.get(job["kind"], {}).get(name))
        if isinstance(found, dict):
            normalized = found.get("normalized")
            return found.get("text") if normalized is None else normalized
        return found

    def code(job: dict[str, Any], name: str, table: str) -> str:
        found = approved(job, name)
        return "" if found in (None, "") else tables[table].get(_plain(found).casefold(), "?")

    def contract_key(job: dict[str, Any]) -> tuple[str, str, str]:
        return (
            code(job, "insurer", "insurers"),
            _key_form(_plain(approved(job, "policy_number"))),
            code(job, "line_of_business", "lines_of_business"),
        )

    with_contract = {contract_key(j) for j in jobs if j["kind"] in settings["contract_kinds"]}
    seen = set()
    for job in jobs:
        number = _plain(approved(job, "policy_number"))
        key = contract_key(job)
        contract = contracts.get(key)
        if contract is None:
            return f"job {job['id']}: contract is not in the file"
        seen.add(key)
        expected = {
            "name": _plain(approved(job, "policyholder")),
            "role": "01",
            "broker": str(settings["broker_number"]),
            "currency": settings["currency"],
            "header": ((settings.get("sender_kind") or " ") + (settings.get("addressee_kind") or " ")),
            "status": settings.get("contract_status") or "",
            "collection_kind": settings.get("collection_kind") or "",
        }
        is_contract = job["kind"] in settings["contract_kinds"]
        if is_contract or key not in with_contract:
            # The printed form is that of the policy, if one is in the file.
            expected["printed"] = number
        if is_contract:
            premium = approved(job, "premium")
            if premium in (None, ""):
                premium = approved(job, "annual_premium")
                # Annex 14: only with mode 1 or 6 is a year one payment period.
                if premium not in (None, "") and code(job, "payment_mode", "payment_modes") not in ("1", "6"):
                    return f"job {job['id']}: an annual amount stands for a payment period"
            expected |= {
                "start": _day(approved(job, "start_date")),
                "end": _day(approved(job, "end_date")),
                "payment": code(job, "payment_mode", "payment_modes"),
                "gross": _cents(premium),
                "net": _cents(approved(job, "net_premium")),
                "issued": _day(approved(job, "issue_date")),
            }
            # With instalments, a net amount above the gross amount of a period,
            # or without one to compare with, is one for a year and has no field.
            per_period = _cents(approved(job, "premium"))
            if expected["payment"] not in ("1", "6") and not 0 < expected["net"] <= per_period:
                expected["net"] = 0
        for field, value in expected.items():
            if contract.get(field) != value:
                return f"job {job['id']}: {field} differs"
        if job["kind"] in settings["collection_kinds"]:
            wanted = {
                "from": _day(approved(job, "period_start") or approved(job, "due_date")),
                "to": _day(approved(job, "period_end")),
                "created": _day(approved(job, "invoice_date")),
                "kinds": (
                    (settings.get("collection_kind") or " ") + (settings.get("debit_kind") or "")
                ).rstrip(),
                "payment": code(job, "payment_mode", "payment_modes"),
                "net": _cents(approved(job, "net_premium")),
                "tax": _cents(approved(job, "insurance_tax")),
                "gross": _cents(approved(job, "premium")),
                "signs": "+++",
            }
            if wanted not in contract["collections"]:
                return f"job {job['id']}: collection differs"
            contract["collections"].remove(wanted)
    if set(contracts) != seen or any(c["collections"] for c in contracts.values()):
        return "the file holds a record no approved job stands for"
    return None
