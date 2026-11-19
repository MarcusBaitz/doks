"""Render approved contracts as records of the GDV data set “VU-Vermittler”.

This module is the only place that knows the record layout. Every position,
length and format below is transcribed from the record tables of release
01.12.2023 at https://www.gdv-online.de/vuvm/bestand/rel2023/ (read on
10 November 2026):

- ``ds0001.htm``  header 0001, version 2.5, three partial records
- ``ds0100.htm``  address part 0100, version 2.3, partial record 1
- ``ds0200.htm``  general contract part 0200, version 2.5, partial records 1, 2
- ``ds0400.htm``  collection 0400, version 1.7, partial record 1
- ``ds9999.htm``  trailer 9999, version 1.1
- ``anl2.htm``    annex 2, sequence number; ``anl7.htm`` annex 7, partner role

The formats are those of the brochure “Der GDV-Datensatz VU-Vermittler”,
4th edition, section 3.1.5 with table 2 (numeric: right-aligned with leading
zeros, initial value zero; alphanumeric: left-aligned with spaces; date
DDMMYYYY; amounts without a decimal separator, sign in a field of its own),
section 3.1.2 (one header and one trailer per insurer and broker) and
section 3.1.7 (order of the records, sequence number).

Two things the tables leave open were taken from the sample file the GDV
publishes (``musterdatei_041222.txt``): the trailer counts partial records,
and a sum of zero still carries the sign “+”.

A value that does not fit its field, or has a character the encoding lacks,
is never cut or replaced: the contract is not written and the item is named.
The layout lists every numeric field of a partial record, filled or not,
because an unfilled numeric field is zeros, not spaces.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

RECORD_LENGTH = 256

VERSIONS = {"0001": "2.5", "0100": "2.3", "0200": "2.5", "0400": "1.7", "9999": "1.1"}

# Annex 14: with these payment modes a year, or the whole contract, is one
# payment period, so an annual amount is the amount per payment period.
WHOLE_PERIOD_MODES = {"1", "6"}


@dataclass(frozen=True)
class Field:
    name: str
    start: int  # byte address as the record table prints it, counted from 1
    length: int
    kind: str = "an"  # an, an_right, n, date or amount
    const: str | None = None


class Unfit(ValueError):
    """A value cannot be written into its field as it is."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


def _key(record: str) -> tuple[Field, ...]:
    """Fields 1 to 7, identical in every record between header and trailer."""
    return (
        Field("record", 1, 4, "n", record),
        Field("insurer_number", 5, 5),
        Field("line_code", 11, 3, "n"),
        Field("policy_number", 14, 17, "an_right"),
        Field("sequence", 31, 2, "n"),
        Field("broker_number", 33, 10),
    )


def _header(part: int) -> tuple[Field, ...]:
    return (
        Field("record", 1, 4, "n", "0001"),
        Field("insurer_number", 5, 5),
        Field("sender", 10, 30),
        Field("addressee", 40, 30),
        Field("created_from", 70, 8, "date"),
        Field("created_to", 78, 8, "date"),
        Field("broker_number", 86, 10),
        Field("part", 256, 1, "n", str(part)),
    )


_SIGN = "+"

LAYOUT: dict[tuple[str, int], tuple[Field, ...]] = {
    ("0001", 1): (
        *_header(1),
        # Versions of the record types this file can contain (fields 7, 8, 9, 46, 50).
        Field("version_0001", 96, 3, const=VERSIONS["0001"]),
        Field("version_0100", 99, 3, const=VERSIONS["0100"]),
        Field("version_0200", 102, 3, const=VERSIONS["0200"]),
        Field("version_0400", 213, 3),  # only in a package that holds a 0400
        Field("version_9999", 225, 3, const=VERSIONS["9999"]),
        Field("sender_kind", 237, 1),
        Field("addressee_kind", 238, 1),
        # Field 56: “00” where the insurer has no billing office.
        Field("billing_office", 239, 2, const="00"),
    ),
    ("0001", 2): _header(2),
    ("0001", 3): _header(3),
    ("0100", 1): (
        *_key("0100"),
        Field("name_1", 44, 30),
        Field("name_2", 74, 30),
        Field("name_3", 104, 30),
        Field("birth_date", 226, 8, "date"),
        # Annex 7: 01 is the policyholder, which is what the approved value names.
        Field("partner_role", 237, 2, const="01"),
        Field("part", 256, 1, "n", "1"),
    ),
    ("0200", 1): (
        *_key("0200"),
        Field("collection_kind", 43, 1),
        Field("start_date", 44, 8, "date"),
        Field("end_date", 52, 8, "date"),
        Field("main_due_date", 60, 8, "date"),
        Field("payment_code", 68, 1),
        Field("contract_status", 69, 1),
        Field("exit_date", 72, 8, "date"),
        Field("change_date", 90, 8, "date"),
        Field("share", 99, 5, "n"),
        Field("currency", 113, 3),
        Field("net_premium", 116, 12, "amount"),
        Field("remaining_term", 195, 2, "n"),
        Field("term_discount", 197, 4, "n"),
        Field("application_date", 201, 8, "date"),
        Field("part", 256, 1, "n", "1"),
    ),
    ("0200", 2): (
        *_key("0200"),
        Field("product_valid_from", 66, 6, "n"),
        Field("gross_premium", 72, 12, "amount"),
        Field("printed_policy_number", 84, 30),
        Field("instalment_surcharge", 134, 5, "n"),
        Field("application_received", 139, 8, "date"),
        Field("issue_date", 147, 8, "date"),
        Field("part", 256, 1, "n", "2"),
    ),
    ("0400", 1): (
        *_key("0400"),
        Field("collection_kind", 43, 1),
        Field("debit_kind", 44, 2),
        Field("booking_date", 46, 8, "date"),
        Field("period_start", 54, 8, "date"),
        Field("period_end", 62, 8, "date"),
        Field("payment_code", 70, 1),
        Field("created", 71, 8, "date"),
        Field("change_date", 79, 8, "date"),
        Field("supplement_number", 87, 3, "n"),
        Field("currency", 107, 3),
        Field("net", 110, 11, "amount"),
        Field("net_sign", 121, 1, const=_SIGN),
        Field("tax", 122, 11, "amount"),
        Field("tax_sign", 133, 1, const=_SIGN),
        Field("fee", 134, 4, "amount"),
        Field("fee_sign", 138, 1, const=_SIGN),
        Field("gross", 139, 11, "amount"),
        Field("gross_sign", 150, 1, const=_SIGN),
        Field("commission", 151, 11, "amount"),
        Field("commission_sign", 162, 1, const=_SIGN),
        Field("lead_share", 163, 11, "amount"),
        Field("lead_share_sign", 174, 1, const=_SIGN),
        Field("discount", 207, 11, "amount"),
        Field("discount_sign", 218, 1, const=_SIGN),
        Field("remaining_term", 243, 2, "n"),
        Field("term_discount", 245, 4, "n"),
        Field("share", 250, 5, "n"),
        Field("part", 256, 1, "n", "1"),
    ),
    ("9999", 1): (
        Field("record", 1, 4, "n", "9999"),
        Field("count", 5, 10, "n"),
        Field("broker_number", 15, 10),
        Field("total_net", 25, 15, "amount"),
        Field("total_gross", 40, 14, "amount"),
        Field("total_gross_sign", 54, 1, const=_SIGN),
        Field("total_commission", 55, 14, "amount"),
        Field("total_commission_sign", 69, 1, const=_SIGN),
        Field("total_benefits", 70, 14, "amount"),
        Field("total_benefits_sign", 84, 1, const=_SIGN),
        Field("total_claim_costs", 85, 14, "amount"),
        Field("total_claim_costs_sign", 99, 1, const=_SIGN),
    ),
}


def cents(value: Any) -> int:
    """An amount as whole cents; anything else than a plain amount is unfit."""
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation:
        raise ValueError(value) from None
    if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
        raise ValueError(value)
    return int(amount)


def _text(field: Field, value: Any, encoding: str) -> bytes:
    if field.const is not None:
        value = field.const
    try:
        if field.kind == "date":
            text = "0" * 8 if value is None else date.fromisoformat(str(value)).strftime("%d%m%Y")
        elif field.kind == "amount":
            text = str(cents(value or 0)).rjust(field.length, "0")
        elif field.kind == "n":
            text = str(value or 0).rjust(field.length, "0")
            if not (text.isascii() and text.isdigit()):
                raise ValueError(value)
        elif field.kind == "an_right":
            text = str(value or "").rjust(field.length)
        else:
            text = str(value or "").ljust(field.length)
        if not text.isprintable():
            raise ValueError(value)
        data = text.encode(encoding)
    except ValueError:  # includes UnicodeEncodeError
        raise Unfit(field.name) from None
    if len(data) != field.length:
        raise Unfit(field.name)
    return data


def render(record: str, part: int, values: dict[str, Any], encoding: str) -> bytes:
    """Render one partial record; the only function that produces record bytes."""
    fields = LAYOUT[record, part]
    unknown = set(values) - {f.name for f in fields}
    assert not unknown, f"{record}.{part} has no field {sorted(unknown)}"
    line = bytearray(b" " * RECORD_LENGTH)
    for field in fields:
        line[field.start - 1 : field.start - 1 + field.length] = _text(
            field, values.get(field.name), encoding
        )
    return checked(bytes(line))


def checked(data: bytes) -> bytes:
    """Every partial record passes here; another length cannot be written."""
    assert len(data) == RECORD_LENGTH, f"partial record of {len(data)} bytes"
    return data


def _item(item: str, **more: Any) -> dict[str, Any]:
    return {"item": item, **more}


def build(
    jobs: list[dict[str, Any]],
    names: dict[str, dict[str, str]],
    settings: dict[str, Any],
    tables: dict[str, dict[str, str]],
    created: date,
) -> tuple[bytes, list[Any], dict[Any, list[dict[str, Any]]]]:
    """Return the file content, the jobs in it and the jobs that wait with their items.

    ``names`` maps, per kind, the value name of the kind to the name under
    which the job carries the value. ``tables`` are the mapping tables with
    normalised names as keys.
    """
    encoding = settings["encoding"]
    separator = b"\r\n" if settings["record_separator"] == "crlf" else b""
    broker = settings["broker_number"]
    contract_kinds, collection_kinds = settings["contract_kinds"], settings["collection_kinds"]
    waiting: dict[Any, list[dict[str, Any]]] = {}
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    def value(job: dict[str, Any], name: str) -> Any:
        found = job["values"].get(names.get(job["kind"], {}).get(name))
        if isinstance(found, dict):  # a value of a job file: printed text and normalised form
            found = found["text"] if found.get("normalized") is None else found["normalized"]
        return None if found == "" else found

    def code(job: dict[str, Any], name: str, table: str, item: str, items: list) -> str | None:
        approved = value(job, name)
        if approved is None:
            return None
        found = tables[table].get(" ".join(str(approved).split()).casefold())
        if found is None:
            items.append(_item(item, value=approved))
        return found

    for job in jobs:
        if job["kind"] not in (*contract_kinds, *collection_kinds):
            waiting[job["id"]] = [_item("kind_not_handed_over", value=job["kind"])]
            continue
        items = [
            _item(name)
            for name in ("insurer", "policy_number", "policyholder", "line_of_business")
            if value(job, name) is None
        ]
        insurer = code(job, "insurer", "insurers", "insurer_number", items)
        line = code(job, "line_of_business", "lines_of_business", "line_of_business_code", items)
        payment = code(job, "payment_mode", "payment_modes", "payment_mode_code", items)
        if (
            job["kind"] in contract_kinds
            and value(job, "premium") is None
            and value(job, "annual_premium") is not None
            and payment not in WHOLE_PERIOD_MODES
        ):
            # 0200 wants the amount per payment period; instalments carry a
            # surcharge (brochure 3.1.7), so it cannot be derived from a year.
            items.append(_item("premium_per_payment_period"))
        number = key_number(value(job, "policy_number"))
        if value(job, "policy_number") is not None and number is None:
            items.append(_item("value_fits_field", field="policy_number"))
        if items:
            waiting[job["id"]] = items
        else:
            job = {**job, "payment_code": payment}
            groups.setdefault((insurer, number, line), []).append(job)

    # One package per insurer: (sort key, record bytes, gross cents of a collection).
    packages: dict[str, list[tuple[tuple, bytes, int, Any]]] = {}
    written: list[Any] = []

    def record(key, name, part, sequence, values, gross=0):
        insurer, policy_number, line = key
        data = render(name, part, {
            "insurer_number": insurer,
            "line_code": line,
            "policy_number": policy_number,
            "sequence": sequence,
            "broker_number": broker,
            **values,
        }, encoding)
        return (policy_number, sequence, line, name, part), data, gross, values.get("net_premium")

    for key, group in sorted(groups.items()):
        contracts = [j for j in group if j["kind"] in contract_kinds]
        collections = [j for j in group if j["kind"] in collection_kinds]
        holders = {" ".join(str(value(j, "policyholder")).split()) for j in group}
        problem = None
        if len(contracts) > 1:
            problem = _item("one_contract_per_policy_number")
        elif len(holders) > 1:
            problem = _item("same_policyholder")
        else:
            try:
                records = _records(key, contracts, collections, holders.pop(), value, record,
                                   settings)
            except Unfit as unfit:
                problem = _item("value_fits_field", field=unfit.field)
        if problem:
            for job in group:
                waiting[job["id"]] = [problem]
            continue
        packages.setdefault(key[0], []).extend(records)
        written += [job["id"] for job in group]

    out: list[bytes] = []
    for insurer, records in sorted(packages.items()):
        records.sort(key=lambda r: r[0])
        head = {
            "insurer_number": insurer,
            "sender": settings["sender"],
            "addressee": settings["addressee"],
            "created_from": created.isoformat(),
            "created_to": created.isoformat(),
            "broker_number": broker,
        }
        first = {
            **head,
            "sender_kind": settings.get("sender_kind"),
            "addressee_kind": settings.get("addressee_kind"),
            "version_0400": VERSIONS["0400"] if any(r[0][3] == "0400" for r in records) else None,
        }
        out.append(render("0001", 1, first, encoding))
        out += [render("0001", part, head, encoding) for part in (2, 3)]
        out += [r[1] for r in records]
        out.append(render("9999", 1, {
            "count": len(records),
            "broker_number": broker,
            "total_net": Decimal(sum(cents(r[3] or 0) for r in records)) / 100,
            "total_gross": Decimal(sum(r[2] for r in records)) / 100,
        }, encoding))
    return b"".join(checked(data) + separator for data in out), written, waiting


def key_number(printed: Any) -> str | None:
    """A policy number as key field 5 takes it: digits and letters only.

    The record tables allow “Ziffern und Buchstaben (ohne Umlaute und ß)” and
    no special character, a space included; the printed form has its own
    field in 0200. A number that leaves nothing, or a letter outside A to Z,
    has no key form.
    """
    number = "".join(c for c in str(printed or "") if c.isalnum())
    return number if number and number.isascii() else None


def _net_fits(net: Any, gross: Any, payment: str | None) -> bool:
    """Whether an approved net amount is the net amount per payment period.

    With one payment period per year or contract it is. With instalments a
    net amount for the year is at least twice the net amount per period and
    therefore above the gross amount per period, while the net amount per
    period is below it; so the comparison tells the two apart without a
    conversion. Without a gross amount per period nothing tells them apart.
    """
    if net is None or payment in WHOLE_PERIOD_MODES:
        return True
    try:
        return gross is not None and cents(net) <= cents(gross)
    except ValueError:
        return True  # an unreadable amount is named when it is rendered


def _records(key, contracts, collections, holder, value, record, settings) -> list:
    """The records of one contract: address, contract part, one collection per invoice."""
    head = (contracts or collections)[0]
    name_lines = textwrap.wrap(holder, 30, break_long_words=False)
    if len(name_lines) > 3:
        raise Unfit("policyholder")
    currency = settings["currency"]
    gross = net = None
    if contracts:
        net = value(head, "net_premium")
        if not _net_fits(net, value(head, "premium"), head["payment_code"]):
            # A net amount for another period has no field, like the annual
            # amount of a contract paid in instalments; it is left out, not converted.
            net = None
        gross = value(head, "premium")
        if gross is None:
            gross = value(head, "annual_premium")
    records = [
        record(key, "0100", 1, 1, {f"name_{i}": text for i, text in enumerate(name_lines, 1)}),
        record(key, "0200", 1, 1, {
            "collection_kind": settings.get("collection_kind"),
            "contract_status": settings.get("contract_status"),
            "net_premium": net,
            "start_date": value(head, "start_date"),
            "end_date": value(head, "end_date"),
            "payment_code": head["payment_code"],
            "currency": currency,
        }),
        record(key, "0200", 2, 1, {
            "gross_premium": gross,
            "printed_policy_number": value(head, "policy_number"),
            "issue_date": value(head, "issue_date") if contracts else None,
        }),
    ]
    # Annex 2: contract and collection of one run share a sequence number;
    # every further collection for the same policy number counts on.
    for sequence, job in enumerate(collections, 1):
        gross = value(job, "premium")
        try:
            total = cents(gross or 0)
        except ValueError:
            raise Unfit("gross") from None
        records.append(record(key, "0400", 1, sequence, {
            "collection_kind": settings.get("collection_kind"),
            "debit_kind": settings.get("debit_kind"),
            # Field 11 is the start of the billing period, which the table
            # equates with the due date; the due date has no field of its own.
            "period_start": value(job, "period_start") or value(job, "due_date"),
            "period_end": value(job, "period_end"),
            "created": value(job, "invoice_date"),
            "payment_code": job["payment_code"],
            "currency": currency,
            "net": value(job, "net_premium"),
            "tax": value(job, "insurance_tax"),
            "gross": gross,
        }, gross=total))
    return records
