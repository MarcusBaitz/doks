"""What the broker is promised: no transfer, deletion, retention, a record of who approved."""

from __future__ import annotations

import json
import logging
import shutil
import socket
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import Desk, Queue, put, variant

from substrakt import audit, logging_setup, pipeline_profiles
from substrakt import inbox as inbox_module
from substrakt import jobs as jobs_module
from substrakt.db.session import Session
from substrakt.errors import FileChanged, InboxEntryUnknown, SubstraktError
from substrakt.inbox import DEFAULT_RETENTION_DAYS, OUTPUT, Correction, InboxEntry
from substrakt.jobs import JobFile, Jobs
from substrakt.parsers import ocr

FIXTURES = Path(__file__).parent / "fixtures"
LOOPBACK = {"127.0.0.1", "::1"}
# A corrected value that no file name, key or message can contain by chance.
MARKED = "ZZ-UNIQUE-771"
# Typed by hand in the row of a value, as in Review.
BY_HAND = "ZZ-HAND-4412"


# --- Z6.1 ------------------------------------------------------------------------


class OutboundConnection(AssertionError):
    """A socket was pointed at an address that is not this machine."""


@pytest.fixture
def loopback_only(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Let every socket reach 127.0.0.1 and ::1 only; returns the refused targets.

    The list matters as much as the exception: code that swallows the
    exception still leaves the attempt here.
    """
    attempts: list[str] = []

    def refuse(host: object) -> None:
        if host not in LOOPBACK:
            attempts.append(str(host))
            raise OutboundConnection(str(host))

    def guarded(name: str):
        original = getattr(socket.socket, name)

        def call(self, *arguments):
            # connect and connect_ex take the address first, sendto takes it last.
            address = arguments[-1] if name == "sendto" else arguments[0]
            refuse(address[0] if isinstance(address, tuple) else address)
            return original(self, *arguments)

        return call

    for name in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, name, guarded(name))
    resolve = socket.getaddrinfo

    def resolving(host, *arguments, **options):
        refuse(host)
        return resolve(host, *arguments, **options)

    monkeypatch.setattr(socket, "getaddrinfo", resolving)
    return attempts


def shipped_queue(desk: Desk, monkeypatch: pytest.MonkeyPatch) -> tuple[Jobs, Path, list[JobFile]]:
    """The shipped profile, its output folder and a writer for its target."""
    pipeline_profiles.configure(None)
    [shipped] = pipeline_profiles.titles()
    desk.inbox.choose_profile(shipped)
    desk.inbox.choose_folder(str(desk.folder))
    handover = desk.folder / OUTPUT
    received: list[JobFile] = []
    target = pipeline_profiles.load(shipped).target
    monkeypatch.setitem(jobs_module.WRITERS, target, lambda file, _: received.append(file))
    return Jobs(desk.inbox), handover, received


def truth_of(corpus: Path, file: str) -> dict:
    truth = json.loads((corpus / "insurance" / "truth.json").read_text(encoding="utf-8"))
    return next(item for item in truth if item["file"] == file)


def settle_values(desk: Desk, entry: InboxEntry, truth: dict) -> None:
    """Enter, as a clerk would, every required value that was not read unambiguously."""
    required = pipeline_profiles.load(entry.profile).kinds[truth["kind"]].values
    read = {value.field: value for value in entry.values}
    missing = {
        name: str(truth["values"][name])
        for name in required
        if not (read[name].value and read[name].grounded)
    }
    if missing:
        desk.inbox.correct(entry.id, Correction(values=missing))


SCAN = pytest.param(
    "policy_a_1_scan300.png",
    marks=pytest.mark.skipif(not ocr.available(), reason="Tesseract or deu.traineddata missing"),
)


@pytest.mark.parametrize(
    "file", ["policy_a_1.pdf", "contract_change_b_1.pdf", "premium_invoice_c_1.pdf", SCAN]
)
def test_no_outbound_connection_from_the_scan_folder_to_the_hand_over_job(
    desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch, loopback_only: list[str], file: str
) -> None:
    jobs, handover, received = shipped_queue(desk, monkeypatch)
    truth = truth_of(corpus, file)
    put(desk, f"Kunde/{file}", (corpus / "insurance" / file).read_bytes())

    desk.settle()
    [entry] = desk.inbox.entries()
    assert (entry.state, entry.kind) == ("waiting", truth["kind"])
    settle_values(desk, entry, truth)
    job = jobs.approve(entry.id)

    assert job.state == "handed_over"
    assert [file.name for file in handover.iterdir()] == [f"{job.id}.json"]
    assert [file.id for file in received] == [job.id]
    assert loopback_only == []


def test_no_outbound_guard_fails_a_connection_made_inside_the_path(
    desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch, loopback_only: list[str]
) -> None:
    jobs, _, _ = shipped_queue(desk, monkeypatch)
    file = "policy_a_1.pdf"
    truth = truth_of(corpus, file)
    put(desk, f"Kunde/{file}", (corpus / "insurance" / file).read_bytes())
    desk.settle()
    [entry] = desk.inbox.entries()
    settle_values(desk, entry, truth)

    def phoning_home(_file: JobFile, _folder: Path) -> None:
        socket.create_connection(("192.0.2.1", 9), timeout=0.1)

    target = pipeline_profiles.load(entry.profile).target
    monkeypatch.setitem(jobs_module.WRITERS, target, phoning_home)
    with pytest.raises(OutboundConnection):
        jobs.approve(entry.id)
    assert loopback_only == ["192.0.2.1"]

    # The reading step swallows every exception; the attempt is recorded all the same.
    parse = desk.store.parse

    def resolving(path: Path, sha: str):
        socket.getaddrinfo("example.com", 443)
        return parse(path, sha)

    monkeypatch.setattr(desk.store, "parse", resolving)
    put(desk, "Kunde/other.pdf", variant((corpus / "insurance" / file).read_bytes(), 1))
    desk.settle()
    assert desk.entries()["Kunde/other.pdf"].state == "error"  # type: ignore[attr-defined]
    assert loopback_only == ["192.0.2.1", "example.com"]

    # The guard lets this machine through.
    listener = socket.create_server(("127.0.0.1", 0))
    socket.create_connection(listener.getsockname(), timeout=1).close()
    listener.close()


# --- Z6.2 ------------------------------------------------------------------------


def stored(db: Session) -> list[tuple]:
    return [
        tuple(row)
        for row in db.query(
            "SELECT occurred_at, action, target, bytes, result, mode FROM audit_log ORDER BY id"
        )
    ]


def test_audit_attempts_of_the_shell_reach_the_table_and_survive_a_restart(
    tmp_path: Path,
) -> None:
    # The fixture holds lines exactly as the shell writes them; a Rust test checks that.
    shutil.copy(FIXTURES / "egress_audit.jsonl", tmp_path / audit.SPOOL)
    db = Session(tmp_path / "substrakt.db")

    assert audit.ingest(db, tmp_path) == 2
    assert audit.ingest(db, tmp_path) == 0, "nothing is stored twice"
    db.close()

    rows = stored(Session(tmp_path / "substrakt.db"))
    assert [row[1:] for row in rows] == [
        ("export", "https://example.com/x", 0, "denied", "airgap"),
        ("export", "https://files.customer.internal/x", 0, "allowed", "onprem"),
    ]
    assert datetime.fromisoformat(rows[0][0]) == datetime.fromtimestamp(1794300000, UTC)
    assert [file.name for file in tmp_path.iterdir() if "audit" in file.name] == []


def test_audit_finishes_an_interrupted_take_over_and_skips_a_torn_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    lines = (FIXTURES / "egress_audit.jsonl").read_text(encoding="utf-8").splitlines()
    (tmp_path / "egress-audit.taken").write_text(lines[0] + "\n", encoding="utf-8")
    (tmp_path / audit.SPOOL).write_text(lines[1] + "\n" + lines[0][:40], encoding="utf-8")
    db = Session(tmp_path / "substrakt.db")

    assert audit.ingest(db, tmp_path) == 1, "the interrupted file first"
    with caplog.at_level(logging.ERROR):
        assert audit.ingest(db, tmp_path) == 1
    assert "1 lines of the spool were unreadable" in caplog.text

    assert [row[4] for row in stored(db)] == ["denied", "allowed"]


def test_audit_spool_is_taken_by_the_running_application(tmp_path: Path) -> None:
    import substrakt.app as app_module

    app_module._inbox()
    try:
        data_dir = app_module.CONFIG.data_dir
        before = len(stored(app_module._inbox().db))
        shutil.copy(FIXTURES / "egress_audit.jsonl", data_dir / audit.SPOOL)

        for chore in app_module._inbox().chores:
            chore()

        assert len(stored(app_module._inbox().db)) == before + 2
        assert not (data_dir / audit.SPOOL).exists()
    finally:
        app_module._stop_inbox()


# --- Z6.3 ------------------------------------------------------------------------


def database_bytes(desk: Desk) -> bytes:
    return b"".join(file.read_bytes() for file in sorted(desk.database.parent.iterdir()))


def approved(queue: Queue) -> jobs_module.Job:
    """Correct a value to a marked string and approve the entry."""
    queue.desk.inbox.correct(queue.entry.id, Correction(values={"document_number": MARKED}))
    return queue.jobs.approve(queue.entry.id)


def test_inbox_delete_removes_values_corrections_job_and_job_file_and_leaves_the_scan(
    queue: Queue, writer: list[JobFile]
) -> None:
    job = approved(queue)
    scan = Path(queue.entry.file_path)
    assert queue.files() == [f"{job.id}.json"]
    assert MARKED.encode() in database_bytes(queue.desk)

    queue.jobs.delete_entry(queue.entry.id)

    db = queue.desk.inbox.db
    for table in ("inbox_entry", "inbox_correction", "job", "job_transition"):
        assert db.query(f"SELECT * FROM {table}") == []
    assert queue.files() == []
    assert scan.is_file(), "the scanned file is not the application's to remove"
    assert MARKED.encode() not in database_bytes(queue.desk), "also not in freed pages or the log"
    with pytest.raises(InboxEntryUnknown):
        queue.jobs.delete_entry(queue.entry.id)


def test_inbox_delete_leaves_a_marker_without_values_so_the_file_is_not_read_again(
    queue: Queue, writer: list[JobFile]
) -> None:
    approved(queue)
    queue.jobs.delete_entry(queue.entry.id)
    marker = queue.desk.inbox.db.query("SELECT * FROM inbox_deleted")

    assert [(row["file_path"], row["sha256"]) for row in marker] == [
        (queue.entry.file_path, queue.entry.sha256)
    ]
    assert set(marker[0].keys()) == {"file_path", "sha256", "deleted_at"}
    for _ in range(2):
        queue.desk.settle()
        queue.desk.inbox.stop()
        queue.desk.restart()
    assert queue.desk.inbox.entries() == []
    assert queue.desk.parsed == {"policy.pdf": 1}

    # The marker goes when the file leaves the folder; the same file is then new again.
    scan = Path(queue.entry.file_path)
    content = scan.read_bytes()
    scan.unlink()
    queue.desk.settle()
    assert queue.desk.inbox.db.query("SELECT * FROM inbox_deleted") == []
    scan.write_bytes(content)
    queue.desk.settle()
    assert [entry.state for entry in queue.desk.inbox.entries()] == ["waiting"]


def test_inbox_delete_keeps_the_marker_while_the_watched_folder_is_unreachable(
    queue: Queue, writer: list[JobFile]
) -> None:
    queue.jobs.delete_entry(queue.entry.id)
    away = queue.desk.root / "share-is-down"

    queue.desk.folder.rename(away)
    queue.desk.settle()
    away.rename(queue.desk.folder)
    queue.desk.settle()

    assert len(queue.desk.inbox.db.query("SELECT * FROM inbox_deleted")) == 1
    assert queue.desk.inbox.entries() == []


def test_inbox_delete_removes_the_scan_only_on_request_and_never_a_namesake(
    queue: Queue, writer: list[JobFile]
) -> None:
    namesake = put(queue.desk, "Schulze/policy.pdf", variant(queue.invoice, 2))
    copy = put(queue.desk, "Schulze/copy.pdf", variant(queue.invoice, 1))
    queue.desk.settle()
    approved(queue)

    queue.jobs.delete_entry(queue.entry.id, delete_file=True)

    assert not Path(queue.entry.file_path).exists()
    assert namesake.is_file(), "a file of the same name elsewhere stays"
    assert copy.is_file(), "a file of the same content elsewhere stays"
    assert queue.desk.inbox.db.query("SELECT * FROM inbox_deleted") == []
    assert queue.files() == []
    assert {entry.file_name for entry in queue.desk.inbox.entries()} == {"policy.pdf", "copy.pdf"}


def test_inbox_delete_refuses_to_remove_a_file_that_changed_and_deletes_nothing(
    queue: Queue, writer: list[JobFile]
) -> None:
    job = approved(queue)
    scan = Path(queue.entry.file_path)
    scan.write_bytes(variant(queue.invoice, 7))

    with pytest.raises(FileChanged):
        queue.jobs.delete_entry(queue.entry.id, delete_file=True)

    assert scan.read_bytes() == variant(queue.invoice, 7)
    assert queue.desk.inbox.entry(queue.entry.id).state == "approved"
    assert queue.files() == [f"{job.id}.json"]

    # Without the file the entry can still go, and a missing scan is no obstacle.
    scan.unlink()
    queue.jobs.delete_entry(queue.entry.id, delete_file=True)
    assert queue.desk.inbox.entries() == []


# --- Z6.4 ------------------------------------------------------------------------


def done_since(queue: Queue, entry: InboxEntry, days: int) -> jobs_module.Job:
    """Approve an entry and let its job have been done for a number of days."""
    job = queue.jobs.approve(entry.id)
    queue.jobs.move(job.id, "done", "imported")
    at = (datetime.now(UTC) - timedelta(days=days)).astimezone().isoformat(timespec="seconds")
    queue.desk.inbox.db.write(
        "UPDATE job_transition SET at = ? WHERE job_id = ? AND to_state = 'done'", at, job.id
    )
    return job


def test_retention_period_is_a_setting_with_a_named_default(queue: Queue) -> None:
    assert queue.desk.inbox.settings().retention_days == DEFAULT_RETENTION_DAYS == 90

    queue.desk.inbox.choose_retention(30)
    queue.desk.inbox.stop()

    assert queue.desk.restart().settings().retention_days == 30


def test_retention_deletes_done_entries_older_than_the_period_with_their_job_files(
    queue: Queue, writer: list[JobFile]
) -> None:
    queue.desk.inbox.choose_retention(30)
    old = done_since(queue, queue.entry, days=31)
    recent = done_since(queue, queue.arrive("Meier/recent.pdf", 2), days=29)
    open_entry = queue.arrive("Meier/open.pdf", 3)
    waiting = queue.jobs.approve(open_entry.id)
    queue.desk.inbox.db.write(
        "UPDATE job_transition SET at = '2020-01-01T00:00:00+00:00' WHERE job_id = ?", waiting.id
    )
    assert f"{old.id}.json" in queue.files()

    assert queue.jobs.apply_retention() == 1

    assert {entry.file_name for entry in queue.desk.inbox.entries()} == {"recent.pdf", "open.pdf"}
    assert queue.files() == sorted([f"{recent.id}.json", f"{waiting.id}.json"])
    assert Path(queue.entry.file_path).is_file(), "retention never removes a scan"
    queue.desk.settle()
    assert len(queue.desk.inbox.entries()) == 2, "the deleted entry is not read again"

    queue.desk.inbox.choose_retention(20)
    assert queue.jobs.apply_retention() == 1
    assert [entry.file_name for entry in queue.desk.inbox.entries()] == ["open.pdf"]


def test_retention_runs_at_start_and_then_once_a_day(
    queue: Queue, writer: list[JobFile], monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(jobs_module.time, "monotonic", lambda: clock[0])
    runs: list[float] = []
    monkeypatch.setattr(queue.jobs, "apply_retention", lambda: runs.append(clock[0]) or 0)

    queue.jobs.keep_retention()
    clock[0] += jobs_module.RETENTION_INTERVAL - 1
    queue.jobs.keep_retention()
    clock[0] += 1
    queue.jobs.keep_retention()

    assert runs == [1000.0, 1000.0 + jobs_module.RETENTION_INTERVAL]


def test_retention_is_a_chore_of_the_running_application() -> None:
    import substrakt.app as app_module

    inbox = app_module._inbox()
    try:
        assert app_module._jobs().keep_retention in inbox.chores
        assert app_module._jobs()._retention_due > time.monotonic(), "it ran at start"
    finally:
        app_module._stop_inbox()


# --- Z6.5 ------------------------------------------------------------------------


def test_approval_record_stores_the_account_and_the_time_of_approval_and_release(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(inbox_module.getpass, "getuser", lambda: "clerk-a")
    queue.desk.inbox.correct(queue.entry.id, Correction(values={"document_number": "7"}))
    failed = queue.jobs.approve(queue.entry.id)

    monkeypatch.setattr(inbox_module.getpass, "getuser", lambda: "clerk-b")
    monkeypatch.setitem(jobs_module.WRITERS, "test_target", lambda *_: None)
    queue.jobs.release(failed.id)
    queue.desk.inbox.stop()
    queue.desk.restart()
    job = Jobs(queue.desk.inbox).get(failed.id)

    assert [(t.to_state, t.reason, t.account) for t in job.transitions] == [
        ("pending", "approved", "clerk-a"),
        ("failed", "target-without-writer", None),
        ("pending", "released", "clerk-b"),
        ("handed_over", "job-file-written", None),
    ]
    for transition in job.transitions:
        assert datetime.now(UTC) - datetime.fromisoformat(transition.at) < timedelta(minutes=1)
    corrections = queue.desk.inbox.db.query("SELECT account, corrected_at FROM inbox_correction")
    assert [row["account"] for row in corrections] == ["clerk-a"]


def test_approval_record_is_the_account_the_operating_system_reports(
    queue: Queue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOGNAME", "from-the-system")

    job = queue.jobs.approve(queue.entry.id)

    assert job.transitions[0].account == "from-the-system"


# --- Z6.6 ------------------------------------------------------------------------


def test_no_content_in_logs_error_messages_or_any_file_but_the_job_file_and_the_database(
    desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    logging_setup.configure(desk.root / "logs", development=True)
    try:
        problems, known, job = _path_with_every_refusal(desk, corpus, monkeypatch)
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers[:], root.level = handlers, level
        logging.getLogger("substrakt").setLevel(logging.NOTSET)

    log_text = (desk.root / "logs" / "substrakt.log").read_text(encoding="utf-8")
    assert "Inbox entry" in log_text and "could not be handed over" in log_text
    job_file = desk.folder / OUTPUT / f"{job.id}.json"
    scans = set(desk.folder.rglob("*"))
    elsewhere = [
        file
        for file in desk.root.rglob("*")
        if file.is_file() and file not in scans and file != job_file
        and file.parent != desk.database.parent
    ]
    assert desk.root / "logs" / "substrakt.log" in elsewhere

    def holders(texts: dict[str, str]) -> list[tuple[str, str]]:
        return [(name, value) for name, text in texts.items() for value in known if value in text]

    assert holders({str(file): file.read_text("utf-8", "replace") for file in elsewhere}) == []
    assert holders({"problems": json.dumps(problems, ensure_ascii=False)}) == []
    assert len(problems) == 5
    in_job_file = job_file.read_text(encoding="utf-8")
    in_database = database_bytes(desk).decode("utf-8", "replace")
    assert MARKED in in_job_file and MARKED in in_database
    assert BY_HAND in in_job_file and BY_HAND in in_database
    assert all(value in in_database for value in known)


def _path_with_every_refusal(
    desk: Desk, corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[dict], set[str], jobs_module.Job]:
    """Drive the whole path and collect every problem a person could be shown."""
    jobs, _, _ = shipped_queue(desk, monkeypatch)
    file = "policy_a_1.pdf"
    truth = truth_of(corpus, file)
    put(desk, f"Kunde/{file}", (corpus / "insurance" / file).read_bytes())
    put(desk, "Kunde/broken.pdf", b"%PDF-1.4\nnot a document\n")
    desk.settle()
    entry = desk.entries()[f"Kunde/{file}"]
    problems: list[dict] = []

    def refused(action) -> None:
        with pytest.raises(SubstraktError) as raised:
            action()
        problems.append(raised.value.as_problem())

    refused(lambda: jobs.approve(entry.id))  # type: ignore[attr-defined]
    refused(lambda: desk.inbox.correct(entry.id, Correction(values={"no_such": MARKED})))  # type: ignore[attr-defined]
    desk.inbox.correct(entry.id, Correction(values={"start_date": MARKED}))  # type: ignore[attr-defined]
    refused(lambda: jobs.approve(entry.id))  # type: ignore[attr-defined]
    refused(lambda: jobs.approve(desk.entries()["Kunde/broken.pdf"].id))  # type: ignore[attr-defined]
    settle_values(desk, desk.inbox.entry(entry.id), truth)  # type: ignore[attr-defined]
    desk.inbox.correct(entry.id, Correction(values={"policyholder": MARKED}))  # type: ignore[attr-defined]
    desk.inbox.correct(entry.id, Correction(values={"insurer": BY_HAND}))  # type: ignore[attr-defined]

    # The first hand-over fails while writing, which is logged with its traceback.
    fsync = jobs_module.os.fsync
    monkeypatch.setattr(jobs_module.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("full")))
    failed = jobs.approve(entry.id)  # type: ignore[attr-defined]
    monkeypatch.setattr(jobs_module.os, "fsync", fsync)
    refused(lambda: jobs.move(failed.id, "done", "test"))
    job = jobs.release(failed.id)
    assert job.state == "handed_over"

    known = {str(value) for value in truth["values"].values() if isinstance(value, str)}
    known |= {MARKED, BY_HAND, *(value.value for value in desk.inbox.entry(entry.id).values if value.value)}  # type: ignore[attr-defined]
    return problems, known, job
