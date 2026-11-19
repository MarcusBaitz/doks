"""The watched folder feeds a durable inbox: real files, a real database, no sleep."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from conftest import Desk, put, variant

from substrakt import pipeline_profiles
from substrakt.errors import (
    FileNotFound,
    OutputNameTaken,
    PathNotAllowed,
    PipelineProfileUnknown,
)
from substrakt.inbox import Inbox
from substrakt.parsers import ocr
from substrakt.store import file_hash

ROOT = Path(__file__).resolve().parents[2]
DICTIONARIES = [ROOT / "src" / "i18n" / "de.ts", ROOT / "src" / "i18n" / "en.ts"]

# --- Z3.1 --------------------------------------------------------------------


def test_inbox_reads_a_file_only_after_it_has_stopped_growing(desk: Desk, invoice: bytes) -> None:
    desk.inbox.choose_folder(str(desk.folder))
    half = len(invoice) // 2
    file = put(desk, "Meier/scan.pdf", invoice[:half])

    desk.inbox.poll()
    assert desk.inbox.entries() == []

    with file.open("ab") as growing:
        growing.write(invoice[half:])
    desk.inbox.poll()
    assert desk.inbox.entries() == [], "a file that changed since the last look is not read"

    desk.inbox.poll()
    [entry] = desk.inbox.entries()
    assert entry.state == "waiting"
    assert entry.sha256 == file_hash(file)
    assert desk.parsed == {"scan.pdf": 1}


def test_inbox_takes_scans_and_ignores_other_files(desk: Desk, invoice: bytes) -> None:
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Meier/scan.pdf", invoice)
    put(desk, "Meier/Thumbs.db", b"not a scan")
    put(desk, "Meier/list.xlsx", b"not a scan")

    desk.settle()

    assert list(desk.entries()) == ["Meier/scan.pdf"]


@pytest.mark.skipif(not ocr.available(), reason="Tesseract or deu.traineddata is unavailable")
def test_inbox_reads_a_scanned_file_through_text_recognition(desk: Desk, corpus: Path) -> None:
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Meier/scan.png", (corpus / "rechnung_scan_300dpi.png").read_bytes())

    desk.settle()

    [entry] = desk.inbox.entries()
    assert (entry.state, entry.kind, entry.page_count) == ("waiting", "invoice", 1)
    number = next(value for value in entry.values if value.field == "document_number")
    assert (number.value, number.grounded) == ("2026-0147", True)
    assert number.locator is not None


# --- Z3.2 --------------------------------------------------------------------


def test_inbox_entries_survive_a_restart_with_values_locations_and_timings(
    desk: Desk, invoice: bytes
) -> None:
    desk.inbox.choose_folder(str(desk.folder))
    file = put(desk, "Meier/scan.pdf", invoice)
    desk.settle()
    before = desk.inbox.entries()

    desk.inbox.stop()
    after = desk.restart().entries()

    assert after == before
    [entry] = after
    assert (entry.state, entry.file_path, entry.kind) == ("waiting", str(file), "invoice")
    assert entry.sha256 == file_hash(file)
    number = next(value for value in entry.values if value.field == "document_number")
    assert number.value == "2026-0147"
    assert number.locator is not None
    assert set(entry.timings) == {"stable_ms", "parse_ms", "extraction_ms", "total_ms"}


def test_inbox_table_has_no_column_for_document_text_or_images(desk: Desk) -> None:
    conn = sqlite3.connect(desk.database)
    try:
        columns = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(inbox_entry)")}
    finally:
        conn.close()

    assert set(columns) == {
        "id", "import_id", "state", "file_path", "sha256", "customer", "profile", "kind",
        "page_count", "values_json", "timings_json", "duplicate_of", "problem_key",
        "later_arrival", "arrived_at", "comparison_key", "possible_duplicate_of",
        "duplicate_decision", "duplicate_decided_by", "duplicate_decided_at",
    }
    assert "BLOB" not in columns.values()


def test_inbox_database_holds_no_text_of_the_document_beyond_its_values(
    desk: Desk, invoice: bytes
) -> None:
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Meier/scan.pdf", invoice)
    desk.settle()
    desk.inbox.stop()

    stored = b"".join(file.read_bytes() for file in desk.database.parent.iterdir())

    assert b"2026-0147" in stored, "the read value is stored"
    for elsewhere_on_the_page in (b"Grubenrand", b"Wartungspauschale", b"Lieferdatum", b"K-4711"):
        assert elsewhere_on_the_page not in stored


# --- Z3.4 --------------------------------------------------------------------


def test_inbox_error_entry_has_a_stable_key_is_not_retried_and_does_not_stop_the_rest(
    desk: Desk, invoice: bytes
) -> None:
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Meier/a_broken.pdf", b"%PDF-1.4\nthis is not a document\n")
    put(desk, "Meier/b_good.pdf", invoice)

    desk.settle()
    entries = desk.entries()
    broken, good = entries["Meier/a_broken.pdf"], entries["Meier/b_good.pdf"]

    assert (broken.state, broken.problem_key) == ("error", "document-corrupt")
    assert broken.values == []
    assert good.state == "waiting"
    for dictionary in DICTIONARIES:
        assert f"'{broken.problem_key}'" in dictionary.read_text(encoding="utf-8")

    desk.settle()
    desk.inbox.stop()
    desk.restart()
    desk.settle()
    assert desk.parsed == {"a_broken.pdf": 1, "b_good.pdf": 1}
    assert len(desk.inbox.entries()) == 2


def test_inbox_error_of_an_unexpected_kind_becomes_an_entry_with_the_internal_key(
    desk: Desk, invoice: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(path: Path, sha: str):
        raise RuntimeError("parser bug")

    monkeypatch.setattr(desk.store, "parse", explode)
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Meier/scan.pdf", invoice)

    desk.settle()

    [entry] = desk.inbox.entries()
    assert (entry.state, entry.problem_key) == ("error", "internal-error")


# --- Z3.5 --------------------------------------------------------------------


def test_inbox_roots_refuse_a_folder_outside_them_and_a_system_directory(
    desk: Desk, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")

    for refused in (outside, Path("/etc"), Path("/"), desk.root.parent):
        with pytest.raises(PathNotAllowed):
            desk.inbox.choose_folder(str(refused))

    assert desk.inbox.settings().folder is None
    desk.settle()
    assert desk.inbox.entries() == []


def test_inbox_roots_refuse_a_link_that_leads_out_of_them(
    desk: Desk, invoice: bytes, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret.pdf").write_bytes(invoice)
    (desk.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathNotAllowed):
        desk.inbox.choose_folder(str(desk.root / "link"))

    desk.inbox.choose_folder(str(desk.folder))
    (desk.folder / "Meier").mkdir()
    (desk.folder / "Meier" / "linked.pdf").symlink_to(outside / "secret.pdf")
    desk.settle()

    [entry] = desk.inbox.entries()
    assert (entry.state, entry.problem_key) == ("error", "path-not-allowed")
    assert desk.parsed == {}


def test_inbox_roots_refuse_everything_when_the_shell_passed_none(desk: Desk) -> None:
    unrestricted = Inbox(desk.database, desk.store, [])

    with pytest.raises(PathNotAllowed):
        unrestricted.choose_folder(str(desk.folder))


def test_inbox_folder_must_exist_and_be_a_folder(desk: Desk, invoice: bytes) -> None:
    file = put(desk, "scan.pdf", invoice)

    for missing in (desk.root / "absent", file):
        with pytest.raises(FileNotFound):
            desk.inbox.choose_folder(str(missing))


# --- Z3.8 --------------------------------------------------------------------


def test_inbox_customer_folder_import_takes_everything_already_there(
    desk: Desk, invoice: bytes
) -> None:
    put(desk, "Meier/policy.pdf", variant(invoice, 1))
    put(desk, "Schulze GmbH/2026/invoice.pdf", variant(invoice, 2))
    put(desk, "loose.pdf", variant(invoice, 3))

    desk.inbox.choose_folder(str(desk.folder))
    desk.settle()
    entries = desk.entries()

    assert {path: entry.customer for path, entry in entries.items()} == {
        "Meier/policy.pdf": "Meier",
        "Schulze GmbH/2026/invoice.pdf": "Schulze GmbH",
        "loose.pdf": None,
    }
    assert {entry.state for entry in entries.values()} == {"waiting"}
    assert not any(entry.later_arrival for entry in entries.values())
    assert len({entry.import_id for entry in entries.values()}) == 1


def test_inbox_customer_folder_chosen_twice_starts_no_second_import(
    desk: Desk, invoice: bytes
) -> None:
    put(desk, "Meier/policy.pdf", invoice)
    desk.inbox.choose_folder(str(desk.folder))
    desk.settle()

    desk.inbox.choose_folder(str(desk.folder))
    desk.settle()

    assert len(desk.inbox.entries()) == 1
    assert desk.parsed == {"policy.pdf": 1}
    assert desk.inbox.settings().folder == str(desk.folder)


# --- Z3.10 -------------------------------------------------------------------


def test_inbox_later_arrival_is_read_also_after_a_restart_and_old_files_are_read_once(
    desk: Desk, invoice: bytes
) -> None:
    put(desk, "Meier/first.pdf", variant(invoice, 1))
    desk.inbox.choose_folder(str(desk.folder))
    desk.settle()

    put(desk, "Meier/second.pdf", variant(invoice, 2))
    desk.settle()

    desk.inbox.stop()
    desk.restart()
    desk.settle()
    put(desk, "Meier/third.pdf", variant(invoice, 3))
    desk.settle()
    entries = desk.entries()

    assert {path: entry.later_arrival for path, entry in entries.items()} == {
        "Meier/first.pdf": False,
        "Meier/second.pdf": True,
        "Meier/third.pdf": True,
    }
    assert {entry.customer for entry in entries.values()} == {"Meier"}
    assert {entry.state for entry in entries.values()} == {"waiting"}
    assert desk.parsed == {"first.pdf": 1, "second.pdf": 1, "third.pdf": 1}


# An entry that a crash left unfinished is not read again: see
# test_inbox_hardening.py. Reading it again would let a file that ends the
# process end it at every start.


# --- Z3.11 -------------------------------------------------------------------


def test_inbox_duplicate_under_the_same_name_another_name_or_another_customer_is_not_read(
    desk: Desk, invoice: bytes
) -> None:
    put(desk, "Meier/policy.pdf", invoice)
    desk.inbox.choose_folder(str(desk.folder))
    desk.settle()
    first = desk.entries()["Meier/policy.pdf"]

    put(desk, "Meier/copy/policy.pdf", invoice)
    put(desk, "Meier/renamed.pdf", invoice)
    put(desk, "Schulze/policy.pdf", invoice)
    desk.settle()
    entries = desk.entries()

    for path in ("Meier/copy/policy.pdf", "Meier/renamed.pdf", "Schulze/policy.pdf"):
        duplicate = entries[path]
        assert (duplicate.state, duplicate.duplicate_of) == ("duplicate", first.id)
        assert duplicate.folder == str((desk.folder / path).parent)
        assert duplicate.sha256 == first.sha256
        assert duplicate.values == []
    assert entries["Schulze/policy.pdf"].customer == "Schulze"
    assert entries["Meier/policy.pdf"].state == "waiting"
    assert desk.parsed == {"policy.pdf": 1}

    desk.inbox.stop()
    desk.restart()
    desk.settle()
    assert len(desk.inbox.entries()) == 4
    assert desk.parsed == {"policy.pdf": 1}


def test_inbox_duplicate_within_one_import_points_to_the_file_read_first(
    desk: Desk, invoice: bytes
) -> None:
    put(desk, "Meier/a.pdf", invoice)
    put(desk, "Schulze/b.pdf", invoice)

    desk.inbox.choose_folder(str(desk.folder))
    desk.settle()
    entries = desk.entries()

    assert entries["Meier/a.pdf"].state == "waiting"
    assert entries["Schulze/b.pdf"].duplicate_of == entries["Meier/a.pdf"].id
    assert sum(desk.parsed.values()) == 1


# --- Z7.4 --------------------------------------------------------------------


def test_profile_on_entry_stays_when_the_active_profile_changes(
    desk: Desk, invoice: bytes
) -> None:
    put(desk, "Meier/first.pdf", variant(invoice, 1))
    desk.inbox.choose_folder(str(desk.folder))
    desk.settle()
    before = desk.entries()["Meier/first.pdf"]

    desk.inbox.choose_profile("flat")
    put(desk, "Meier/second.pdf", variant(invoice, 2))
    desk.settle()
    desk.inbox.stop()
    entries = desk.restart().entries()

    assert entries[0] == before
    assert (before.profile, before.customer) == ("scans", "Meier")
    assert (entries[1].profile, entries[1].customer) == ("flat", None)
    assert desk.inbox.settings().profile == "flat"


def test_profile_on_entry_needs_a_choice_when_several_profiles_exist(
    tmp_path: Path, desk: Desk
) -> None:
    undecided = Inbox(tmp_path / "other" / "substrakt.db", desk.store, [desk.root])

    with pytest.raises(PipelineProfileUnknown):
        undecided.choose_folder(str(desk.folder))
    with pytest.raises(PipelineProfileUnknown):
        undecided.choose_profile("absent")

    settings = undecided.settings()
    assert (settings.folder, settings.profile, settings.watching) == (None, None, False)
    assert {"scans", "flat"} <= {choice.name for choice in settings.profiles}


# --- Loop --------------------------------------------------------------------


def test_inbox_loop_reads_without_any_call_and_survives_a_failing_poll(
    desk: Desk, invoice: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    looks = threading.Semaphore(0)
    poll = desk.inbox.poll

    def counted_poll() -> None:
        try:
            if not desk.parsed and desk.inbox.entries() == [] and not failed:
                failed.append(True)
                raise RuntimeError("one bad poll")
            poll()
        finally:
            looks.release()

    failed: list[bool] = []
    monkeypatch.setattr(desk.inbox, "poll", counted_poll)
    monkeypatch.setattr(desk.inbox, "_interval", 0.01)
    put(desk, "Meier/scan.pdf", invoice)
    desk.inbox.choose_folder(str(desk.folder))

    desk.inbox.start()
    assert desk.inbox.settings().watching
    for _ in range(4):
        assert looks.acquire(timeout=10)
    desk.inbox.stop()

    assert failed == [True]
    assert [entry.state for entry in desk.restart().entries()] == ["waiting"]


# --- Shipped profile ---------------------------------------------------------


def shipped_desk(desk: Desk) -> str:
    """Activate the one profile that ships with the application."""
    pipeline_profiles.configure(None)
    [shipped] = pipeline_profiles.titles()
    desk.inbox.choose_profile(shipped)
    desk.inbox.choose_folder(str(desk.folder))
    return shipped


def expected(corpus: Path, file: str) -> dict:
    truth = json.loads((corpus / "insurance" / "truth.json").read_text(encoding="utf-8"))
    return next(item for item in truth if item["file"] == file)


@pytest.mark.parametrize(
    "file", ["policy_b_1.pdf", "contract_change_b_1.pdf", "premium_invoice_c_1.pdf"]
)
def test_inbox_with_the_shipped_profile_recognises_the_kind_and_reads_its_values(
    desk: Desk, corpus: Path, file: str
) -> None:
    shipped = shipped_desk(desk)
    truth = expected(corpus, file)
    put(desk, f"Okafor/{file}", (corpus / "insurance" / file).read_bytes())

    desk.settle()

    [entry] = desk.inbox.entries()
    assert (entry.state, entry.profile, entry.kind) == ("waiting", shipped, truth["kind"])
    assert entry.customer == "Okafor"
    read = {value.field: value.normalized for value in entry.values if value.grounded}
    required = set(pipeline_profiles.load(shipped).kinds[truth["kind"]].values)
    # Not every required value is read unambiguously; those wait for a person.
    assert {"policy_number", "line_of_business"} <= set(read) & required
    assert {name: read[name] for name in required & set(read)} == {
        name: truth["values"][name] for name in required & set(read)
    }


def test_inbox_with_the_shipped_profile_gives_no_kind_to_a_document_of_none_or_two(
    desk: Desk, corpus: Path
) -> None:
    shipped_desk(desk)
    for file in ("neither_claim_report.pdf", "both_policy_and_invoice.pdf"):
        put(desk, f"Okafor/{file}", (corpus / "insurance" / file).read_bytes())

    desk.settle()

    assert [(entry.state, entry.kind, entry.values) for entry in desk.inbox.entries()] == [
        ("waiting", None, []),
        ("waiting", None, []),
    ]


@pytest.mark.skipif(not ocr.available(), reason="Tesseract or deu.traineddata is unavailable")
def test_inbox_with_the_shipped_profile_recognises_the_kind_of_a_scan(
    desk: Desk, corpus: Path
) -> None:
    shipped_desk(desk)
    file = "policy_a_1_scan300.png"
    truth = expected(corpus, file)
    put(desk, f"Okafor/{file}", (corpus / "insurance" / file).read_bytes())

    desk.settle()

    [entry] = desk.inbox.entries()
    assert (entry.state, entry.kind, entry.page_count) == ("waiting", "policy", 1)
    number = next(value for value in entry.values if value.field == "policy_number")
    assert (number.normalized, number.grounded) == (truth["values"]["policy_number"], True)
    assert number.locator is not None


# --- The output folder Ausgabe ---------------------------


def test_ausgabe_is_created_when_the_folder_is_chosen_and_named_in_the_settings(desk: Desk) -> None:
    desk.inbox.choose_folder(str(desk.folder))

    assert (desk.folder / "Ausgabe").is_dir()
    assert desk.inbox.settings().handover_folder == str(desk.folder / "Ausgabe")


def test_ausgabe_not_read_creates_no_entry_or_customer_also_after_a_restart(
    desk: Desk, invoice: bytes
) -> None:
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Ausgabe/scan.pdf", invoice)
    put(desk, "Ausgabe/Meier/scan.png", variant(invoice, 1))
    put(desk, f"Ausgabe/{'0' * 32}.json", b"{}")
    put(desk, "Ausgabe/Okafor_20261119-120000.gdv", b"0001")

    desk.settle()
    desk.restart()
    desk.settle()
    assert desk.inbox.entries() == []

    # The counter-check: the same PDF in a customer folder is read.
    put(desk, "Meier/scan.pdf", invoice)
    desk.settle()
    assert [(e.customer, e.file_name) for e in desk.inbox.entries()] == [("Meier", "scan.pdf")]


def test_ausgabe_file_of_that_name_is_refused_and_keeps_its_bytes(desk: Desk) -> None:
    foreign = desk.folder / "Ausgabe"
    foreign.write_bytes(b"not a folder")
    before = file_hash(foreign)

    with pytest.raises(OutputNameTaken) as refused:
        desk.inbox.choose_folder(str(desk.folder))

    assert refused.value.key == "output-name-taken"
    assert (foreign.is_file(), file_hash(foreign)) == (True, before)
    assert desk.inbox.settings().folder is None
