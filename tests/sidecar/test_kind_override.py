"""A person changes the values of a kind in Templates; the next document read uses them."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import Desk, put, variant
from fastapi.testclient import TestClient
from test_api import auth, client  # noqa: F401  (the app with a data directory of its own)

from substrakt import document_kinds, kind_values, pipeline_profiles
from substrakt.errors import KindChangeRefused
from substrakt.jobs import Jobs
from substrakt.kind_values import ValueChange, ValuesChange

ROOT = Path(__file__).resolve().parents[2]
DICTIONARIES = [ROOT / "src" / "i18n" / "de.ts", ROOT / "src" / "i18n" / "en.ts"]

# A profile that takes two values of an invoice and hands over a third when it is read.
TAKES_THREE = """\
name: scans
title: Test
target: test_target
customer_folder_level: 1
overview_columns:
  document_number: Nummer
  total_amount: Betrag
kinds:
  invoice:
    values:
      document_number: Nummer
      total_amount: Betrag
    optional:
      currency: Währung
"""


def current(kind: str = "invoice") -> list[ValueChange]:
    """The values of a kind as Templates sends them back unchanged."""
    return [ValueChange(name=f.name, label=f.label) for f in document_kinds.load(kind).fields]


def change(values: list[ValueChange], kind: str = "invoice") -> kind_values.KindValues:
    return kind_values.change(kind, ValuesChange(values=values))


def value(entry, name: str):
    return next((v for v in entry.values if v.field == name), None)


def test_kind_override_rename_changes_the_label_only_and_never_the_shipped_file(desk: Desk) -> None:
    shipped = (document_kinds.BUILTIN / "invoice.yml").read_bytes()
    values = current()
    number = next(v for v in values if v.name == "document_number")
    number.label = "Belegnummer"

    changed = change(values)

    assert (document_kinds.BUILTIN / "invoice.yml").read_bytes() == shipped
    assert (desk.root / "kinds" / "invoice.yml").is_file()
    assert [v.name for v in changed.values] == [
        f.name for f in document_kinds.load("invoice").fields
    ]
    field = next(f for f in document_kinds.load("invoice").fields if f.name == "document_number")
    assert field.label == "Belegnummer"
    shipped_kind = document_kinds.load("invoice", custom=desk.root / "nowhere")
    assert field.label_rule == shipped_kind.rule_for("document_number"), "it is found as before"
    assert not list((desk.root / "kinds").glob(".*")), "no temporary file is left"


def test_kind_override_new_value_is_read_from_the_next_document_without_a_restart(
    desk: Desk, invoice: bytes
) -> None:
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Meier/before.pdf", invoice)
    desk.settle()

    changed = change([*current(), ValueChange(label="Kundennummer")])
    put(desk, "Meier/after.pdf", variant(invoice, 1))
    desk.settle()

    added = changed.values[-1]
    assert (added.name, added.label) == ("kundennummer", "Kundennummer")
    entries = desk.entries()
    assert value(entries["Meier/before.pdf"], "kundennummer") is None, "a stored entry stays"
    read = value(entries["Meier/after.pdf"], "kundennummer")
    assert read is not None
    assert (read.value, read.grounded) == ("K-4711", True)


def test_kind_override_removing_a_value_the_profile_expects_keeps_the_profile_valid(
    desk: Desk, invoice: bytes
) -> None:
    profiles = desk.root / "profiles"
    (profiles / "scans.yml").write_text(TAKES_THREE, encoding="utf-8")
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Meier/scan.pdf", invoice)
    desk.settle()
    [before] = desk.inbox.entries()

    change([v for v in current() if v.name not in ("total_amount", "currency")])

    profile = pipeline_profiles.load("scans")
    assert profile.kinds["invoice"].values == {"document_number": "Nummer"}
    assert profile.kinds["invoice"].optional == {}
    assert profile.overview_columns == {"document_number": "Nummer"}
    assert profile.target == "test_target"
    [after] = desk.inbox.entries()
    assert after.values == before.values, "values already read are not rewritten"
    job = Jobs(desk.inbox).approve(after.id)
    # Approved: the job went to the output folder, where the test target has no writer.
    assert job.transitions[-1].reason == "target-without-writer"

    put(desk, "Meier/next.pdf", variant(invoice, 1))
    desk.settle()
    entry = desk.entries()["Meier/next.pdf"]
    assert entry.state == "waiting", "reading goes on with the changed profile"
    assert value(entry, "total_amount") is None


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ([], "no-value-left"),
        ([ValueChange(name="document_number", label="  ")], "label-empty"),
        (
            [ValueChange(name="document_number", label="Nummer"), ValueChange(label="nummer")],
            "label-twice",
        ),
        ([ValueChange(name="no_such_value", label="Nummer")], "value-unknown"),
        # The test profile takes only the number; without it the target gets nothing.
        ([ValueChange(name="total_amount", label="Betrag")], "target-needs-a-value"),
    ],
)
def test_kind_override_refused_change_writes_no_file(
    desk: Desk, values: list[ValueChange], reason: str
) -> None:
    kinds = sorted((desk.root / "kinds").iterdir())
    profiles = {p: p.read_bytes() for p in (desk.root / "profiles").iterdir()}

    with pytest.raises(KindChangeRefused) as refused:
        change(values)

    assert refused.value.fields["reason"] == reason
    assert sorted((desk.root / "kinds").iterdir()) == kinds
    assert {p: p.read_bytes() for p in (desk.root / "profiles").iterdir()} == profiles


def test_kind_override_a_broken_profile_does_not_block_a_change(desk: Desk) -> None:
    (desk.root / "profiles" / "broken.yml").write_text("name: [\n", encoding="utf-8")

    change([v for v in current() if v.name != "currency"])

    assert "currency" not in [f.name for f in document_kinds.load("invoice").fields]


def test_kind_override_a_change_that_fails_validation_writes_nothing(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid(_data: object) -> None:
        kind_values.FieldSpec.model_validate({})  # raises a real ValidationError

    monkeypatch.setattr(kind_values.DocumentKind, "model_validate", invalid)
    kinds = sorted((desk.root / "kinds").iterdir())

    with pytest.raises(KindChangeRefused) as refused:
        change(current())

    assert refused.value.fields["reason"] == "invalid"
    assert sorted((desk.root / "kinds").iterdir()) == kinds


def test_kind_override_a_failed_write_leaves_neither_file_nor_temporary_name(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full_disk(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(kind_values.os, "replace", full_disk)
    kinds = sorted((desk.root / "kinds").iterdir())

    with pytest.raises(OSError):
        change(current())

    assert sorted((desk.root / "kinds").iterdir()) == kinds


def test_kind_override_without_user_directories_nothing_is_changed(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_kinds, "custom_directory", lambda: None)

    with pytest.raises(RuntimeError):
        change(current())


def test_kind_override_new_names_start_with_a_letter_and_never_reuse_a_name() -> None:
    assert kind_values._free_name("1. Rate", set()) == "value_1_rate"
    assert kind_values._free_name("Währung", {"wahrung"}) == "wahrung_2"
    assert kind_values._free_name("Währung", {"wahrung", "wahrung_2"}) == "wahrung_3"


def test_kind_override_refusal_has_a_text_in_both_dictionaries() -> None:
    for dictionary in DICTIONARIES:
        assert f"'{KindChangeRefused.key}'" in dictionary.read_text(encoding="utf-8")


def test_kind_override_endpoints_list_kinds_and_store_a_change(client: TestClient) -> None:  # noqa: F811
    listed = client.get("/document-kinds", headers=auth())
    assert listed.status_code == 200
    policy = next(k for k in listed.json() if k["name"] == "policy")
    assert policy["title"] == "Police"
    values = [{"name": v["name"], "label": v["label"]} for v in policy["values"]]
    values[0]["label"] = "Gesellschaft"

    stored = client.post("/document-kinds/policy/values", json={"values": values}, headers=auth())

    assert stored.status_code == 200
    assert stored.json()["values"][0] == {"name": "insurer", "label": "Gesellschaft"}
    refused = client.post("/document-kinds/policy/values", json={"values": []}, headers=auth())
    assert refused.status_code == 409
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert (refused.json()["key"], refused.json()["reason"]) == (
        "kind-change-refused",
        "no-value-left",
    )
