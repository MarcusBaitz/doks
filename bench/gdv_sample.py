"""Write a sample GDV file and the values it was made from, for an independent review.

A reviewer who has only the specification, the file and the inputs can check
the writer without reading it. This script calls the entry point of the
application, ``substrakt.gdv.hand_over``, with invented jobs and writes

- ``sample.gdv``  the file, byte for byte as the application names it, and
- ``inputs.md``   every approved value, setting and code that went in.

Nothing is written into the repository: the target is a folder you name, or
a new temporary folder whose path is printed.

    cd sidecar && uv run python ../bench/gdv_sample.py [folder]

``docs/gdv-hand-over.md``, section “Independent review”, says what the
review of 10 November 2026 found.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from substrakt import gdv
from substrakt.gdv import tables

CREATED = datetime(2026, 11, 10, 9, 30, 0)
CUSTOMER = "Müller"

SETTINGS = {
    "format": "gdv",
    "encoding": "iso-8859-1",
    "record_separator": "crlf",
    "broker_number": "4711",
    "sender": "Maklerbüro Schönfeld",
    "addressee": "Bestandsprogramm",
    "currency": "EUR",
    "sender_kind": "2",
    "addressee_kind": "9",
    "contract_status": "1",
    "collection_kind": "2",
    "debit_kind": "30",
    "contract_kinds": ["policy"],
    "collection_kinds": ["premium_invoice"],
}

# (kind, note for the reviewer, values under the names of the document kinds)
JOBS = [
    ("policy", "annual payment; the document prints only the amount for a year", {
        "insurer": "Nordlicht Versicherung AG", "policy_number": "HR-2026-004711",
        "policyholder": "Jörg Müller", "line_of_business": "Hausrat",
        "start_date": "2026-01-01", "end_date": "2027-01-01", "issue_date": "2025-12-10",
        "payment_mode": "jährlich", "annual_premium": "248.90", "net_premium": "209.16",
    }),
    ("policy", "quarterly payment; premium and net premium are per quarter", {
        "insurer": "Wattenmeer Assekuranz SE", "policy_number": "KF-88/2026-15",
        "policyholder": "Jörg Müller", "line_of_business": "Kraftfahrt",
        "start_date": "2026-04-01", "end_date": "2027-04-01", "issue_date": "2026-03-12",
        "payment_mode": "vierteljährlich", "premium": "163.74", "annual_premium": "654.96",
        "net_premium": "137.60",
    }),
    ("premium_invoice", "invoice for the contract above; payable two weeks after the period starts", {
        "insurer": "Wattenmeer Assekuranz SE", "policy_number": "KF-88/2026-15",
        "policyholder": "Jörg Müller", "line_of_business": "Kraftfahrt",
        "invoice_date": "2026-06-15", "period_start": "2026-07-01", "period_end": "2026-09-30",
        "due_date": "2026-07-15", "payment_mode": "vierteljährlich", "net_premium": "137.60",
        "insurance_tax": "26.14", "premium": "163.74",
    }),
    ("premium_invoice", "second invoice for the same contract", {
        "insurer": "Wattenmeer Assekuranz SE", "policy_number": "KF-88/2026-15",
        "policyholder": "Jörg Müller", "line_of_business": "Kraftfahrt",
        "invoice_date": "2026-09-15", "period_start": "2026-10-01", "period_end": "2026-12-31",
        "due_date": "2026-10-15", "payment_mode": "vierteljährlich", "net_premium": "137.60",
        "insurance_tax": "26.14", "premium": "163.74",
    }),
]


def inputs(result: dict) -> str:
    lines = [
        "# Inputs of sample.gdv", "",
        f"One customer (“{CUSTOMER}”), {len(JOBS)} approved jobs, handed over in one call.",
        f"Creation time passed to the call: {CREATED:%d %B %Y, %H:%M:%S}.",
        "Dates are ISO dates (YYYY-MM-DD), amounts in euros with a decimal point.",
        "The approved values contain no street, postcode, town, date of birth, commission",
        "or fee: the document kinds do not deliver such values.", "",
    ]
    for number, (kind, note, values) in enumerate(JOBS, 1):
        lines += [f"## Job {number}: {kind}", "", note + ".", "", "| Value | Approved value |", "|---|---|"]
        lines += [f"| {name} | {value} |" for name, value in values.items()] + [""]
    lines += ["## Profile settings", "", "| Setting | Value |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in SETTINGS.items()] + [""]
    used = {name: {str(v[name]) for _, _, v in JOBS if name in v}
            for name in ("insurer", "line_of_business", "payment_mode")}
    for table, name in (("insurers", "insurer"), ("lines_of_business", "line_of_business"),
                        ("payment_modes", "payment_mode")):
        codes = tables.load(table)
        lines += [f"## Codes from the mapping table {table}", "", "| Name | Code |", "|---|---|"]
        lines += [f"| {value} | {codes[tables.norm(value)]} |" for value in sorted(used[name])] + [""]
    lines += ["The insurers and their numbers are invented.", "",
              "## What the call returned", "",
              f"Written: jobs {sorted(result['written'])}. Held back: {result['waiting'] or 'none'}.",
              f"Read-back by the application's own reader: {result['failed'] or 'no difference'}.", ""]
    return "\n".join(lines)


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="gdv-sample-"))
    target.mkdir(parents=True, exist_ok=True)
    kinds = {kind: {"values": {}} for kind, _, _ in JOBS}
    for kind, _, values in JOBS:
        # The jobs carry every value under the name the kind gives it.
        kinds[kind]["values"] |= {name: name for name in values}
    profile = {"name": "sample", "kinds": kinds, "hand_over": SETTINGS}
    jobs = [{"id": i, "kind": kind, "values": values} for i, (kind, _, values) in enumerate(JOBS, 1)]
    with tempfile.TemporaryDirectory() as folder:
        result = gdv.hand_over(jobs, Path(folder), profile, customer=CUSTOMER, created=CREATED)
        if result["file"] is None:
            sys.exit(f"No file was written: {result}")
        shutil.copyfile(result["file"], target / "sample.gdv")
    (target / "inputs.md").write_text(inputs(result), encoding="utf-8")
    print(f"{target / 'sample.gdv'} ({(target / 'sample.gdv').stat().st_size} bytes)")
    print(target / "inputs.md")


if __name__ == "__main__":
    main()
