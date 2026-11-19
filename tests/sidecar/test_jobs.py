"""Corrections, approval and the job queue: nothing leaves without an approval by a person."""

from __future__ import annotations

import getpass
import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pytest
from conftest import PROFILE, Desk, Queue, put, variant
from test_privacy import shipped_queue

from substrakt import jobs as jobs_module
from substrakt import pipeline_profiles
from substrakt.errors import (
    ApprovalRefused,
    CorrectionRefused,
    FileChanged,
    InboxEntryUnknown,
    JobTransitionInvalid,
    JobUnknown,
)
from substrakt.inbox import Correction, InboxEntry
from substrakt.jobs import TRANSITIONS, JobFile, Jobs
from substrakt.store import file_hash

ROOT = Path(__file__).resolve().parents[2]
DICTIONARIES = [ROOT / "src" / "i18n" / "de.ts", ROOT / "src" / "i18n" / "en.ts"]

def refusal(queue: Queue, entry_id: int) -> ApprovalRefused:
    with pytest.raises(ApprovalRefused) as raised:
        queue.jobs.approve(entry_id)
    return raised.value


# --- Corrections (data part of Z4.1) -------------------------------------------


def test_correction_of_a_value_is_stored_with_the_entry_and_keeps_what_stood_there(
    queue: Queue,
) -> None:
    corrected = queue.desk.inbox.correct(
        queue.entry.id, Correction(values={"document_number": " 2026-0148 ", "sender": "Muster AG"})
    )

    values = {value.field: value for value in corrected.values}
    assert (values["document_number"].value, values["document_number"].source) == (
        "2026-0148", "manual",
    )
    assert values["sender"].grounded
    assert values["total_amount"] == next(
        value for value in queue.entry.values if value.field == "total_amount"
    )
    queue.desk.inbox.stop()
    assert queue.desk.restart().entry(queue.entry.id) == corrected
    history = queue.desk.inbox.db.query(
        "SELECT value_name, before, after FROM inbox_correction ORDER BY id"
    )
    assert [tuple(row) for row in history] == [
        ("document_number", "2026-0147", "2026-0148"),
        ("sender", None, "Muster AG"),
    ]


def test_correction_of_the_kind_reads_the_file_again_with_that_kind(
    desk: Desk, invoice: bytes, unrecognised: None
) -> None:
    queue = Queue(desk, invoice, profile="two_kinds")
    assert (queue.entry.kind, queue.entry.values) == (None, [])

    corrected = desk.inbox.correct(queue.entry.id, Correction(kind="credit_note"))

    assert corrected.kind == "credit_note"
    number = next(value for value in corrected.values if value.field == "document_number")
    assert (number.value, number.grounded) == ("2026-0147", True)
    assert number.locator is not None
    history = desk.inbox.db.query("SELECT value_name, before, after FROM inbox_correction")
    assert [tuple(row) for row in history] == [(None, None, "credit_note")]
    assert desk.parsed == {"policy.pdf": 2}


def test_entry_lists_values_a_person_changed_since_the_kind_was_last_set(
    desk: Desk, invoice: bytes, unrecognised: None
) -> None:
    queue = Queue(desk, invoice, profile="two_kinds")
    inbox = desk.inbox
    inbox.correct(queue.entry.id, Correction(kind="credit_note"))
    number = next(v.value for v in inbox.entry(queue.entry.id).values if v.field == "document_number")

    confirmed = inbox.correct(queue.entry.id, Correction(values={"document_number": number}))
    assert confirmed.changed == []
    changed = inbox.correct(queue.entry.id, Correction(values={"document_number": "2026-0148"}))
    assert changed.changed == ["document_number"]
    assert [entry.changed for entry in inbox.entries()] == [["document_number"]]

    again = inbox.correct(queue.entry.id, Correction(kind="invoice"))
    assert again.changed == []


def test_confirmed_value_keeps_its_location_and_is_not_changed_by_the_clerk(queue: Queue) -> None:
    inbox = queue.desk.inbox
    read = {value.field: value for value in queue.entry.values}["document_number"]
    assert read.locator is not None
    # The reading was not certain: same text and location, not settled.
    unclear = [
        v.model_copy(update={"grounded": False}) if v.field == read.field else v
        for v in queue.entry.values
    ]
    inbox.db.write(
        "UPDATE inbox_entry SET values_json = ? WHERE id = ?",
        json.dumps([v.model_dump() for v in unclear]),
        queue.entry.id,
    )

    confirmed = inbox.correct(queue.entry.id, Correction(confirmed=["document_number"]))

    value = {v.field: v for v in confirmed.values}["document_number"]
    assert value == read.model_copy(update={"grounded": True})
    assert value.locator == read.locator and value.source != "manual"
    assert confirmed.changed == []
    history = inbox.db.query("SELECT value_name, before, after, account FROM inbox_correction")
    assert [tuple(row)[:3] for row in history] == [("document_number", read.value, read.value)]
    assert history[0]["account"]


@pytest.mark.parametrize("confirmed", [["no_such_value"], ["sender"]], ids=["unknown", "not-read"])
def test_confirmation_of_a_value_that_was_not_read_is_refused(
    queue: Queue, confirmed: list[str]
) -> None:
    with pytest.raises(CorrectionRefused):
        queue.desk.inbox.correct(queue.entry.id, Correction(confirmed=confirmed))
    assert queue.desk.inbox.entry(queue.entry.id) == queue.entry


@pytest.mark.parametrize(
    ("correction", "reason"),
    [
        (Correction(kind="no_such_kind"), "kind-not-in-profile"),
        (Correction(kind="credit_note"), "kind-not-in-profile"),
        (Correction(values={"no_such_value": "1"}), "value-unknown"),
        (Correction(values={"document_number": "  "}), "value-empty"),
    ],
)
def test_correction_that_names_a_foreign_kind_or_value_is_refused_and_changes_nothing(
    queue: Queue, correction: Correction, reason: str
) -> None:
    with pytest.raises(CorrectionRefused) as raised:
        queue.desk.inbox.correct(queue.entry.id, correction)

    assert raised.value.fields["reason"] == reason
    assert queue.desk.inbox.entry(queue.entry.id) == queue.entry
    assert queue.desk.inbox.db.query("SELECT * FROM inbox_correction") == []


def test_correction_is_refused_for_an_approved_or_missing_entry_and_a_changed_file(
    desk: Desk, invoice: bytes, unrecognised: None
) -> None:
    queue = Queue(desk, invoice, profile="two_kinds")
    with pytest.raises(InboxEntryUnknown):
        desk.inbox.correct(999, Correction())
    Path(queue.entry.file_path).write_bytes(variant(invoice, 9))
    with pytest.raises(FileChanged):
        desk.inbox.correct(queue.entry.id, Correction(kind="invoice"))

    other = queue.arrive("Meier/other.pdf", 2)
    desk.inbox.correct(other.id, Correction(kind="invoice"))
    queue.jobs.approve(other.id)
    with pytest.raises(CorrectionRefused) as raised:
        desk.inbox.correct(other.id, Correction(values={"document_number": "1"}))
    assert raised.value.fields["reason"] == "entry-not-waiting"


# --- Values entered by hand -----------------------


def reported_case(desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Jobs, InboxEntry]:
    """policy_b_1.pdf under the shipped profile: insurer read unclear, policyholder not read."""
    jobs, _, _ = shipped_queue(desk, monkeypatch)
    put(desk, "Brandt/policy_b_1.pdf", (corpus / "insurance" / "policy_b_1.pdf").read_bytes())
    desk.settle()
    entry = desk.entries()["Brandt/policy_b_1.pdf"]
    read = {value.field: value for value in entry.values}
    assert read["insurer"].value and not read["insurer"].grounded
    assert "policyholder" not in read or not read["policyholder"].value
    return jobs, entry


def test_values_entered_by_hand_settle_an_unread_and_an_unclear_required_value(
    desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs, entry = reported_case(desk, corpus, monkeypatch)
    with pytest.raises(ApprovalRefused) as raised:
        jobs.approve(entry.id)
    assert raised.value.fields["open"] == ["policyholder"]
    assert raised.value.fields["unclear"] == ["insurer"]

    desk.inbox.correct(
        entry.id, Correction(values={"policyholder": "Jonas Brandt", "insurer": "Nordlicht Versicherung"})
    )
    job = jobs.approve(entry.id)

    assert [j.id for j in jobs.all()] == [job.id]
    rows = desk.inbox.db.query(
        "SELECT value_name, after, account, corrected_at FROM inbox_correction ORDER BY value_name"
    )
    assert [(row["value_name"], row["after"]) for row in rows] == [
        ("insurer", "Nordlicht Versicherung"), ("policyholder", "Jonas Brandt"),
    ]
    assert {row["account"] for row in rows} == {getpass.getuser()}
    for row in rows:
        assert datetime.fromisoformat(row["corrected_at"]).tzinfo is not None


def test_value_entered_by_hand_type_that_does_not_fit_stays_unclear_and_is_not_named(
    desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs, entry = reported_case(desk, corpus, monkeypatch)
    desk.inbox.correct(
        entry.id,
        Correction(values={"policyholder": "Jonas Brandt", "insurer": "Nordlicht", "start_date": "31.02.2025"}),
    )

    with pytest.raises(ApprovalRefused) as raised:
        jobs.approve(entry.id)

    assert raised.value.fields["reason"] == "values-not-settled"
    assert raised.value.fields["unclear"] == ["start_date"]
    assert "31.02.2025" not in json.dumps(raised.value.as_problem())
    assert jobs.all() == []


# --- Z4.2 ------------------------------------------------------------------------


def test_approval_is_refused_while_a_required_value_is_open_or_not_unambiguous(
    desk: Desk, invoice: bytes, writer: list[JobFile]
) -> None:
    queue = Queue(desk, invoice, profile="strict")

    open_value = refusal(queue, queue.entry.id)
    assert open_value.fields == {"reason": "values-not-settled", "open": ["sender"], "unclear": []}

    desk.inbox.correct(
        queue.entry.id, Correction(values={"sender": "Muster AG", "document_date": "irgendwann"})
    )
    unclear = refusal(queue, queue.entry.id)
    assert (unclear.fields["open"], unclear.fields["unclear"]) == ([], ["document_date"])
    assert "irgendwann" not in str(unclear.as_problem())

    assert queue.jobs.all() == []
    assert queue.files() == []
    assert desk.inbox.entry(queue.entry.id).state == "waiting"

    desk.inbox.correct(queue.entry.id, Correction(values={"document_date": "26.07.2026"}))
    job = queue.jobs.approve(queue.entry.id)
    assert job.file.values["Datum"].normalized == "2026-07-26"
    assert queue.files() == [f"{job.id}.json"]


def test_approval_takes_an_optional_value_along_when_it_was_read_and_never_waits_for_it(
    desk: Desk, invoice: bytes, writer: list[JobFile]
) -> None:
    # sender is not on the sample invoice, iban is, and the date is made unclear.
    optional = "    optional:\n      sender: Absender\n      iban: IBAN\n      document_date: Datum\n"
    (desk.root / "profiles" / "scans.yml").write_text(
        PROFILE.format(name="scans", level=1) + optional, encoding="utf-8"
    )
    queue = Queue(desk, invoice)
    desk.inbox.correct(queue.entry.id, Correction(values={"document_date": "irgendwann"}))

    job = queue.jobs.approve(queue.entry.id)

    assert set(job.file.values) == {"Nummer", "IBAN"}
    assert job.file.values["IBAN"].normalized == "DE89370400440532013000"


def test_approval_is_refused_for_an_entry_without_a_kind_a_duplicate_and_an_error(
    desk: Desk, invoice: bytes, writer: list[JobFile], unrecognised: None
) -> None:
    queue = Queue(desk, invoice, profile="two_kinds")
    put(desk, "Meier/copy.pdf", variant(invoice, 1))
    put(desk, "Meier/broken.pdf", b"%PDF-1.4\nnot a document\n")
    desk.settle()
    entries = desk.entries()

    assert refusal(queue, queue.entry.id).fields["reason"] == "kind-missing"
    for closed in ("Meier/copy.pdf", "Meier/broken.pdf"):
        assert refusal(queue, entries[closed].id).fields["reason"] == "entry-not-waiting"  # type: ignore[attr-defined]
    with pytest.raises(InboxEntryUnknown):
        queue.jobs.approve(999)
    assert queue.jobs.all() == []
    assert queue.files() == []


def test_approval_alone_puts_a_file_into_the_hand_over_folder(
    queue: Queue, writer: list[JobFile]
) -> None:
    queue.arrive("Schulze/policy.pdf", 2)
    queue.desk.inbox.correct(queue.entry.id, Correction(values={"document_number": "7"}))
    queue.jobs.hand_over_pending()
    assert queue.files() == [], "reading, correcting and running the queue hand nothing over"

    job = queue.jobs.approve(queue.entry.id)

    assert queue.files() == [f"{job.id}.json"]
    assert [file.id for file in writer] == [job.id]
    assert queue.desk.inbox.entry(queue.entry.id).state == "approved"
    assert queue.desk.entries()["Schulze/policy.pdf"].state == "waiting"  # type: ignore[attr-defined]


def test_approval_errors_have_texts_in_both_languages() -> None:
    keys = [
        error.key
        for error in (
            ApprovalRefused, CorrectionRefused, InboxEntryUnknown, JobUnknown, JobTransitionInvalid,
        )
    ]
    for dictionary in DICTIONARIES:
        text = dictionary.read_text(encoding="utf-8")
        assert [key for key in keys if f"'{key}'" not in text] == []


# --- Z4.3 ------------------------------------------------------------------------


def test_job_duplicate_is_not_created_by_approving_the_same_entry_twice(
    queue: Queue, writer: list[JobFile]
) -> None:
    first = queue.jobs.approve(queue.entry.id)
    second = queue.jobs.approve(queue.entry.id)

    assert second == first
    assert len(first.id) == 32
    assert [job.id for job in queue.jobs.all()] == [first.id]
    assert queue.files() == [f"{first.id}.json"]
    assert len(writer) == 1


def test_job_duplicate_is_not_created_by_the_same_content_under_another_entry(
    queue: Queue, writer: list[JobFile]
) -> None:
    put(queue.desk, "Schulze/copy.pdf", variant(queue.invoice, 1))
    queue.desk.settle()
    copy = queue.desk.entries()["Schulze/copy.pdf"]
    first = queue.jobs.approve(queue.entry.id)
    # As if the copy had been read before the first entry was known.
    with queue.desk.inbox.db.transaction() as conn:
        conn.execute(
            "UPDATE inbox_entry SET state = 'waiting', duplicate_of = NULL, kind = 'invoice', "
            "page_count = 1, values_json = (SELECT values_json FROM inbox_entry WHERE id = ?) "
            "WHERE id = ?",
            (queue.entry.id, copy.id),  # type: ignore[attr-defined]
        )

    again = queue.jobs.approve(copy.id)  # type: ignore[attr-defined]

    assert again == first
    assert len(queue.jobs.all()) == 1
    assert queue.files() == [f"{first.id}.json"]
    marked = queue.desk.inbox.entry(copy.id)  # type: ignore[attr-defined]
    assert (marked.state, marked.duplicate_of) == ("duplicate", queue.entry.id)


def test_job_duplicate_key_comes_from_file_hash_kind_and_values_and_is_unique(
    queue: Queue, writer: list[JobFile]
) -> None:
    job = queue.jobs.approve(queue.entry.id)
    values = job.file.values
    key = jobs_module.idempotency_key

    assert job.file.idempotency_key == key(queue.entry.sha256, "invoice", values)
    assert key(queue.entry.sha256, "invoice", dict(reversed(values.items()))) == key(
        queue.entry.sha256, "invoice", values
    )
    changed = {"Nummer": values["Nummer"].model_copy(update={"text": "2026-0148"})}
    others = {
        key("0" * 64, "invoice", values),
        key(queue.entry.sha256, "credit_note", values),
        key(queue.entry.sha256, "invoice", changed),
    }
    assert len(others) == 3 and job.file.idempotency_key not in others

    other = queue.arrive("Meier/other.pdf", 2)
    with pytest.raises(sqlite3.IntegrityError), queue.desk.inbox.db.transaction() as conn:
        conn.execute(
            "INSERT INTO job (id, entry_id, idempotency_key, state, file_json) "
            "VALUES ('x', ?, ?, 'pending', '{}')",
            (other.id, job.file.idempotency_key),
        )


def test_job_duplicate_from_two_threads_is_prevented_by_the_key_and_not_by_timing(
    queue: Queue, writer: list[JobFile], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both threads have passed every check and built their job before either stores it.
    both_built = threading.Barrier(2, timeout=10)
    build = jobs_module.job_file

    def build_then_wait(entry, profile) -> JobFile:
        file = build(entry, profile)
        both_built.wait()
        return file

    monkeypatch.setattr(jobs_module, "job_file", build_then_wait)
    results: list[object] = []

    def approve() -> None:
        try:
            results.append(queue.jobs.approve(queue.entry.id).id)
        except Exception as error:
            results.append(error)

    threads = [threading.Thread(target=approve) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    [job] = queue.jobs.all()
    assert results == [job.id, job.id]
    assert queue.files() == [f"{job.id}.json"]
    assert len(writer) == 1


# --- Z4.4 and Z7.5 ---------------------------------------------------------------


def test_job_file_is_valid_against_the_documented_schema_and_names_profile_and_target(
    queue: Queue, writer: list[JobFile]
) -> None:
    job = queue.jobs.approve(queue.entry.id)

    written = json.loads((queue.handover / f"{job.id}.json").read_text(encoding="utf-8"))
    assert JobFile.model_validate(written) == job.file
    assert set(written) == set(json.loads(jobs_module.schema_text())["required"]) | {"version"}
    assert written == {
        "version": 1,
        "id": job.id,
        "idempotency_key": job.file.idempotency_key,
        "approved_at": job.transitions[0].at,
        "profile": "scans",
        "target": "test_target",
        "kind": "invoice",
        "customer": "Meier",
        "file": {"path": queue.entry.file_path, "sha256": queue.entry.sha256},
        "pages": {"first": 1, "last": 1},
        "values": {"Nummer": {"text": "2026-0147", "normalized": "2026-0147"}},
    }
    assert job.handover_path == str(queue.handover / f"{job.id}.json")
    with pytest.raises(ValueError):
        JobFile.model_validate({**written, "document_text": "Rechnung"})
    with pytest.raises(ValueError):
        JobFile.model_validate({**written, "version": 2})


def test_job_file_page_range_covers_every_page_of_the_scanned_file(
    queue: Queue, writer: list[JobFile], corpus: Path
) -> None:
    put(queue.desk, "Meier/long.pdf", (corpus / "rechnung_mehrseitig.pdf").read_bytes())
    queue.desk.settle()

    job = queue.jobs.approve(queue.desk.entries()["Meier/long.pdf"].id)  # type: ignore[attr-defined]

    assert (job.file.pages.first, job.file.pages.last) == (1, 3)


def test_job_file_appears_under_its_name_only_with_its_whole_content(
    queue: Queue, writer: list[JobFile], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[list[str], dict]] = []
    replace = os.replace

    def watching(source, target) -> None:
        seen.append((queue.files(), json.loads(Path(source).read_text(encoding="utf-8"))))
        replace(source, target)

    monkeypatch.setattr(jobs_module.os, "replace", watching)

    job = queue.jobs.approve(queue.entry.id)

    [(before_rename, content)] = seen
    assert before_rename == [f".{job.id}.json.tmp"], "no *.json exists before the rename"
    assert JobFile.model_validate(content) == job.file
    assert queue.files() == [f"{job.id}.json"]


def test_job_file_that_cannot_be_written_leaves_nothing_behind_and_the_job_failed(
    queue: Queue, writer: list[JobFile], monkeypatch: pytest.MonkeyPatch
) -> None:
    def full_disk(_descriptor: int) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(jobs_module.os, "fsync", full_disk)

    job = queue.jobs.approve(queue.entry.id)

    assert queue.files() == []
    assert (job.state, job.handover_path) == ("failed", None)
    assert job.transitions[-1].reason == "handover-write-failed"
    assert writer == []


def test_job_file_schema_file_matches_the_model_and_the_documentation(tmp_path: Path) -> None:
    assert jobs_module.schema_is_current(), (
        "job.schema.json is stale: "
        'uv run python -c "from substrakt import jobs; jobs.write_schema()"'
    )
    schema = json.loads(jobs_module.schema_text())
    assert schema["additionalProperties"] is False
    documentation = (ROOT / "docs" / "job-format.md").read_text(encoding="utf-8")
    assert [key for key in schema["properties"] if f"`{key}`" not in documentation] == []
    assert f"version {schema['properties']['version']['const']}" in documentation.lower()

    stale = tmp_path / "job.schema.json"
    stale.write_text(jobs_module.schema_text().replace('"target"', '"stale"', 1))
    assert not jobs_module.schema_is_current(stale)


def test_unknown_target_ends_as_a_failed_job_with_a_reason_and_writes_no_file(
    queue: Queue,
) -> None:
    assert "test_target" not in jobs_module.WRITERS

    job = queue.jobs.approve(queue.entry.id)

    assert job.state == "failed"
    assert [(t.from_state, t.to_state, t.reason) for t in job.transitions] == [
        (None, "pending", "approved"),
        ("pending", "failed", "target-without-writer"),
    ]
    assert queue.files() == []


def test_unknown_target_is_also_the_target_of_every_shipped_profile_until_its_writer_exists() -> (
    None
):
    shipped = {
        pipeline_profiles._read(file, (0, 0)).target
        for file in pipeline_profiles.BUILTIN.glob("*.yml")
    }

    assert shipped and not shipped & set(jobs_module.WRITERS)


# --- Z4.5 ------------------------------------------------------------------------


def test_job_states_follow_only_the_named_transitions_and_each_is_stored(
    queue: Queue, writer: list[JobFile]
) -> None:
    job = queue.jobs.approve(queue.entry.id)
    assert job.state == "handed_over"

    for forbidden in ("pending", "handed_over"):
        with pytest.raises(JobTransitionInvalid) as raised:
            queue.jobs.move(job.id, forbidden, "test")  # type: ignore[arg-type]
        assert raised.value.fields == {"from_state": "handed_over", "to_state": forbidden}
    with pytest.raises(JobTransitionInvalid):
        queue.jobs.release(job.id)
    with pytest.raises(JobUnknown):
        queue.jobs.move("absent", "done", "test")
    assert queue.jobs.get(job.id) == job, "a rejected transition stores nothing"

    done = queue.jobs.move(job.id, "done", "imported")
    for forbidden in TRANSITIONS:
        with pytest.raises(JobTransitionInvalid):
            queue.jobs.move(job.id, forbidden, "test")

    assert [(t.from_state, t.to_state, t.reason) for t in done.transitions] == [
        (None, "pending", "approved"),
        ("pending", "handed_over", "job-file-written"),
        ("handed_over", "done", "imported"),
    ]
    assert all(t.at.startswith("20") and "T" in t.at for t in done.transitions)


def test_job_states_table_names_exactly_four_states_and_the_database_accepts_no_other(
    queue: Queue, writer: list[JobFile]
) -> None:
    job = queue.jobs.approve(queue.entry.id)

    assert set(TRANSITIONS) == {"pending", "handed_over", "done", "failed"}
    assert TRANSITIONS["failed"] == {"pending"} and TRANSITIONS["done"] == set()
    with pytest.raises(sqlite3.IntegrityError), queue.desk.inbox.db.transaction() as conn:
        conn.execute("UPDATE job SET state = 'archived' WHERE id = ?", (job.id,))


def test_job_states_keep_a_failed_job_failed_until_a_person_releases_it(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = queue.jobs.approve(queue.entry.id)
    assert failed.state == "failed"

    queue.jobs.hand_over_pending()
    queue.desk.inbox.stop()
    queue.desk.restart()
    queue.jobs = Jobs(queue.desk.inbox)
    queue.jobs.hand_over_pending()
    assert queue.jobs.get(failed.id) == failed, "neither the queue nor a restart retries it"

    monkeypatch.setitem(jobs_module.WRITERS, "test_target", lambda *_: None)
    released = queue.jobs.release(failed.id)

    assert released.state == "handed_over"
    assert [(t.to_state, t.reason) for t in released.transitions[2:]] == [
        ("pending", "released"),
        ("handed_over", "job-file-written"),
    ]
    assert queue.files() == [f"{failed.id}.json"]


def test_ausgabe_missing_leaves_a_job_pending_until_the_folder_is_chosen_again(
    queue: Queue, writer: list[JobFile]
) -> None:
    queue.handover.rmdir()

    job = queue.jobs.approve(queue.entry.id)
    assert (job.state, queue.handover.exists()) == ("pending", False)

    queue.desk.inbox.choose_folder(str(queue.desk.folder))
    queue.jobs.hand_over_pending()
    assert queue.jobs.get(job.id).state == "handed_over"
    assert queue.files() == [f"{job.id}.json"]


def test_ausgabe_receives_the_job_file_and_the_settings_name_it(
    queue: Queue, writer: list[JobFile]
) -> None:
    job = queue.jobs.approve(queue.entry.id)

    assert job.handover_path == str(queue.desk.folder / "Ausgabe" / f"{job.id}.json")
    assert queue.desk.inbox.settings().handover_folder == str(queue.desk.folder / "Ausgabe")
    assert not hasattr(queue.desk.inbox, "choose_handover_folder")


def _sha(folder: Path) -> dict[str, str]:
    return {file.name: file_hash(file) for file in sorted(folder.iterdir())}


def test_ausgabe_exists_keeps_foreign_files_through_choice_hand_over_and_second_choice(
    desk: Desk, invoice: bytes, writer: list[JobFile]
) -> None:
    output = desk.folder / "Ausgabe"
    output.mkdir()
    (output / "Notiz.txt").write_text("vom Makler", encoding="utf-8")
    (output / "alt.gdv").write_bytes(b"\x00\x01 foreign")
    before = _sha(output)

    queue = Queue(desk, invoice)
    job = queue.jobs.approve(queue.entry.id)
    desk.inbox.choose_folder(str(desk.folder))

    after = _sha(output)
    assert {name: after[name] for name in before} == before
    assert set(after) == {*before, f"{job.id}.json"}


def test_foreign_name_of_a_job_file_keeps_its_bytes_and_the_job_fails(
    queue: Queue, writer: list[JobFile], monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed = "f" * 32
    monkeypatch.setattr(jobs_module.uuid, "uuid4", lambda: type("U", (), {"hex": fixed})())
    for name in (f"{fixed}.json", f".{fixed}.json.tmp"):
        foreign = queue.handover / name
        foreign.write_bytes(b"foreign bytes")
        before = file_hash(foreign)

        job = queue.jobs.approve(queue.entry.id)

        assert file_hash(foreign) == before
        assert (job.state, job.handover_path) == ("failed", None)
        assert job.transitions[-1].reason == jobs_module.REASON_NAME_TAKEN
        assert writer == []
        foreign.unlink()
        with queue.desk.inbox.db.transaction() as conn:
            conn.execute("DELETE FROM job")
            conn.execute("UPDATE inbox_entry SET state = 'waiting'")


def test_old_handover_setting_is_ignored_and_its_job_file_still_goes_with_the_entry(
    queue: Queue, writer: list[JobFile]
) -> None:
    old = queue.desk.root / "handover"
    old.mkdir()
    with queue.desk.inbox.db.transaction() as conn:
        conn.execute(
            "INSERT INTO app_setting (key, value) VALUES ('handover_folder', ?)", (str(old),)
        )
    first = queue.jobs.approve(queue.entry.id)
    # Written before this contract: the job file lies in the old folder.
    moved = old / Path(first.handover_path or "").name
    Path(first.handover_path or "").rename(moved)
    with queue.desk.inbox.db.transaction() as conn:
        conn.execute("UPDATE job SET handover_path = ? WHERE id = ?", (str(moved), first.id))

    second = queue.jobs.approve(queue.arrive("Meier/second.pdf", 2).id)

    assert Path(second.handover_path or "").parent == queue.desk.folder / "Ausgabe"
    assert queue.desk.inbox.settings().handover_folder == str(queue.desk.folder / "Ausgabe")
    queue.jobs.delete_entry(queue.entry.id)
    assert list(old.iterdir()) == []


# --- Z7.4, job part ----------------------------------------------------------------


def test_profile_on_entry_reaches_the_job_when_the_active_profile_has_changed(
    queue: Queue, writer: list[JobFile]
) -> None:
    queue.desk.inbox.choose_profile("strict")

    job = queue.jobs.approve(queue.entry.id)

    assert (job.file.profile, queue.entry.profile) == ("scans", "scans")
    assert set(job.file.values) == {"Nummer"}, "the values the entry's own profile expects"
    queue.desk.inbox.stop()
    queue.desk.restart()
    assert Jobs(queue.desk.inbox).get(job.id) == job


# --- Deleting (prepared for Z6.3) --------------------------------------------------


def test_job_tables_let_an_entry_be_deleted_with_everything_that_hangs_on_it(
    queue: Queue, writer: list[JobFile]
) -> None:
    queue.desk.inbox.correct(queue.entry.id, Correction(values={"document_number": "7"}))
    queue.jobs.approve(queue.entry.id)
    db = queue.desk.inbox.db

    db.write("DELETE FROM inbox_entry WHERE id = ?", queue.entry.id)

    for table in ("inbox_correction", "job", "job_transition"):
        assert db.query(f"SELECT * FROM {table}") == []
