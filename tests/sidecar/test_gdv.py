"""Tests for the GDV hand-over: writer, mapping tables and read-back.

The names carry ``gdv_writer``, ``gdv_mapping`` and ``gdv_roundtrip`` so that
the filters of criteria Z5.1 to Z5.3 select them.

The positions in ``SPEC`` are a third transcription of the record tables of
release 01.12.2023 (https://www.gdv-online.de/vuvm/bestand/rel2023/), written
as the byte address and length the tables print, so that the tests depend on
neither the layout of the writer nor the slices of the reader.
"""

from __future__ import annotations

import ast
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from substrakt import gdv
from substrakt.errors import HandOverTableInvalid, PipelineProfileInvalid
from substrakt.gdv import reader, tables, writer

CREATED = datetime(2026, 11, 10, 9, 30, 0)

HAND_OVER = {
    "format": "gdv",
    "encoding": "cp850",
    "record_separator": "none",
    "broker_number": "4711",
    "sender": "Maklerbüro Beispiel",
    "addressee": "Bestandsprogramm",
    "currency": "EUR",
    "contract_kinds": ["policy"],
    "collection_kinds": ["premium_invoice"],
}

# The values stand under the names the target gives them, as in a job file.
PROFILE = {
    "name": "example",
    "kinds": {
        "policy": {"values": {
            "insurer": "Versicherer", "policy_number": "Nummer", "policyholder": "Kunde",
            "line_of_business": "Sparte", "start_date": "Beginn", "end_date": "Ablauf",
            "payment_mode": "Zahlungsweise", "premium": "Beitrag", "annual_premium": "Jahresbeitrag",
            "net_premium": "Netto", "issue_date": "Ausstellung",
        }},
        "contract_change": {"values": {"insurer": "Versicherer", "policy_number": "Nummer"}},
        "premium_invoice": {"values": {
            "insurer": "Versicherer", "policy_number": "Nummer", "policyholder": "Kunde",
            "line_of_business": "Sparte", "due_date": "Fälligkeit", "premium": "Beitrag",
            "net_premium": "Netto", "insurance_tax": "Steuer", "invoice_date": "Rechnungsdatum",
            "period_start": "Von", "period_end": "Bis", "payment_mode": "Zahlungsweise",
        }},
    },
    "hand_over": HAND_OVER,
}

# (byte address, length) as printed in the record tables.
SPEC = {
    "record": (1, 4), "insurer": (5, 5), "line": (11, 3), "policy": (14, 17), "sequence": (31, 2),
    "broker": (33, 10), "part": (256, 1),
    "0001.sender": (10, 30), "0001.addressee": (40, 30), "0001.created": (70, 16),
    "0001.broker": (86, 10), "0001.v0001": (96, 3), "0001.v0100": (99, 3), "0001.v0200": (102, 3),
    "0001.v0400": (213, 3), "0001.v9999": (225, 3), "0001.sender_kind": (237, 1),
    "0001.addressee_kind": (238, 1),
    "0100.name1": (44, 30), "0100.name2": (74, 30), "0100.role": (237, 2),
    "0200.start": (44, 8), "0200.end": (52, 8), "0200.payment": (68, 1), "0200.currency": (113, 3),
    "0200.net": (116, 12), "0200.gross": (72, 12), "0200.printed": (84, 30),
    "0200.collection_kind": (43, 1), "0200.status": (69, 1), "0200.issued": (147, 8),
    "0400.collection_kind": (43, 1), "0400.debit_kind": (44, 2), "0400.to": (62, 8),
    "0400.created": (71, 8),
    "0400.due": (54, 8), "0400.net": (110, 11), "0400.tax": (122, 11), "0400.gross": (139, 11),
    "0400.gross_sign": (150, 1),
    "9999.count": (5, 10), "9999.broker": (15, 10), "9999.net": (25, 15), "9999.gross": (40, 14),
    "9999.gross_sign": (54, 1),
}


def at(record: str, field: str) -> str:
    start, length = SPEC[field]
    return record[start - 1 : start - 1 + length]


def policy(job_id=1, **values) -> dict:
    return {"id": job_id, "kind": "policy", "values": {
        "Versicherer": "Nordlicht Versicherung AG", "Nummer": "HR4711", "Kunde": "Jörg Müßig",
        "Sparte": "Hausrat", "Beginn": "2026-01-01", "Ablauf": "2027-01-01",
        "Zahlungsweise": "halbjährlich", "Beitrag": 186.4, **values,
    }}


def invoice(job_id=2, **values) -> dict:
    return {"id": job_id, "kind": "premium_invoice", "values": {
        "Versicherer": "Nordlicht Versicherung AG", "Nummer": "HR4711", "Kunde": "Jörg Müßig",
        "Sparte": "Hausrat", "Fälligkeit": "2026-07-01", "Beitrag": "186.40",
        "Netto": "156.64", "Steuer": "29.76", **values,
    }}


FULL_INVOICE = invoice(Rechnungsdatum="2026-06-15", Von="2026-07-01", Bis="2026-12-31",
                       Fälligkeit="2026-07-14", Zahlungsweise="halbjährlich")
CODES = {"sender_kind": "2", "addressee_kind": "9", "contract_status": "1",
         "collection_kind": "2", "debit_kind": "30"}


def fresh(tmp_path: Path) -> Path:
    """A further empty folder, for a second file of the same customer and second."""
    return Path(tempfile.mkdtemp(dir=tmp_path))


def run(tmp_path: Path, jobs: list[dict], **settings) -> dict:
    profile = {**PROFILE, "hand_over": {**HAND_OVER, **settings}}
    return gdv.hand_over(jobs, tmp_path, profile, customer="Müßig", created=CREATED)


def records(result: dict, encoding: str = "cp850", step: int = 256) -> list[str]:
    data = Path(result["file"]).read_bytes()
    assert len(data) % step == 0
    return [data[i : i + 256].decode(encoding) for i in range(0, len(data), step)]


# --- Z5.1: the writer ---------------------------------------------------------


def test_gdv_writer_writes_one_file_per_customer_with_records_of_256_bytes_in_order(tmp_path) -> None:
    other = policy(3, Versicherer="Wattenmeer Assekuranz SE", Nummer="K-99/1", Sparte="Kraftfahrt")
    result = run(tmp_path, [invoice(), other, policy()])
    assert result["written"] and not result["waiting"] and not result["failed"]
    assert [p.name for p in tmp_path.iterdir()] == ["Müßig_20261110-093000.gdv"]

    lines = records(result)
    assert all(len(line.encode("cp850")) == 256 for line in lines)
    # One package per insurer: header in three parts, address, contract part
    # in two parts, the collection record of the invoice, trailer.
    assert [at(r, "record") + (at(r, "part") if at(r, "record") != "9999" else "") for r in lines] == [
        "00011", "00012", "00013", "01001", "02001", "02002", "04001", "9999",
        "00011", "00012", "00013", "01001", "02001", "02002", "9999",
    ]
    assert [at(r, "insurer") for r in lines[:7]] == ["9901 "] * 7
    assert [at(r, "insurer") for r in lines[8:14]] == ["9904 "] * 6


def test_gdv_writer_puts_every_approved_value_at_the_position_of_the_record_table(tmp_path) -> None:
    lines = records(run(tmp_path, [policy(), invoice()]))
    header, address, contract, contract_2, collection = lines[0], *lines[3:7]

    assert at(header, "0001.sender") == "Maklerbüro Beispiel".ljust(30)
    assert at(header, "0001.addressee") == "Bestandsprogramm".ljust(30)
    assert at(header, "0001.created") == "1011202610112026"
    assert at(header, "0001.broker") == "4711      "
    versions = [at(header, f"0001.v{r}") for r in ("0001", "0100", "0200", "0400", "9999")]
    assert versions == ["2.5", "2.3", "2.5", "1.7", "1.1"]

    for line in (address, contract, contract_2, collection):
        assert at(line, "line") == "130"
        assert at(line, "policy") == "HR4711".rjust(17)
        assert at(line, "sequence") == "01"
        assert at(line, "broker") == "4711      "
    assert at(address, "0100.name1") == "Jörg Müßig".ljust(30)
    assert at(address, "0100.role") == "01"
    assert at(contract, "0200.start") == "01012026"
    assert at(contract, "0200.end") == "01012027"
    assert at(contract, "0200.payment") == "2"
    assert at(contract, "0200.currency") == "EUR"
    assert at(contract_2, "0200.gross") == "000000018640"
    assert at(contract_2, "0200.printed") == "HR4711".ljust(30)
    assert at(collection, "0400.due") == "01072026"
    assert at(collection, "0400.net") == "00000015664"
    assert at(collection, "0400.tax") == "00000002976"
    assert at(collection, "0400.gross") + at(collection, "0400.gross_sign") == "00000018640+"
    # A numeric field nobody fills is zeros, an alphanumeric one spaces.
    assert address[225:233] == "00000000" and address[133:153] == " " * 20


def test_gdv_writer_trailer_carries_count_and_control_sums(tmp_path) -> None:
    second = invoice(4, Fälligkeit="2027-01-01", Beitrag="190.00", Netto=None, Steuer=None)
    lines = records(run(tmp_path, [policy(), invoice(), second]))
    trailer = lines[-1]
    assert at(trailer, "record") == "9999"
    # Partial records between header and trailer, as in the GDV sample file.
    assert int(at(trailer, "9999.count")) == len(lines) - 4 == 5
    assert at(trailer, "9999.broker") == "4711      "
    assert int(at(trailer, "9999.net")) == sum(int(at(r, "0200.net")) for r in lines if r[:4] + r[255] == "02001")
    assert at(trailer, "9999.gross") == "00000000037640"
    assert at(trailer, "9999.gross_sign") == "+"
    # The second invoice for the same policy number counts the sequence on.
    assert [at(r, "sequence") for r in lines if r[:4] == "0400"] == ["01", "02"]


@pytest.mark.parametrize(("encoding", "eszett"), [("cp850", b"\xe1"), ("iso-8859-15", b"\xdf")])
def test_gdv_writer_uses_the_encoding_and_separator_the_profile_names(tmp_path, encoding, eszett) -> None:
    result = run(tmp_path, [policy()], encoding=encoding, record_separator="crlf")
    data = Path(result["file"]).read_bytes()
    assert len(data) == 7 * 258 and all(data[i + 256 : i + 258] == b"\r\n" for i in range(0, len(data), 258))
    assert b"M\xfc" not in data or encoding != "cp850"
    assert eszett in data[3 * 258 : 4 * 258]


def test_gdv_writer_cannot_write_a_record_of_another_length() -> None:
    with pytest.raises(AssertionError):
        writer.checked(b" " * 255)
    with pytest.raises(AssertionError):
        writer.checked(b" " * 257)
    # A value longer than its field is refused, not cut.
    with pytest.raises(writer.Unfit):
        writer.render("0100", 1, {"name_1": "x" * 31}, "cp850")
    assert len(writer.render("0100", 1, {"name_1": "x" * 30}, "cp850")) == 256


def test_gdv_writer_layout_has_no_overlap_and_stays_inside_the_record() -> None:
    for key, fields in writer.LAYOUT.items():
        taken = [False] * 256
        for field in fields:
            span = range(field.start - 1, field.start - 1 + field.length)
            assert span.start >= 0 and span.stop <= 256, (key, field.name)
            assert not any(taken[i] for i in span), (key, field.name)
            for i in span:
                taken[i] = True


def test_gdv_writer_holds_back_a_value_that_does_not_fit_its_field(tmp_path) -> None:
    long_number = policy(1, Nummer="1234567890123456789")  # 19 characters, the field has 17
    foreign = policy(2, Nummer="B2", Kunde="Łukasz Nowak")  # no Ł in code page 850
    result = run(tmp_path, [long_number, foreign, policy(3, Nummer="C3")])
    assert result["written"] == [3]
    assert result["waiting"] == {
        1: [{"item": "value_fits_field", "field": "policy_number"}],
        2: [{"item": "value_fits_field", "field": "name_1"}],
    }


def test_gdv_writer_does_not_take_an_annual_amount_for_a_payment_period(tmp_path) -> None:
    yearly = {"Beitrag": None, "Jahresbeitrag": "372.80"}
    result = run(tmp_path, [
        policy(1, Nummer="A1", **yearly),
        policy(2, Nummer="B2", Zahlungsweise="jährlich", **yearly),
    ])
    assert result["waiting"] == {1: [{"item": "premium_per_payment_period"}]}
    assert result["written"] == [2]
    assert at(records(result)[5], "0200.gross") == "000000037280"


def test_gdv_writer_does_not_hand_over_a_contract_change_or_two_policies_of_one_number(tmp_path) -> None:
    change = {"id": 9, "kind": "contract_change", "values": {"Versicherer": "x", "Nummer": "HR4711"}}
    result = run(tmp_path, [change, policy(1), policy(2)])
    assert result["file"] is None and list(tmp_path.iterdir()) == []
    assert result["waiting"] == {
        9: [{"item": "kind_not_handed_over", "value": "contract_change"}],
        1: [{"item": "one_contract_per_policy_number"}],
        2: [{"item": "one_contract_per_policy_number"}],
    }


def test_gdv_writer_needs_the_settings_of_the_profile(tmp_path) -> None:
    with pytest.raises(PipelineProfileInvalid) as missing:
        gdv.hand_over([policy()], tmp_path, {**PROFILE, "hand_over": None}, customer="a")
    assert "hand_over.encoding" in str(missing.value) and "hand_over.broker_number" in str(missing.value)
    with pytest.raises(PipelineProfileInvalid):
        run(tmp_path, [policy()], encoding="utf-8")
    with pytest.raises(PipelineProfileInvalid):
        run(tmp_path, [policy()], password="x")
    assert list(tmp_path.iterdir()) == []


def test_gdv_writer_key_field_holds_the_policy_number_without_special_characters(tmp_path) -> None:
    jobs = [policy(1, Nummer="HR-2026-004711"), invoice(2, Nummer="HR-2026-004711")]
    lines = records(run(tmp_path, jobs))
    # Record tables, field 5: digits and letters only, right-aligned.
    assert [at(r, "policy") for r in lines[3:7]] == ["HR2026004711".rjust(17)] * 4
    assert at(lines[5], "0200.printed") == "HR-2026-004711".ljust(30)

    result = run(fresh(tmp_path), [
        policy(1, Nummer="123 456 789 012 345 678"),  # 18 digits without the spaces
        policy(2, Nummer="MÜ-4711"),  # a letter the key field does not allow
        policy(3, Nummer="-/-"),  # nothing left
        policy(4, Nummer="12.345.678-901/234 567"),  # 17 digits: fits
    ])
    assert result["written"] == [4]
    assert all(items == [{"item": "value_fits_field", "field": "policy_number"}]
               for items in result["waiting"].values()) and set(result["waiting"]) == {1, 2, 3}


def test_gdv_writer_writes_the_net_amount_only_when_it_is_one_per_payment_period(tmp_path) -> None:
    result = run(tmp_path, [
        policy(1, Nummer="A1", Netto="156.64"),  # half-yearly, below the gross amount per period
        policy(2, Nummer="B2", Netto="313.28"),  # above it: the net amount of a year
        policy(3, Nummer="C3", Zahlungsweise="jährlich", Beitrag=None, Jahresbeitrag="372.80",
               Netto="313.28"),
        policy(4, Nummer="D4", Beitrag=None, Netto="156.64"),  # nothing to tell it by
    ])
    # A net amount for a year is left out, not converted, and blocks nothing.
    assert not result["waiting"] and not result["failed"]
    lines = records(result)
    assert [at(r, "0200.net") for r in lines if r[:4] + r[255] == "02001"] == [
        "000000015664", "000000000000", "000000031328", "000000000000",
    ]
    # The first sum of the trailer adds exactly this field.
    assert at(lines[-1], "9999.net") == "000000000046992"


def test_gdv_writer_writes_the_dates_of_policy_and_invoice_into_their_fields(tmp_path) -> None:
    lines = records(run(tmp_path, [policy(Ausstellung="2025-12-10"), FULL_INVOICE]))
    assert at(lines[5], "0200.issued") == "10122025"
    collection = lines[6]
    # Field 11 is the start of the billing period; the due date has no field of its own.
    assert at(collection, "0400.due") == "01072026"
    assert at(collection, "0400.to") == "31122026"
    assert at(collection, "0400.created") == "15062026"
    # Without a period, the due date is what field 11 gets.
    assert at(records(run(fresh(tmp_path), [invoice(Fälligkeit="2026-07-14")]))[6], "0400.due") == "14072026"


def test_gdv_writer_takes_codes_that_are_on_no_paper_from_the_profile_only(tmp_path) -> None:
    lines = records(run(tmp_path, [policy(), invoice()], **CODES))
    assert at(lines[0], "0001.sender_kind") + at(lines[0], "0001.addressee_kind") == "29"
    assert at(lines[4], "0200.status") == "1" and at(lines[4], "0200.collection_kind") == "2"
    assert at(lines[6], "0400.collection_kind") + at(lines[6], "0400.debit_kind") == "230"

    # A profile that does not name them leaves them empty: no code is guessed.
    lines = records(run(fresh(tmp_path), [policy(), invoice()]))
    assert at(lines[0], "0001.sender_kind") + at(lines[0], "0001.addressee_kind") == "  "
    assert at(lines[4], "0200.status") + at(lines[4], "0200.collection_kind") == "  "
    assert at(lines[6], "0400.collection_kind") + at(lines[6], "0400.debit_kind") == "   "
    for wrong in ({"contract_status": "X"}, {"sender_kind": "5"}, {"debit_kind": "3"}):
        with pytest.raises(PipelineProfileInvalid):
            run(tmp_path, [policy()], **wrong)


def test_gdv_writer_header_announces_the_collection_record_only_where_one_follows(tmp_path) -> None:
    other = policy(3, Versicherer="Wattenmeer Assekuranz SE", Nummer="K1", Sparte="Kraftfahrt")
    lines = records(run(tmp_path, [policy(), invoice(), other]))
    assert [at(r, "0001.v0400") for r in lines if r[:4] + r[255] == "00011"] == ["1.7", "   "]


# --- Z5.2: mapping tables -----------------------------------------------------


def test_gdv_mapping_unknown_insurer_is_not_written_and_is_named(tmp_path) -> None:
    result = run(tmp_path, [policy(1, Versicherer="Unbekannte Gesellschaft AG"), policy(2, Nummer="B2")])
    assert result["waiting"] == {1: [{"item": "insurer_number", "value": "Unbekannte Gesellschaft AG"}]}
    assert result["written"] == [2]
    assert "Unbekannte" not in Path(result["file"]).read_bytes().decode("cp850")
    assert len(records(result)) == 7


def test_gdv_mapping_unknown_line_of_business_and_payment_mode_are_named(tmp_path) -> None:
    result = run(tmp_path, [policy(1, Sparte="Reisegepäck", Zahlungsweise="wöchentlich")])
    assert result["file"] is None and list(tmp_path.iterdir()) == []
    assert result["waiting"] == {1: [
        {"item": "line_of_business_code", "value": "Reisegepäck"},
        {"item": "payment_mode_code", "value": "wöchentlich"},
    ]}


def test_gdv_mapping_missing_approved_value_is_named(tmp_path) -> None:
    result = run(tmp_path, [policy(1, Versicherer=None, Nummer="")])
    assert result["waiting"] == {1: [{"item": "insurer"}, {"item": "policy_number"}]}


def test_gdv_mapping_codes_come_from_the_table_files(tmp_path) -> None:
    assert tables.load("lines_of_business")["hausrat"] == "130"
    assert tables.load("payment_modes") == {
        "jährlich": "1", "halbjährlich": "2", "vierteljährlich": "4", "einmalig": "6", "monatlich": "8",
    }
    # Case and spacing of an approved name do not count; another spelling does.
    result = run(tmp_path, [policy(1, Versicherer="  nordlicht  versicherung ag"),
                            policy(2, Nummer="B2", Versicherer="Nordlicht Versicherungs-AG")])
    assert result["written"] == [1] and list(result["waiting"]) == [2]


def test_gdv_mapping_table_in_the_data_directory_replaces_the_bundled_one(tmp_path) -> None:
    custom = tmp_path / "gdv"
    custom.mkdir()
    (custom / "insurers.yml").write_text(
        'name: insurers\nsource: test\nentries:\n  Echte Gesellschaft AG: "5312"\n', encoding="utf-8"
    )
    tables.configure(custom)
    try:
        assert tables.load("insurers") == {"echte gesellschaft ag": "5312"}
        assert tables.load("payment_modes")["monatlich"] == "8"
    finally:
        tables.configure(None)


@pytest.mark.parametrize("content", [
    'name: insurers\nsource: test\nentries: {A: "1"}\ncomment: x\n',  # unknown key
    "name: insurers\nsource: test\nentries: {A: 5312}\n",  # a number loses its leading zero
    'name: insurers\nsource: test\nentries: {A: "123456"}\n',  # longer than the field
    'name: insurers\nsource: test\nentries: {A: "1", " a ": "2"}\n',  # one name twice
    'name: payment_modes\nsource: test\nentries: {A: "1"}\n',  # another table's name
])
def test_gdv_mapping_table_with_an_unknown_key_or_a_wrong_code_is_rejected(tmp_path, content) -> None:
    (tmp_path / "insurers.yml").write_text(content, encoding="utf-8")
    tables.configure(tmp_path)
    try:
        with pytest.raises(HandOverTableInvalid):
            tables.load("insurers")
    finally:
        tables.configure(None)


# --- Z5.3: read-back ----------------------------------------------------------


def test_gdv_roundtrip_reader_shares_no_code_with_the_writer() -> None:
    tree = ast.parse(Path(reader.__file__).read_text(encoding="utf-8"))
    imported = {
        name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for name in ([node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names])
    }
    assert imported == {"__future__", "decimal", "re", "typing"}


def test_gdv_roundtrip_values_read_back_equal_the_approved_values(tmp_path) -> None:
    jobs = [policy(), invoice(), policy(3, Versicherer="Wattenmeer Assekuranz SE", Nummer="K-99/1",
                                        Sparte="Kraftfahrt", Zahlungsweise="jährlich",
                                        Kunde="Tischlerei Okafor & Söhne Gesellschaft mit beschränkter Haftung")]
    result = run(tmp_path, jobs, record_separator="crlf")
    assert sorted(result["written"]) == [1, 2, 3] and not result["failed"]
    contracts = reader.parse(Path(result["file"]).read_bytes(), "cp850", b"\r\n")
    assert contracts["9901", "HR4711", "130"] == {
        "broker": "4711", "name": "Jörg Müßig", "role": "01", "start": "01012026", "end": "01012027",
        "payment": "2", "currency": "EUR", "gross": 18640, "net": 0, "printed": "HR4711",
        "issued": "00000000", "status": "", "collection_kind": "", "header": "  ",
        "announces_0400": True,
        "collections": [{"from": "01072026", "to": "00000000", "created": "00000000", "kinds": "",
                         "payment": "", "net": 15664, "tax": 2976, "gross": 18640, "signs": "+++"}],
    }
    # A name longer than one field continues in the next and reads back whole.
    # The key holds the number without its special characters, the printed field with them.
    assert contracts["9904", "K991", "050"]["name"] == jobs[2]["values"]["Kunde"]
    assert contracts["9904", "K991", "050"]["printed"] == "K-99/1"


@pytest.mark.parametrize("field", [
    "start_date", "gross_premium", "name_1", "policy_number", "net_premium", "issue_date",
    "period_end", "created", "contract_status", "debit_kind", "sender_kind",
])
def test_gdv_roundtrip_mismatch_marks_the_jobs_failed_and_removes_the_file(tmp_path, monkeypatch, field) -> None:
    # A slip in the writer's layout: one field lands one byte too far left.
    layout = dict(writer.LAYOUT)
    for key, fields in layout.items():
        layout[key] = tuple(
            writer.Field(f.name, f.start - 1, f.length, f.kind, f.const) if f.name == field else f
            for f in fields
        )
    monkeypatch.setattr(writer, "LAYOUT", layout)
    result = run(tmp_path, [policy(Netto="156.64", Ausstellung="2025-12-10"), FULL_INVOICE], **CODES)
    assert result["file"] is None and result["written"] == []
    assert set(result["failed"]) == {1, 2} and all(result["failed"].values())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("damage", [
    lambda d: d[:-1],  # a record of 255 bytes
    lambda d: d[:-256],  # no trailer
    lambda d: d[: 7 * 256 + 13] + b"9" + d[7 * 256 + 14 :],  # wrong count in the trailer
    lambda d: d[: 7 * 256 + 52] + b"1" + d[7 * 256 + 53 :],  # wrong sum in the trailer
    lambda d: d[: 6 * 256 + 148] + b"1" + d[6 * 256 + 149 :],  # another amount in the collection
    lambda d: d[: 4 * 256 + 50] + b"7" + d[4 * 256 + 51 :],  # another start date
    lambda d: d[: 3 * 256] + d[4 * 256 :],  # the address record is gone
])
def test_gdv_roundtrip_reader_finds_a_damaged_file(tmp_path, damage) -> None:
    jobs = [policy(), invoice()]
    data = Path(run(tmp_path, jobs)["file"]).read_bytes()
    names = {kind: spec["values"] for kind, spec in PROFILE["kinds"].items()}
    assert reader.check(data, jobs, names, HAND_OVER, tables.load_all()) is None
    assert reader.check(damage(data), jobs, names, HAND_OVER, tables.load_all())


def test_gdv_roundtrip_takes_the_normalised_form_of_a_job_file_value(tmp_path) -> None:
    job = policy(1, Beginn={"text": "1. Januar 2026", "normalized": "2026-01-01"},
                 Beitrag={"text": "186,40 EUR", "normalized": 186.4},
                 Kunde={"text": "Jörg Müßig", "normalized": None})
    result = run(tmp_path, [job])
    assert result["written"] == [1] and not result["failed"]
    lines = records(result)
    assert at(lines[4], "0200.start") == "01012026" and at(lines[5], "0200.gross") == "000000018640"


def test_gdv_roundtrip_refuses_to_replace_an_existing_file(tmp_path) -> None:
    first = run(tmp_path, [policy()])
    before = Path(first["file"]).read_bytes()
    second = run(tmp_path, [policy(1, Kunde="Jemand Anderes")])
    assert second["file"] is None and second["failed"] == {1: "a file of that name exists"}
    assert Path(first["file"]).read_bytes() == before
