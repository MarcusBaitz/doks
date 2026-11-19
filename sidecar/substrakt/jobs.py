"""Approval and the job queue.

Reading ends in an inbox entry, review in an approval by a person, and an
approval creates exactly one job. A job carries the approved values under the
names of the target and moves only along the transitions named below; every
transition is stored with its time and reason. Nothing reaches the hand-over
folder without a job, and the writer of a hand-over format reads only jobs.

The hand-over is a folder inside the read roots, not a connection. A job is
written there as one JSON file through a temporary name and a rename, so a
reader never sees half a file. Which format follows is chosen by the target
of the profile; a target without a writer ends as a failed job with a reason
instead of being written in some other format.

The format of the job file is documented in ``docs/job-format.md``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from substrakt import pipeline_profiles, yaml_model
from substrakt.errors import (
    ApprovalRefused,
    ImportReasonMissing,
    JobTransitionInvalid,
    JobUnknown,
)
from substrakt.extraction.fields import ExtractionResult
from substrakt.inbox import Inbox, InboxEntry, account, now
from substrakt.pipeline_profiles import ExpectedValues, PipelineProfile

log = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).parent / "job.schema.json"

State = Literal["pending", "handed_over", "done", "failed"]

# Every transition a job may take. A failed job stays failed until a person
# releases it; a job that is done never moves again.
TRANSITIONS: dict[State, frozenset[State]] = {
    "pending": frozenset({"handed_over", "failed"}),
    "handed_over": frozenset({"done", "failed"}),
    "failed": frozenset({"pending"}),
    "done": frozenset(),
}

# Reasons stored with a transition; stable keys, not prose.
REASON_APPROVED = "approved"
REASON_WRITTEN = "job-file-written"
REASON_NO_WRITER = "target-without-writer"
REASON_WRITE_FAILED = "handover-write-failed"
# A foreign file in the hand-over folder has the name the job file would get.
REASON_NAME_TAKEN = "hand-over-name-taken"
REASON_RELEASED = "released"
# The file a job was written into went with a deleted contract of the same file.
REASON_FILE_REMOVED = "hand-over-file-removed"
# A person reports what the import of a hand-over did; a failure carries
# the person's words after the key.
REASON_IMPORTED = "import-confirmed"
REASON_IMPORT_FAILED = "import-failed"

# The retention period is applied at start and then once in this many seconds.
RETENTION_INTERVAL = 24 * 60 * 60


class JobValue(BaseModel):
    """One approved value: as it stands on the paper, and as it was read."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="The value as written in the document or entered by a person")
    normalized: str | float | bool | None = Field(
        description="ISO date, number or cleaned text; null when the value has no such form"
    )


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Where the scanned file lies; the file itself is not copied")
    sha256: str = Field(description="SHA-256 of the file as it was read")


class PageRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first: int = Field(ge=1, description="First page of the document in the file, counted from 1")
    last: int = Field(ge=1, description="Last page of the document in the file")


class JobFile(BaseModel):
    """One approved document, as it is written into the hand-over folder."""

    model_config = ConfigDict(extra="forbid")

    # Raised when a key is added, removed or changes its meaning.
    version: Literal[1] = Field(default=1, description="Version of this format")
    id: str = Field(description="Unique id of the job; the file is named <id>.json")
    idempotency_key: str = Field(
        description="SHA-256 over file hash, kind and values; equal for the same approved content"
    )
    approved_at: str = Field(description="Time of the approval, ISO 8601 with offset")
    profile: str = Field(description="Name of the pipeline profile the document was read with")
    target: str = Field(description="Target of that profile; it chooses the hand-over format")
    kind: str = Field(description="Document kind")
    customer: str | None = Field(description="Customer folder the file lay in, or null")
    file: SourceFile
    pages: PageRange
    values: dict[str, JobValue] = Field(description="Approved values by their name in the target")


class Transition(BaseModel):
    # None for the creation of the job.
    from_state: State | None
    to_state: State
    reason: str
    at: str
    # The person who approved or released; None where the application moved the job.
    account: str | None


class Job(BaseModel):
    id: str
    entry_id: int
    state: State
    file: JobFile
    # Where the job file was written; None until it was handed over.
    handover_path: str | None
    transitions: list[Transition]


# Writers of hand-over formats by target name. A writer receives the job and
# the hand-over folder after the job file was written. The first one arrives
# with the GDV writer of milestone M5; until then every job ends as failed
# with REASON_NO_WRITER.
Writer = Callable[[JobFile, Path], None]
WRITERS: dict[str, Writer] = {}


def idempotency_key(sha256: str, kind: str, values: dict[str, JobValue]) -> str:
    """Hash file, kind and values in a form that does not depend on key order."""
    content = [sha256, kind, {name: value.model_dump() for name, value in values.items()}]
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def approved_values(results: list[ExtractionResult], expected: ExpectedValues) -> dict[str, JobValue]:
    """Return the values under their target names, or refuse the approval.

    Every required value must be settled. An optional value goes along when it
    was read unambiguously and is left out otherwise.
    """
    read = {result.field: result for result in results}
    required = expected.values
    open_values = [name for name in required if name not in read or not read[name].value]
    unclear = [
        name for name in required if name not in open_values and not read[name].grounded
    ]
    if open_values or unclear:
        # Names only: the values themselves do not belong in an error message.
        raise ApprovalRefused(
            "A required value is open or not unambiguous.",
            reason="values-not-settled",
            open=open_values,
            unclear=unclear,
        )
    settled = required | {
        name: target_name
        for name, target_name in expected.optional.items()
        if name in read and read[name].value and read[name].grounded
    }
    return {
        target_name: JobValue(text=read[name].value or "", normalized=read[name].normalized)
        for name, target_name in settled.items()
    }


def job_file(entry: InboxEntry, profile: PipelineProfile) -> JobFile:
    """Build the job of an entry that a person approves, or refuse the approval."""
    if entry.state != "waiting":
        raise ApprovalRefused("The entry does not wait for review.", reason="entry-not-waiting")
    if entry.kind is None or entry.kind not in profile.kinds or entry.page_count is None:
        raise ApprovalRefused("The entry has no kind of its profile.", reason="kind-missing")
    if entry.possible_duplicate_of is not None and entry.duplicate_decision is None:
        raise ApprovalRefused(
            "A person must decide whether this is the same document as another entry.",
            reason="possible-duplicate-undecided",
            other=entry.possible_duplicate_of,
        )
    values = approved_values(entry.values, profile.kinds[entry.kind])
    return JobFile(
        id=uuid.uuid4().hex,
        idempotency_key=idempotency_key(entry.sha256, entry.kind, values),
        approved_at=now(),
        profile=profile.name,
        target=profile.target,
        kind=entry.kind,
        customer=entry.customer,
        file=SourceFile(path=entry.file_path, sha256=entry.sha256),
        # Splitting a scan into several documents is outside the pilot.
        pages=PageRange(first=1, last=entry.page_count),
        values=values,
    )


# The name of a job file while it is written. A crash can leave one behind,
# with values in it and no job row that points to it.
TEMPORARY = re.compile(r"\.[0-9a-f]{32}\.json\.tmp")


def write_job_file(folder: Path, file: JobFile) -> Path:
    """Write the job as ``<id>.json``; the name appears only with the whole content.

    A file that already has either name is foreign, since every way a job
    leaves removes its own file: it keeps its bytes and FileExistsError
    makes the job fail.
    """
    target = folder / f"{file.id}.json"
    temporary = folder / f".{file.id}.json.tmp"
    if target.exists() or target.is_symlink():
        raise FileExistsError("The name of the job file is taken.")
    # "x": a foreign file under the temporary name is neither emptied nor removed.
    handle = temporary.open("x", encoding="utf-8")
    try:
        with handle:
            handle.write(file.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


class Jobs:
    """The job queue on the database of an inbox."""

    def __init__(
        self,
        inbox: Inbox,
        check: Callable[[JobFile], None] = lambda file: None,
        in_runs: Callable[[JobFile], bool] = lambda file: False,
    ) -> None:
        self._inbox = inbox
        # Both come from substrakt/hand_over.py: what the hand-over format
        # refuses at approval, and which jobs wait for a run a person starts.
        self._check, self._in_runs = check, in_runs
        self._db = inbox.db
        # One hand-over at a time, so that no job file is written twice.
        # Shared with the hand-over runs: a run and a deletion must not overlap.
        self.handover_lock = threading.Lock()
        # Monotonic time at which the retention period is applied next.
        self._retention_due = 0.0

    def all(self) -> list[Job]:
        return [self._job(row) for row in self._db.query("SELECT * FROM job ORDER BY rowid")]

    def get(self, job_id: str) -> Job:
        rows = self._db.query("SELECT * FROM job WHERE id = ?", job_id)
        if not rows:
            raise JobUnknown("No such job.")
        return self._job(rows[0])

    def _job(self, row: sqlite3.Row) -> Job:
        transitions = self._db.query(
            "SELECT * FROM job_transition WHERE job_id = ? ORDER BY id", row["id"]
        )
        return Job(
            id=row["id"],
            entry_id=row["entry_id"],
            state=row["state"],
            file=JobFile.model_validate_json(row["file_json"]),
            handover_path=row["handover_path"],
            transitions=[Transition(**dict(transition)) for transition in transitions],
        )

    # --- Approval ----------------------------------------------------------

    def approve(self, entry_id: int) -> Job:
        """Create the one job of an entry; a second approval returns the first job."""
        entry = self._inbox.entry(entry_id)
        existing = self._db.query("SELECT id FROM job WHERE entry_id = ?", entry_id)
        if existing:
            return self.get(existing[0]["id"])
        file = job_file(entry, pipeline_profiles.load(entry.profile))
        self._check(file)
        job_id = self._store(entry_id, file)
        self.hand_over_pending()
        return self.get(job_id)

    def _store(self, entry_id: int, file: JobFile) -> str:
        """Store job, first transition and entry state together; return the id of the job."""
        with self._db.transaction() as conn:
            same = conn.execute(
                "SELECT id, entry_id FROM job WHERE idempotency_key = ?", (file.idempotency_key,)
            ).fetchone()
            if same is None:
                # The condition is part of the write: a decision "same document"
                # or a deletion between the look of the approval and this line
                # must not end as a job for an entry that no longer waits. It
                # comes before the job, which could not reference a deleted entry.
                approved = conn.execute(
                    "UPDATE inbox_entry SET state = 'approved' WHERE id = ? AND state = 'waiting'",
                    (entry_id,),
                ).rowcount
                if not approved:
                    raise ApprovalRefused(
                        "The entry does not wait for review.", reason="entry-not-waiting"
                    )
                conn.execute(
                    "INSERT INTO job (id, entry_id, idempotency_key, state, file_json) "
                    "VALUES (?, ?, ?, 'pending', ?)",
                    (file.id, entry_id, file.idempotency_key, file.model_dump_json()),
                )
                conn.execute(
                    "INSERT INTO job_transition (job_id, to_state, reason, at, account) "
                    "VALUES (?, 'pending', ?, ?, ?)",
                    (file.id, REASON_APPROVED, file.approved_at, account()),
                )
                return file.id
            if same["entry_id"] != entry_id:
                # The same content was approved before under another entry.
                conn.execute(
                    "UPDATE inbox_entry SET state = 'duplicate', duplicate_of = ? "
                    "WHERE id = ? AND state = 'waiting'",
                    (same["entry_id"], entry_id),
                )
            return same["id"]

    # --- States ------------------------------------------------------------

    def move(self, job_id: str, to: State, reason: str, by: str | None = None) -> Job:
        """Take one of the named transitions and store it; reject every other.

        ``by`` is the account of the person who asked for it, if a person did.
        """
        with self._db.transaction() as conn:
            row = conn.execute("SELECT state FROM job WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise JobUnknown("No such job.")
            if to not in TRANSITIONS[row["state"]]:
                raise JobTransitionInvalid(
                    f"A job in state {row['state']} cannot change to {to}.",
                    from_state=row["state"],
                    to_state=to,
                )
            conn.execute("UPDATE job SET state = ? WHERE id = ?", (to, job_id))
            conn.execute(
                "INSERT INTO job_transition (job_id, from_state, to_state, reason, at, account) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, row["state"], to, reason, now(), by),
            )
        return self.get(job_id)

    def release(self, job_id: str) -> Job:
        """A person releases a failed job again; it is handed over once more."""
        self.move(job_id, "pending", REASON_RELEASED, by=account())
        self.hand_over_pending()
        return self.get(job_id)

    def report_import(self, customer: str, imported: bool, reason: str = "") -> list[Job]:
        """A person reports what importing the hand-over of one customer did.

        Only the jobs of runs a person started and only those handed over
        are concerned. Imported, they are done. Failed, they fail with the
        person's reason, and their files go: a released job is written into
        a new file, and the old one must not be imported later or stay with
        contracts that no job points to.
        """
        reason = " ".join(reason.split())
        if not imported and not reason:
            raise ImportReasonMissing("A failed import needs a reason.")
        by = account()
        with self.handover_lock:
            rows = self._db.query(
                "SELECT id, handover_path, format_file FROM job "
                "WHERE state = 'handed_over' ORDER BY rowid"
            )
            handed = [
                row for row in rows
                if (file := self.get(row["id"]).file).customer == customer and self._in_runs(file)
            ]
            for row in handed:
                if imported:
                    self.move(row["id"], "done", REASON_IMPORTED, by=by)
                    continue
                for path in filter(None, (row["handover_path"], row["format_file"])):
                    Path(path).unlink(missing_ok=True)
                self._db.write(
                    "UPDATE job SET format_file = NULL, handover_path = NULL WHERE id = ?",
                    row["id"],
                )
                self.move(row["id"], "failed", f"{REASON_IMPORT_FAILED}: {reason}", by=by)
        return [self.get(row["id"]) for row in handed]

    # --- Deleting ----------------------------------------------------------

    def delete_entry(self, entry_id: int, delete_file: bool = False) -> None:
        """Delete an entry with its values, corrections, job and job file.

        The scanned file stays unless ``delete_file`` asks for it to go. Files
        are removed first: if one cannot be removed, the entry stays and the
        person sees the failure instead of a record that is silently wrong.
        """
        entry = self._inbox.entry(entry_id)
        scan = self._inbox.scan_to_delete(entry) if delete_file else None
        # Not while a hand-over writes the very file that is to go; what the
        # job points to is read only after a running hand-over has finished.
        with self.handover_lock:
            written = self._db.query(
                "SELECT handover_path, format_file FROM job WHERE entry_id = ?", entry_id
            )
            if scan is not None:
                scan.unlink()
            for row in written:
                # Only the stored paths; a file of the same name elsewhere is not ours.
                for path in filter(None, (row["handover_path"], row["format_file"])):
                    Path(path).unlink(missing_ok=True)
                if row["format_file"]:
                    self._fail_others_of(row["format_file"], entry_id)
            self._inbox.delete(entry, keep_marker=scan is None)

    def _fail_others_of(self, format_file: str, entry_id: int) -> None:
        """The other jobs of a removed file fail, so that a person hands them over again.

        A contract cannot be cut out of a written file, so the file goes as a
        whole, and their job files go with it: nothing of a removed hand-over
        stays in the folder. Jobs that are done keep their state.
        """
        others = self._db.query(
            "SELECT id, state, handover_path FROM job WHERE format_file = ? AND entry_id != ?",
            format_file,
            entry_id,
        )
        self._db.write(
            "UPDATE job SET format_file = NULL, handover_path = NULL WHERE format_file = ?",
            format_file,
        )
        for row in others:
            if row["handover_path"]:
                Path(row["handover_path"]).unlink(missing_ok=True)
            if row["state"] == "handed_over":
                self.move(row["id"], "failed", REASON_FILE_REMOVED)

    def apply_retention(self) -> int:
        """Delete every entry whose job has been done for longer than the retention period."""
        limit = datetime.now(UTC) - timedelta(days=self._inbox.retention_days())
        done = self._db.query(
            "SELECT job.entry_id, MAX(t.at) AS at FROM job "
            "JOIN job_transition t ON t.job_id = job.id AND t.to_state = 'done' "
            "WHERE job.state = 'done' GROUP BY job.id"
        )
        old = [row["entry_id"] for row in done if datetime.fromisoformat(row["at"]) < limit]
        for entry_id in old:
            self.delete_entry(entry_id)
        return len(old)

    def keep_retention(self) -> None:
        """Apply the retention period at the first call and then once a day."""
        if time.monotonic() >= self._retention_due:
            self._retention_due = time.monotonic() + RETENTION_INTERVAL
            deleted = self.apply_retention()
            if deleted:
                log.info("Retention: %d entries deleted", deleted)

    # --- Hand-over ---------------------------------------------------------

    def hand_over_pending(self) -> None:
        """Hand over every pending job; without the output folder they wait."""
        folder = self._inbox.handover_folder()
        if folder is None:
            return
        with self.handover_lock:
            for row in self._db.query("SELECT id FROM job WHERE state = 'pending' ORDER BY rowid"):
                self._hand_over(self.get(row["id"]), folder)

    def _hand_over(self, job: Job, folder: Path) -> None:
        if self._in_runs(job.file):
            return
        writer = WRITERS.get(job.file.target)
        if writer is None:
            self.move(job.id, "failed", REASON_NO_WRITER)
            return
        try:
            written = write_job_file(folder, job.file)
            writer(job.file, folder)
        except FileExistsError:
            self.move(job.id, "failed", REASON_NAME_TAKEN)
            return
        except OSError:
            # The path stays in the local log; the job carries only the reason.
            log.exception("Job %s could not be handed over", job.id)
            self.move(job.id, "failed", REASON_WRITE_FAILED)
            return
        self._db.write("UPDATE job SET handover_path = ? WHERE id = ?", str(written), job.id)
        self.move(job.id, "handed_over", REASON_WRITTEN)


def schema_text() -> str:
    """Generate the schema of the job file from the authoritative Pydantic model."""
    return yaml_model.schema_text(JobFile)


def write_schema(target: Path = SCHEMA_FILE) -> None:
    target.write_text(schema_text(), encoding="utf-8")


def schema_is_current(file: Path = SCHEMA_FILE) -> bool:
    return file.is_file() and file.read_text(encoding="utf-8") == schema_text()
