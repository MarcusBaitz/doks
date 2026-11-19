"""Possible duplicates by read values: marked for a person, never discarded by themselves."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import Desk, put, variant
from test_privacy import MARKED, database_bytes, settle_values, shipped_queue, truth_of

from substrakt import document_kinds
from substrakt import inbox as inbox_module
from substrakt.comparison import comparable, comparison_key
from substrakt.errors import ApprovalRefused, CorrectionRefused
from substrakt.inbox import Correction, InboxEntry
from substrakt.jobs import Jobs
from substrakt.parsers import ocr

ROOT = Path(__file__).resolve().parents[2]
needs_ocr = pytest.mark.skipif(not ocr.available(), reason="Tesseract or deu.traineddata missing")


class Folder:
    """A desk with the shipped profile and its job queue."""

    def __init__(self, desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.desk, self.corpus = desk, corpus / "insurance"
        self.jobs, _, _ = shipped_queue(desk, monkeypatch)

    def arrive(self, name: str, source: str, number: int | None = None) -> InboxEntry:
        """Put a corpus file into the folder; a number changes its bytes, not its values."""
        content = (self.corpus / source).read_bytes()
        put(self.desk, f"Kunde/{name}", content if number is None else variant(content, number))
        self.desk.settle()
        return self.entry(name)

    def entry(self, name: str) -> InboxEntry:
        return self.desk.entries()[f"Kunde/{name}"]  # type: ignore[return-value]

    def marks(self) -> dict[str, int | None]:
        return {e.file_name: e.possible_duplicate_of for e in self.desk.inbox.entries()}


@pytest.fixture
def folder(desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch) -> Folder:
    return Folder(desk, corpus, monkeypatch)


# --- Z3.13 -----------------------------------------------------------------------


@needs_ocr
@pytest.mark.parametrize(
    ("document", "scan"),
    [("policy_a_1.pdf", "policy_a_1_scan300.png"), ("policy_a_2.pdf", "policy_a_2_scan150.png")],
)
def test_inbox_value_duplicate_second_scan_of_a_document_is_read_and_marked(
    folder: Folder, document: str, scan: str
) -> None:
    first = folder.arrive(document, document)
    second = folder.arrive(scan, scan)

    assert second.sha256 != first.sha256
    assert (second.state, second.kind) == ("waiting", first.kind), "read, not discarded"
    assert second.possible_duplicate_of == first.id
    assert second.duplicate_of is None, "no certain duplicate: the content differs"
    assert {value.field for value in second.values if value.grounded} >= {"policy_number"}
    assert folder.entry(document).possible_duplicate_of is None
    assert folder.desk.parsed == {document: 1, scan: 1}


def test_inbox_value_duplicate_is_marked_for_other_bytes_with_the_same_values(
    folder: Folder,
) -> None:
    first = folder.arrive("first.pdf", "policy_a_1.pdf")
    second = folder.arrive("second.pdf", "policy_a_1.pdf", 1)
    third = folder.arrive("third.pdf", "policy_a_1.pdf", 2)

    assert folder.marks() == {"first.pdf": None, "second.pdf": first.id, "third.pdf": first.id}
    assert [entry.state for entry in (first, second, third)] == ["waiting"] * 3
    folder.desk.inbox.stop()
    assert folder.desk.restart().entry(second.id).possible_duplicate_of == first.id


def test_inbox_value_duplicate_is_not_seen_for_another_date_another_kind_or_another_number(
    folder: Folder,
) -> None:
    first = folder.arrive("first.pdf", "policy_a_1.pdf")
    other_number = folder.arrive("other.pdf", "policy_a_2.pdf")
    assert other_number.possible_duplicate_of is None

    # The same policy with another date of issue is a later version, not a copy.
    other_date = folder.arrive("date.pdf", "policy_a_1.pdf", 1)
    assert other_date.possible_duplicate_of == first.id
    corrected = folder.desk.inbox.correct(
        other_date.id, Correction(values={"issue_date": "20.09.2024"})
    )
    assert corrected.possible_duplicate_of is None

    # The same number and date read as another kind of document.
    other_kind = folder.arrive("kind.pdf", "policy_a_1.pdf", 2)
    assert other_kind.possible_duplicate_of == first.id
    changed = folder.desk.inbox.correct(other_kind.id, Correction(kind="contract_change"))
    assert (changed.kind, changed.possible_duplicate_of) == ("contract_change", None)


def test_inbox_value_duplicate_needs_every_comparison_value_read_unambiguously(
    folder: Folder,
) -> None:
    first = folder.arrive("first.pdf", "policy_a_1.pdf")
    kind = document_kinds.load("policy")
    assert comparison_key(kind, first.values) is not None

    for name in kind.same_document:
        unclear = [
            value.model_copy(update={"grounded": False}) if value.field == name else value
            for value in first.values
        ]
        missing = [value for value in first.values if value.field != name]
        assert comparison_key(kind, unclear) is None, f"{name} not unambiguous"
        assert comparison_key(kind, missing) is None, f"{name} missing"
    assert comparison_key(None, first.values) is None

    # An entry without a key is neither marked nor a counterpart.
    folder.desk.inbox.db.write("UPDATE inbox_entry SET comparison_key = NULL")
    assert folder.arrive("second.pdf", "policy_a_1.pdf", 1).possible_duplicate_of is None


def test_inbox_value_duplicate_is_never_seen_for_a_kind_that_names_no_values(
    desk: Desk, invoice: bytes
) -> None:
    assert document_kinds.load("invoice").same_document == []
    desk.inbox.choose_folder(str(desk.folder))
    put(desk, "Meier/a.pdf", variant(invoice, 1))
    put(desk, "Meier/b.pdf", variant(invoice, 2))

    desk.settle()

    assert [entry.possible_duplicate_of for entry in desk.inbox.entries()] == [None, None]


def test_inbox_value_duplicate_compares_letters_and_digits_and_normalised_dates() -> None:
    assert comparable("NV-HA 2162/6533") == comparable("nv-ha-2162-6533") == "nvha21626533"
    assert comparable(1454.24) != comparable(1454.25)
    assert comparable("2024-09-19") == comparable("2024-09-19")


def test_inbox_value_duplicate_follows_a_correction_in_both_directions(folder: Folder) -> None:
    first = folder.arrive("first.pdf", "policy_a_1.pdf")
    other = folder.arrive("other.pdf", "policy_a_2.pdf")
    truth = truth_of(folder.corpus.parent, "policy_a_1.pdf")["values"]
    year, month, day = truth["issue_date"].split("-")
    same = {
        "policy_number": truth["policy_number"].replace("-", " "),
        "issue_date": f"{day}.{month}.{year}",
    }

    # A normal entry becomes a possible duplicate when its values are corrected to match.
    marked = folder.desk.inbox.correct(other.id, Correction(values=same))
    assert marked.possible_duplicate_of == first.id
    assert folder.entry("first.pdf").possible_duplicate_of is None, "the two do not wait for each other"

    # And back, when the first entry is corrected away from it.
    folder.desk.inbox.correct(first.id, Correction(values={"policy_number": "ZZ-0000"}))
    assert folder.marks() == {"first.pdf": None, "other.pdf": None}


def test_inbox_value_duplicate_names_are_in_the_kind_files_and_not_in_the_core() -> None:
    named = {
        name for kind in document_kinds.load_all().values() for name in kind.same_document
    }
    assert {"policy_number", "issue_date", "change_date", "invoice_date"} <= named
    core = ["comparison.py", "inbox.py", "jobs.py", "app.py", "hand_over.py"]
    for module in core:
        text = (ROOT / "sidecar" / "substrakt" / module).read_text(encoding="utf-8")
        assert [name for name in named if name in text] == [], module


# --- Z4.9, data part -------------------------------------------------------------


def marked_pair(folder: Folder) -> tuple[InboxEntry, InboxEntry]:
    """A first entry and a possible duplicate of it, both with every required value settled."""
    truth = truth_of(folder.corpus.parent, "policy_a_2.pdf")
    first = folder.arrive("first.pdf", "policy_a_2.pdf")
    second = folder.arrive("second.pdf", "policy_a_2.pdf", 1)
    for entry in (first, second):
        settle_values(folder.desk, entry, truth)
    second = folder.entry("second.pdf")
    assert second.possible_duplicate_of == first.id
    return first, second


def test_approval_duplicate_is_refused_until_a_person_has_decided(folder: Folder) -> None:
    first, second = marked_pair(folder)

    with pytest.raises(ApprovalRefused) as refused:
        folder.jobs.approve(second.id)

    assert refused.value.fields == {"reason": "possible-duplicate-undecided", "other": first.id}
    assert folder.jobs.all() == []
    assert folder.jobs.approve(first.id).entry_id == first.id, "the first entry is not held up"


def test_approval_duplicate_decided_as_the_same_document_creates_no_job(
    folder: Folder, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = marked_pair(folder)
    monkeypatch.setattr(inbox_module.getpass, "getuser", lambda: "clerk-a")

    decided = folder.desk.inbox.decide_duplicate(second.id, same=True)

    assert (decided.state, decided.duplicate_of, decided.duplicate_decision) == (
        "duplicate", first.id, "same",
    )
    with pytest.raises(ApprovalRefused) as refused:
        folder.jobs.approve(second.id)
    assert refused.value.fields["reason"] == "entry-not-waiting"
    assert folder.jobs.all() == []
    folder.desk.inbox.stop()
    [row] = folder.desk.restart().db.query(
        "SELECT duplicate_decided_by, duplicate_decided_at FROM inbox_entry WHERE id = ?", second.id
    )
    assert row["duplicate_decided_by"] == "clerk-a"
    assert row["duplicate_decided_at"].startswith("20")


def test_approval_duplicate_decided_as_a_new_document_is_approved_as_usual(
    folder: Folder, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = marked_pair(folder)
    monkeypatch.setattr(inbox_module.getpass, "getuser", lambda: "clerk-b")

    decided = folder.desk.inbox.decide_duplicate(second.id, same=False)
    job = folder.jobs.approve(second.id)

    assert (decided.state, decided.duplicate_decision, decided.duplicate_of) == (
        "waiting", "new", None,
    )
    assert decided.possible_duplicate_of == first.id, "the link stays visible"
    assert job.entry_id == second.id
    [row] = folder.desk.inbox.db.query(
        "SELECT duplicate_decided_by FROM inbox_entry WHERE id = ?", second.id
    )
    assert row["duplicate_decided_by"] == "clerk-b"

    # A correction that keeps the same counterpart keeps the decision.
    third = folder.arrive("third.pdf", "policy_a_2.pdf", 2)
    folder.desk.inbox.decide_duplicate(third.id, same=False)
    kept = folder.desk.inbox.correct(third.id, Correction(values={"insurer": "Nordlicht AG"}))
    assert (kept.possible_duplicate_of, kept.duplicate_decision) == (first.id, "new")


def test_approval_duplicate_decision_needs_a_mark_and_ends_with_the_first_entry(
    folder: Folder,
) -> None:
    first, second = marked_pair(folder)

    for unmarked in (first.id,):
        with pytest.raises(CorrectionRefused) as refused:
            folder.desk.inbox.decide_duplicate(unmarked, same=True)
        assert refused.value.fields["reason"] == "no-possible-duplicate"

    # When the first entry is deleted, nothing is left to be a duplicate of.
    Jobs(folder.desk.inbox).delete_entry(first.id)
    assert folder.entry("second.pdf").possible_duplicate_of is None
    assert folder.jobs.approve(second.id).entry_id == second.id


def test_approval_duplicate_decided_as_the_same_document_keeps_no_value_and_no_correction(
    folder: Folder,
) -> None:
    first, second = marked_pair(folder)
    inbox = folder.desk.inbox
    inbox.correct(second.id, Correction(values={"insurer": MARKED}))
    third = folder.arrive("third.pdf", "policy_a_2.pdf", 2)
    inbox.db.write(
        "UPDATE inbox_entry SET possible_duplicate_of = ? WHERE id = ?", second.id, third.id
    )
    assert MARKED.encode() in database_bytes(folder.desk)
    number = truth_of(folder.corpus.parent, "policy_a_2.pdf")["values"]["policy_number"]

    decided = inbox.decide_duplicate(second.id, same=True)

    assert (decided.values, decided.kind, decided.page_count) == ([], None, None)
    assert (decided.state, decided.duplicate_of, decided.duplicate_decision) == (
        "duplicate", first.id, "same",
    )
    [row] = inbox.db.query("SELECT * FROM inbox_entry WHERE id = ?", second.id)
    byte_duplicate = {"values_json": "[]", "timings_json": "{}", "comparison_key": None}
    assert {name: row[name] for name in byte_duplicate} == byte_duplicate
    assert inbox.db.query("SELECT * FROM inbox_correction WHERE entry_id = ?", second.id) == []
    assert MARKED.encode() not in database_bytes(folder.desk), "also not in freed pages or the log"
    # The first entry still holds the number; the decided one was the only other holder.
    inbox.db.write("UPDATE inbox_entry SET values_json = '[]' WHERE id IN (?, ?)", first.id, third.id)
    inbox.db.query("PRAGMA wal_checkpoint(TRUNCATE)")
    assert number.encode() not in database_bytes(folder.desk)
    # An entry that pointed to the decided one points to an entry that still waits.
    assert folder.entry("third.pdf").possible_duplicate_of == first.id
    # The decision is final: nothing is left to decide or to correct.
    with pytest.raises(CorrectionRefused):
        inbox.decide_duplicate(second.id, same=False)


def test_approval_duplicate_decided_as_a_new_document_keeps_its_values(folder: Folder) -> None:
    _, second = marked_pair(folder)

    decided = folder.desk.inbox.decide_duplicate(second.id, same=False)

    assert (decided.values, decided.kind) == (second.values, second.kind)


def test_approval_duplicate_decision_that_meets_an_approved_entry_changes_nothing(
    folder: Folder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, second = marked_pair(folder)
    inbox = folder.desk.inbox
    # As between two requests: “new” and the approval ran after this “same” looked.
    inbox.decide_duplicate(second.id, same=False)
    looked = inbox.entry(second.id)
    job = folder.jobs.approve(second.id)
    monkeypatch.setattr(inbox, "entry", lambda _id: looked)

    with pytest.raises(CorrectionRefused) as refused:
        inbox.decide_duplicate(second.id, same=True)
    monkeypatch.undo()

    assert refused.value.fields["reason"] == "no-possible-duplicate"
    after = inbox.entry(second.id)
    assert (after.state, after.duplicate_decision, after.duplicate_of) == ("approved", "new", None)
    assert after.values == looked.values and after.values, "the job's entry keeps its values"
    assert folder.jobs.get(job.id).entry_id == second.id


def test_approval_duplicate_decided_as_the_same_document_during_an_approval_creates_no_job(
    folder: Folder, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = marked_pair(folder)
    inbox = folder.desk.inbox
    # As between two requests: the approval looked, then "same" was stored.
    inbox.decide_duplicate(second.id, same=False)
    looked = inbox.entry(second.id)
    inbox.db.write("UPDATE inbox_entry SET duplicate_decision = NULL WHERE id = ?", second.id)
    decided = inbox.decide_duplicate(second.id, same=True)
    monkeypatch.setattr(inbox, "entry", lambda _id: looked)

    with pytest.raises(ApprovalRefused) as refused:
        folder.jobs.approve(second.id)
    monkeypatch.undo()

    assert refused.value.fields["reason"] == "entry-not-waiting"
    assert folder.jobs.all() == [], "no job, and no transition of one"
    assert inbox.db.query("SELECT 1 FROM job_transition") == []
    assert inbox.entry(second.id) == decided
    assert (decided.state, decided.duplicate_of, decided.values) == ("duplicate", first.id, [])


@pytest.mark.parametrize(
    "late", [Correction(values={"insurer": "Nordlicht AG"}), Correction(kind="contract_change")]
)
def test_correction_that_meets_an_approved_entry_changes_nothing(
    folder: Folder, monkeypatch: pytest.MonkeyPatch, late: Correction
) -> None:
    first, second = marked_pair(folder)
    inbox = folder.desk.inbox
    # As between two requests: the correction looked, then the entry was approved.
    looked = inbox.entry(first.id)
    job = folder.jobs.approve(first.id)
    approved = inbox.entry(first.id)
    corrections = inbox.db.query("SELECT * FROM inbox_correction")
    monkeypatch.setattr(inbox, "entry", lambda _id: looked)

    with pytest.raises(CorrectionRefused) as refused:
        inbox.correct(first.id, late)
    monkeypatch.undo()

    assert refused.value.fields["reason"] == "entry-not-waiting"
    assert inbox.entry(first.id) == approved, "the entry shows what its job holds"
    assert inbox.db.query("SELECT * FROM inbox_correction") == corrections
    assert folder.jobs.get(job.id).file == job.file
    # No mark was computed for the approved entry or for the one pointing to it.
    assert folder.entry("second.pdf") == second


def test_correction_built_on_values_another_correction_changed_is_refused(
    folder: Folder, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _ = marked_pair(folder)
    inbox = folder.desk.inbox
    # As between two requests: both corrections looked, then the first was stored.
    looked = inbox.entry(first.id)
    stored = inbox.correct(first.id, Correction(values={"insurer": "Nordlicht AG"}))
    corrections = inbox.db.query("SELECT * FROM inbox_correction")
    monkeypatch.setattr(inbox, "entry", lambda _id: looked)

    with pytest.raises(CorrectionRefused) as refused:
        inbox.correct(first.id, Correction(values={"insurer": "Südwind AG"}))
    monkeypatch.undo()

    assert refused.value.fields["reason"] == "entry-changed"
    assert inbox.entry(first.id) == stored, "the first correction is not overwritten"
    assert inbox.db.query("SELECT * FROM inbox_correction") == corrections
    # Every row's "before" is what stood there before it.
    last: dict[str, str | None] = {}
    for row in corrections:
        if row["value_name"] in last:
            assert row["before"] == last[row["value_name"]]
        last[row["value_name"]] = row["after"]
    insurer = next(value for value in stored.values if value.field == "insurer")
    assert last["insurer"] == insurer.value == "Nordlicht AG"


def test_approval_that_meets_a_deleted_entry_is_refused_and_leaves_nothing(
    folder: Folder, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _ = marked_pair(folder)
    inbox = folder.desk.inbox
    # As between two requests: the approval looked, then the entry was deleted.
    looked = inbox.entry(first.id)
    folder.jobs.delete_entry(first.id)
    monkeypatch.setattr(inbox, "entry", lambda _id: looked)

    with pytest.raises(ApprovalRefused) as refused:
        folder.jobs.approve(first.id)
    monkeypatch.undo()

    assert refused.value.fields["reason"] == "entry-not-waiting"
    assert folder.jobs.all() == [], "no job, and no transition of one"
    assert inbox.db.query("SELECT 1 FROM job_transition") == []
    assert list((folder.desk.folder / "Ausgabe").iterdir()) == []
