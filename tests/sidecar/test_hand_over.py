"""Hand-over runs on the production path: folder, reading, approval, GDV file.

The profile is the shipped one with a block ``hand_over`` added in the test,
because its real settings are facts only the broker and the vendor have.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

import pytest
from conftest import Desk, put
from test_api import auth, client  # noqa: F401  (the fixture of the API tests)

from substrakt import gdv, hand_over, pipeline_profiles
from substrakt import jobs as jobs_module
from substrakt.errors import ApprovalRefused
from substrakt.gdv import reader, tables, writer
from substrakt.inbox import OUTPUT, Correction
from substrakt.jobs import REASON_NO_WRITER, Jobs

BLOCK = """
hand_over:
  format: gdv
  encoding: cp850
  record_separator: crlf
  broker_number: "4711"
  sender: Maklerbüro Beispiel
  addressee: Bestandsprogramm
  currency: EUR
  contract_kinds: [policy]
  collection_kinds: [premium_invoice]
"""


class Office:
    """A desk with the shipped profile, its output folder and the job queue of the application."""

    def __init__(self, desk: Desk, corpus: Path, block: str = BLOCK) -> None:
        self.desk, self.corpus = desk, corpus / "insurance"
        pipeline_profiles.configure(None)
        [self.profile] = pipeline_profiles.titles()
        shipped = Path(pipeline_profiles.__file__).parent / f"{self.profile}.yml"
        (desk.root / "profiles" / shipped.name).write_text(
            shipped.read_text(encoding="utf-8") + block, encoding="utf-8"
        )
        pipeline_profiles.configure(desk.root / "profiles")
        desk.inbox.choose_profile(self.profile)
        desk.inbox.choose_folder(str(desk.folder))
        self.handover = desk.folder / OUTPUT
        self.jobs = Jobs(desk.inbox, hand_over.check, hand_over.in_runs)
        self.truth = json.loads((self.corpus / "truth.json").read_text(encoding="utf-8"))

    def arrive(self, customer: str, file: str, **corrections: str):
        """Put a corpus file into the customer's folder and settle what review would settle."""
        put(self.desk, f"{customer}/{file}", (self.corpus / file).read_bytes())
        self.desk.settle()
        entry = self.desk.entries()[f"{customer}/{file}"]
        truth = next(item for item in self.truth if item["file"] == file)["values"]
        required = pipeline_profiles.load(self.profile).kinds[entry.kind].values
        settled = {v.field for v in entry.values if v.value and v.grounded}
        # A person confirms or types what was not read unambiguously.
        values = {name: str(truth[name]) for name in required if name not in settled and name in truth}
        self.desk.inbox.correct(entry.id, Correction(values={**values, **corrections}))
        return entry

    def run(self, customer: str):
        return hand_over.run(self.jobs, self.desk.inbox, customer)

    def gdv_files(self) -> list[Path]:
        return sorted(self.handover.glob("*.gdv"))


@pytest.fixture
def office(desk: Desk, corpus: Path) -> Office:
    return Office(desk, corpus)


def test_hand_over_run_writes_the_approved_jobs_of_one_customer_as_one_gdv_file(office: Office) -> None:
    policy = office.arrive("Okafor", "policy_b_1.pdf")
    invoice = office.arrive("Okafor", "premium_invoice_c_1.pdf")
    other = office.arrive("Brandt", "policy_b_2.pdf")
    approved = [office.jobs.approve(entry.id) for entry in (policy, invoice, other)]

    # Approving alone writes nothing: the jobs wait for a run a person starts.
    assert [job.state for job in approved] == ["pending"] * 3
    assert list(office.handover.iterdir()) == []

    done = office.run("Okafor")
    assert [(job.state, job.transitions[-1].reason) for job in done] == [
        ("handed_over", "job-file-written")
    ] * 2
    assert office.jobs.get(approved[2].id).state == "pending"
    [file] = office.gdv_files()
    assert file.name.startswith("Okafor_")
    assert {Path(job.handover_path).name for job in done} == {f"{job.id}.json" for job in done}

    # The independent reader finds exactly the approved values in the file.
    profile = hand_over._profile(done[0].file)
    names = {kind: spec["values"] for kind, spec in profile["kinds"].items()}
    plain = [hand_over._plain(job.id, job.file) for job in done]
    data = file.read_bytes()
    assert len(data) % 258 == 0
    assert reader.check(data, plain, names, profile["hand_over"], tables.load_all()) is None
    contracts = reader.parse(data, "cp850", b"\r\n")
    truth = next(i for i in office.truth if i["file"] == "policy_b_1.pdf")["values"]
    [contract] = [c for c in contracts.values() if c.get("printed") == truth["policy_number"]]
    assert contract["name"] == truth["policyholder"]
    assert contract["gross"] == round(truth["premium"] * 100)

    # A later run for the same customer writes a further file and replaces none.
    assert office.run("Okafor") == [] and office.gdv_files() == [file]


def test_hand_over_gdv_mapping_missing_refuses_the_approval_with_the_item_named(office: Office) -> None:
    entry = office.arrive("Okafor", "policy_b_1.pdf", insurer="Unbekannte Gesellschaft AG")
    with pytest.raises(ApprovalRefused) as refused:
        office.jobs.approve(entry.id)
    assert refused.value.fields == {"reason": "hand-over-not-possible", "items": ["insurer_number"]}
    assert "Unbekannte" not in json.dumps(refused.value.as_problem())
    # No job exists, and the entry still waits in review.
    assert office.jobs.all() == []
    assert office.desk.inbox.entry(entry.id).state == "waiting"

    office.desk.inbox.correct(entry.id, Correction(values={"line_of_business": "Reisegepäck"}))
    with pytest.raises(ApprovalRefused) as refused:
        office.jobs.approve(entry.id)
    assert refused.value.fields["items"] == ["insurer_number", "line_of_business_code"]


def test_ausgabe_receives_the_gdv_file_and_the_job_files_and_none_of_them_is_read(
    office: Office,
) -> None:
    job = office.jobs.approve(office.arrive("Okafor", "policy_b_1.pdf").id)

    [done] = office.run("Okafor")

    output = office.desk.folder / "Ausgabe"
    [file] = office.gdv_files()
    assert (file.parent, Path(done.handover_path or "").parent) == (output, output)
    assert sorted(p.name for p in output.iterdir()) == sorted([file.name, f"{job.id}.json"])
    before = len(office.desk.inbox.entries())
    office.desk.settle()
    office.desk.restart()
    office.desk.settle()
    assert len(office.desk.inbox.entries()) == before


def test_foreign_name_of_a_gdv_file_or_its_part_keeps_its_bytes_and_the_jobs_fail(
    office: Office, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime

    fixed = datetime(2026, 11, 19, 12, 0, 0)
    monkeypatch.setattr(gdv, "datetime", type("Fixed", (), {"now": staticmethod(lambda: fixed)}))
    job = office.jobs.approve(office.arrive("Okafor", "policy_b_1.pdf").id)
    for name, reason in (
        ("Okafor_20261119-120000.gdv.part", hand_over.REASON_NAME_TAKEN),
        ("Okafor_20261119-120000.gdv", hand_over.REASON_READ_BACK),
    ):
        foreign = office.handover / name
        foreign.write_bytes(b"foreign bytes")

        [done] = office.run("Okafor")

        assert foreign.read_bytes() == b"foreign bytes"
        assert (done.state, done.transitions[-1].reason.split(":")[0]) == ("failed", reason)
        assert sorted(p.name for p in office.handover.iterdir()) == [name]
        foreign.unlink()
        office.jobs.release(job.id)


def test_hand_over_gdv_mapping_does_not_let_a_contract_change_be_approved_for_a_file(office: Office) -> None:
    entry = office.arrive("Okafor", "contract_change_b_1.pdf")
    with pytest.raises(ApprovalRefused) as refused:
        office.jobs.approve(entry.id)
    assert refused.value.fields["items"] == ["kind_not_handed_over"]


def test_hand_over_gdv_roundtrip_mismatch_fails_the_jobs_and_leaves_no_file(
    office: Office, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = office.jobs.approve(office.arrive("Okafor", "policy_b_1.pdf").id)
    layout = dict(writer.LAYOUT)
    layout["0200", 1] = tuple(
        writer.Field(f.name, f.start - 1, f.length, f.kind, f.const) if f.name == "start_date" else f
        for f in layout["0200", 1]
    )
    monkeypatch.setattr(writer, "LAYOUT", layout)

    [failed] = office.run("Okafor")
    assert failed.state == "failed" and failed.handover_path is None
    assert failed.transitions[-1].reason.startswith("hand-over-read-back-failed: ")
    assert list(office.handover.iterdir()) == []

    # Nothing is written again by itself; a person releases the job for the next run.
    monkeypatch.undo()
    office.jobs.hand_over_pending()
    assert office.run("Okafor") == [] and list(office.handover.iterdir()) == []
    assert office.jobs.release(job.id).state == "pending"
    [again] = office.run("Okafor")
    assert again.state == "handed_over" and len(office.gdv_files()) == 1


def test_hand_over_run_fails_two_policies_of_one_number_with_the_reason(office: Office) -> None:
    first = office.arrive("Okafor", "policy_b_1.pdf")
    truth = next(i for i in office.truth if i["file"] == "policy_b_1.pdf")["values"]
    second = office.arrive(
        "Okafor", "policy_b_2.pdf",
        insurer=truth["insurer"], policy_number=truth["policy_number"],
        line_of_business=truth["line_of_business"],
    )
    for entry in (first, second):
        office.jobs.approve(entry.id)
    done = office.run("Okafor")
    assert [(job.state, job.transitions[-1].reason) for job in done] == [
        ("failed", "hand-over-held-back: one_contract_per_policy_number")
    ] * 2
    assert list(office.handover.iterdir()) == []


def test_hand_over_run_names_the_settings_an_incomplete_profile_lacks(desk: Desk, corpus: Path) -> None:
    office = Office(desk, corpus, block="\nhand_over:\n  format: gdv\n  encoding: cp850\n")
    job = office.jobs.approve(office.arrive("Okafor", "policy_b_1.pdf").id)
    assert job.state == "pending"
    [failed] = office.run("Okafor")
    reason = failed.transitions[-1].reason
    assert failed.state == "failed" and reason.startswith("hand-over-settings-invalid: ")
    assert "hand_over.broker_number" in reason and "hand_over.record_separator" in reason
    assert list(office.handover.iterdir()) == []


def test_hand_over_of_a_profile_without_the_block_still_ends_without_a_writer(desk: Desk, corpus: Path) -> None:
    office = Office(desk, corpus, block="")
    job = office.jobs.approve(office.arrive("Okafor", "policy_b_1.pdf").id)
    assert (job.state, job.transitions[-1].reason) == ("failed", REASON_NO_WRITER)
    assert office.run("Okafor") == []


def test_hand_over_run_endpoint_returns_the_jobs_of_the_customer(client) -> None:  # noqa: F811
    assert client.post("/jobs/hand-over", json={"customer": "Niemand"}, headers=auth()).json() == []
    assert client.post("/jobs/hand-over", json={"customer": "Niemand"}).status_code == 401


# --- Optional values ----------------------------------------------------------


def test_approval_of_a_policy_with_only_an_annual_premium_needs_no_typed_premium(
    office: Office,
) -> None:
    # The document prints the annual premium and a quarterly payment mode.
    quarterly = office.arrive("Okafor", "policy_a_1.pdf")
    with pytest.raises(ApprovalRefused) as refused:
        office.jobs.approve(quarterly.id)
    assert refused.value.fields == {
        "reason": "hand-over-not-possible",
        "items": ["premium_per_payment_period"],
    }

    # With an annual payment mode the annual premium is the premium of the period.
    yearly = office.arrive("Okafor", "policy_a_2.pdf", payment_mode="jährlich")
    job = office.jobs.approve(yearly.id)

    truth = next(i for i in office.truth if i["file"] == "policy_a_2.pdf")["values"]
    assert job.file.values["Jahresbeitrag"].normalized == truth["annual_premium"]
    assert "Beitrag" not in job.file.values
    [done] = office.run("Okafor")
    assert done.state == "handed_over"
    assert len(office.gdv_files()) == 1


def test_hand_over_writes_the_optional_values_of_the_shipped_profile_into_the_gdv_file(
    office: Office,
) -> None:
    # Layout a prints issue date, net premium and annual premium; layout c of
    # the invoice prints invoice date, period, net premium and tax.
    policy = office.arrive("Okafor", "policy_a_2.pdf", payment_mode="jährlich")
    invoice = office.arrive("Okafor", "premium_invoice_c_1.pdf")
    jobs = [office.jobs.approve(entry.id) for entry in (policy, invoice)]
    assert {"Nettobeitrag", "Ausstellungsdatum", "Jahresbeitrag"} <= set(jobs[0].file.values)
    assert {"Rechnungsdatum", "Zeitraum von", "Zeitraum bis", "Nettobeitrag",
            "Versicherungsteuer"} <= set(jobs[1].file.values)

    assert [job.state for job in office.run("Okafor")] == ["handed_over"] * 2
    [file] = office.gdv_files()
    contracts = {c["printed"]: c for c in reader.parse(file.read_bytes(), "cp850", b"\r\n").values()}

    def truth(name: str) -> dict:
        return next(i for i in office.truth if i["file"] == name)["values"]

    def day(iso: str) -> str:
        return iso[8:10] + iso[5:7] + iso[0:4]

    paper = truth("policy_a_2.pdf")
    written = contracts[paper["policy_number"]]
    assert written["issued"] == day(paper["issue_date"])
    assert written["net"] == round(paper["net_premium"] * 100)
    assert written["gross"] == round(paper["annual_premium"] * 100)

    paper = truth("premium_invoice_c_1.pdf")
    [collection] = contracts[paper["policy_number"]]["collections"]
    assert collection["created"] == day(paper["invoice_date"])
    assert (collection["from"], collection["to"]) == (day(paper["period_start"]), day(paper["period_end"]))
    assert collection["net"] == round(paper["net_premium"] * 100)
    assert collection["tax"] == round(paper["insurance_tax"] * 100)
    assert collection["gross"] == round(paper["premium"] * 100)


# --- Deleting (Z6.3, Z6.4) ----------------------------------------------------


def handed_over(office: Office) -> tuple[list, Path]:
    """Three contracts of one customer in one GDV file; the third is done."""
    entries = [
        office.arrive("Okafor", file)
        for file in ("policy_b_1.pdf", "premium_invoice_c_1.pdf", "policy_b_3.pdf")
    ]
    for entry in entries:
        office.jobs.approve(entry.id)
    jobs = office.run("Okafor")
    assert [job.state for job in jobs] == ["handed_over"] * 3
    office.jobs.move(jobs[2].id, "done", "imported")
    [file] = office.gdv_files()
    return entries, file


def states(office: Office) -> list[tuple[str, str]]:
    return [(job.state, job.transitions[-1].reason) for job in office.jobs.all()]


def test_inbox_delete_removes_the_gdv_file_and_fails_the_other_contracts_of_that_file(
    office: Office,
) -> None:
    entries, file = handed_over(office)
    namesake = office.desk.root / "elsewhere" / file.name
    namesake.parent.mkdir()
    namesake.write_bytes(file.read_bytes())
    deleted = office.jobs.all()[0]

    office.jobs.delete_entry(entries[0].id)

    assert office.gdv_files() == []
    assert namesake.is_file(), "a file of the same name elsewhere stays"
    assert not Path(deleted.handover_path).exists()
    assert list(office.handover.iterdir()) == [], "nothing of the removed hand-over stays"
    assert [job.handover_path for job in office.jobs.all()] == [None, None]
    assert states(office) == [("failed", "hand-over-file-removed"), ("done", "imported")]
    assert office.desk.inbox.db.query("SELECT 1 FROM job WHERE format_file IS NOT NULL") == []

    # A person releases the failed contract; the next run writes it without the deleted one.
    office.jobs.release(office.jobs.all()[0].id)
    [again] = office.run("Okafor")
    assert again.state == "handed_over"
    [rewritten] = office.gdv_files()
    numbers = {key[1] for key in reader.parse(rewritten.read_bytes(), "cp850", b"\r\n")}
    gone = next(i for i in office.truth if i["file"] == "policy_b_1.pdf")["values"]
    assert gone["policy_number"] not in numbers and len(numbers) == 1


def test_retention_removes_the_gdv_file_of_a_done_entry_past_the_period(office: Office) -> None:
    _, file = handed_over(office)
    office.desk.inbox.db.write(
        "UPDATE job_transition SET at = '2020-01-01T00:00:00+00:00' WHERE to_state = 'done'"
    )

    assert office.jobs.apply_retention() == 1

    assert not file.exists()
    assert states(office) == [("failed", "hand-over-file-removed")] * 2
    assert len(office.desk.inbox.entries()) == 2


def test_inbox_delete_waits_for_a_hand_over_run_of_the_same_customer(
    office: Office, monkeypatch: pytest.MonkeyPatch
) -> None:
    entries = [
        office.arrive("Okafor", file) for file in ("policy_b_1.pdf", "premium_invoice_c_1.pdf")
    ]
    for entry in entries:
        office.jobs.approve(entry.id)
    writing, may_finish = threading.Event(), threading.Event()
    write = hand_over.FORMATS["gdv"].hand_over

    class SlowWriter:
        """The real writer, held between starting and writing its file."""

        check = staticmethod(hand_over.FORMATS["gdv"].check)

        @staticmethod
        def hand_over(*arguments, **options):
            writing.set()
            assert may_finish.wait(timeout=20)
            return write(*arguments, **options)

    monkeypatch.setitem(hand_over.FORMATS, "gdv", SlowWriter)
    failures: list[BaseException] = []

    def guarded(action) -> threading.Thread:
        def run() -> None:
            try:
                action()
            except BaseException as error:
                failures.append(error)

        thread = threading.Thread(target=run)
        thread.start()
        return thread

    run = guarded(lambda: office.run("Okafor"))
    assert writing.wait(timeout=20)
    delete = guarded(lambda: office.jobs.delete_entry(entries[0].id))
    delete.join(timeout=0.5)
    assert delete.is_alive(), "the deletion waits while the run writes"
    assert len(office.desk.inbox.entries()) == 2

    may_finish.set()
    run.join(timeout=20)
    delete.join(timeout=20)

    assert failures == []
    assert list(office.handover.iterdir()) == [], "the file the run wrote went with the entry"
    assert [entry.id for entry in office.desk.inbox.entries()] == [entries[1].id]
    assert states(office) == [("failed", "hand-over-file-removed")]


# --- Half-written files in the hand-over folder -----------------------------------

JOB_TEMPORARY = f".{'0f' * 16}.json.tmp"
GDV_PART = "Okafor_20261110-093000.gdv.part"
NOT_OURS = [
    "Okafor_20261110-093000.gdv",
    f"{'0f' * 16}.json",
    f".{'0f' * 16}.json.tmp.bak",
    f"{'0f' * 16}.json.tmp",
    ".notes.json.tmp",
    "Okafor.gdv.part",
    "scan.pdf.part",
    "x.gdv.part.txt",
]


def test_hand_over_leftovers_of_both_patterns_go_and_no_other_file(office: Office) -> None:
    for name in (JOB_TEMPORARY, GDV_PART, *NOT_OURS):
        (office.handover / name).write_text("Tischlerei Okafor", encoding="utf-8")
    (office.handover / "Meier_20261110-093000.gdv.part").mkdir()
    elsewhere = office.desk.folder / GDV_PART
    elsewhere.write_text("x", encoding="utf-8")

    hand_over.clear_leftovers(office.jobs, office.desk.inbox)

    kept = sorted(p.name for p in office.handover.iterdir())
    assert kept == sorted([*NOT_OURS, "Meier_20261110-093000.gdv.part"])
    assert elsewhere.is_file(), "only the hand-over folder is cleared"


def test_hand_over_leftovers_without_a_folder_or_with_a_missing_one_clear_nothing(
    office: Office, monkeypatch: pytest.MonkeyPatch
) -> None:
    office.handover.rmdir()
    hand_over.clear_leftovers(office.jobs, office.desk.inbox)

    monkeypatch.setattr(office.desk.inbox, "handover_folder", lambda: None)
    hand_over.clear_leftovers(office.jobs, office.desk.inbox)


def test_hand_over_leftovers_are_cleared_at_start_and_when_the_folder_is_chosen(
    client,  # noqa: F811
) -> None:
    import substrakt.app as app_module

    watched = Path(app_module.CONFIG.allowed_roots[0]) / "leftovers"
    folder = watched / OUTPUT
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for name in (JOB_TEMPORARY, GDV_PART, "keep.txt", "x.json.tmp", "x.gdv.part"):
            (folder / name).write_text("x", encoding="utf-8")
        chosen = client.post("/inbox/settings", json={"folder": str(watched)}, headers=auth())
        assert chosen.status_code == 200
        assert sorted(p.name for p in folder.iterdir()) == ["keep.txt", "x.gdv.part", "x.json.tmp"]

        (folder / GDV_PART).write_text("x", encoding="utf-8")
        app_module._stop_inbox()
        app_module._inbox()
        assert sorted(p.name for p in folder.iterdir()) == ["keep.txt", "x.gdv.part", "x.json.tmp"]
    finally:
        app_module._stop_inbox()
        shutil.rmtree(watched)


def test_hand_over_leftovers_wait_for_a_running_run_and_leave_its_part_file(
    office: Office, monkeypatch: pytest.MonkeyPatch
) -> None:
    office.jobs.approve(office.arrive("Okafor", "policy_b_1.pdf").id)
    reading, may_finish = threading.Event(), threading.Event()
    check = gdv.reader.check

    def slow_check(*arguments):
        reading.set()
        assert may_finish.wait(timeout=20)
        return check(*arguments)

    monkeypatch.setattr(gdv.reader, "check", slow_check)
    run = threading.Thread(target=lambda: office.run("Okafor"))
    run.start()
    assert reading.wait(timeout=20)
    [part] = office.handover.iterdir()
    assert gdv.PART.fullmatch(part.name)

    clear = threading.Thread(
        target=lambda: hand_over.clear_leftovers(office.jobs, office.desk.inbox)
    )
    clear.start()
    clear.join(timeout=0.5)
    assert clear.is_alive(), "the clearing waits while the run writes"
    assert part.is_file()

    may_finish.set()
    run.join(timeout=20)
    clear.join(timeout=20)

    assert states(office) == [("handed_over", "job-file-written")]
    assert len(office.gdv_files()) == 1


@pytest.mark.parametrize("error", [RuntimeError("reader"), KeyboardInterrupt()])
def test_hand_over_run_that_ends_in_an_exception_leaves_no_part_file(
    office: Office, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    office.jobs.approve(office.arrive("Okafor", "policy_b_1.pdf").id)

    def broken(*_arguments):
        assert len(list(office.handover.glob("*.part"))) == 1
        raise error

    monkeypatch.setattr(gdv.reader, "check", broken)

    with pytest.raises(type(error)):
        office.run("Okafor")

    assert list(office.handover.iterdir()) == []


def test_job_file_whose_writing_ends_in_any_exception_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = jobs_module.JobFile.model_validate(
        {
            "id": "0f" * 16, "idempotency_key": "k", "approved_at": "2026-11-10T09:30:00+00:00",
            "profile": "p", "target": "t", "kind": "policy", "customer": "Okafor",
            "file": {"path": "a.pdf", "sha256": "0" * 64}, "pages": {"first": 1, "last": 1},
            "values": {},
        }
    )

    def interrupted(_descriptor: int) -> None:
        assert jobs_module.TEMPORARY.fullmatch(next(tmp_path.iterdir()).name)
        raise KeyboardInterrupt

    monkeypatch.setattr(jobs_module.os, "fsync", interrupted)

    with pytest.raises(KeyboardInterrupt):
        jobs_module.write_job_file(tmp_path, file)

    assert list(tmp_path.iterdir()) == []


def test_hand_over_run_leaves_no_gdv_file_when_a_job_file_cannot_be_written(
    office: Office, monkeypatch: pytest.MonkeyPatch
) -> None:
    for file in ("policy_b_1.pdf", "premium_invoice_c_1.pdf"):
        office.jobs.approve(office.arrive("Okafor", file).id)
    write, calls = hand_over.write_job_file, []

    def second_fails(folder: Path, file):
        calls.append(file.id)
        if len(calls) == 2:
            # The file with both contracts has its final name by now.
            assert len(office.gdv_files()) == 1
            raise OSError("disk full")
        return write(folder, file)

    monkeypatch.setattr(hand_over, "write_job_file", second_fails)
    jobs = office.run("Okafor")

    assert [job.state for job in jobs] == ["failed"] * 2
    assert list(office.handover.iterdir()) == [], "no file that no job points to"
    assert office.desk.inbox.db.query(
        "SELECT 1 FROM job WHERE format_file IS NOT NULL OR handover_path IS NOT NULL"
    ) == []

    # Released, the contracts are written once, into one file.
    monkeypatch.undo()
    for job in jobs:
        office.jobs.release(job.id)
    assert [job.state for job in office.run("Okafor")] == ["handed_over"] * 2
    [file] = office.gdv_files()
    rows = office.desk.inbox.db.query("SELECT format_file FROM job")
    assert {row["format_file"] for row in rows} == {str(file)}
