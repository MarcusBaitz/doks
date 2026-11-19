"""Watched folder and durable inbox.

The clerk chooses one folder. A background thread polls it with the standard
library, reads every document once its size and modification time have stopped
changing, and keeps what it found in SQLite so that a restart reads nothing
twice. Polling instead of file events is deliberate: scanner shares deliver
events unreliably, and a watcher library would be a new dependency. Nothing is
read while the application is closed.

An entry stores state, file path, SHA-256, customer, profile, document kind,
values with their locations and step timings. It never stores document text or
a page image; the file stays where the scanner put it. A file is known by its
path and its hash. Content that was already read is recorded as a duplicate
that points to the first entry and is not read again.

Which folder level names the customer comes from the active pipeline profile,
not from this module.

What a person corrects, the kind or single values, is stored with the entry;
the table inbox_correction keeps what stood there before.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pypdfium2
from PIL import Image
from pydantic import BaseModel

from substrakt import document_kinds, pipeline_profiles, yaml_model
from substrakt.comparison import comparison_key
from substrakt.config import MAX_INBOX_PAGES
from substrakt.db.session import Session
from substrakt.document_kinds import DocumentKind
from substrakt.errors import (
    CorrectionRefused,
    DocumentTooManyPages,
    FileChanged,
    FileNameUnreadable,
    FileNotFound,
    InboxEntryUnknown,
    OutputNameTaken,
    PathNotAllowed,
    ReadingInterrupted,
    SubstraktError,
)
from substrakt.extraction.fields import ExtractionResult, FieldSpec, manual_result
from substrakt.extraction.fields import extract as run_extraction
from substrakt.model import Document
from substrakt.parsers import ENDUNGEN, PDFIUM_LOCK, detect_format
from substrakt.pipeline_profiles import PipelineProfile
from substrakt.store import DocumentStore, file_hash

log = logging.getLogger(__name__)

# Seconds between two looks at the folder; a file is read on the second look
# that finds it unchanged.
POLL_INTERVAL = 2.0

# Scanners deliver PDFs and images; spreadsheets in the folder are not scans.
WATCHED_SUFFIXES = {suffix for suffix, kind in ENDUNGEN.items() if kind in ("pdf", "image")}

SETTING_PROFILE = "pipeline_profile"
SETTING_RETENTION = "retention_days"

# Days an entry is kept after its job is done, unless the clerk sets another
# period. An assumption: the owner has not confirmed the figure yet.
DEFAULT_RETENTION_DAYS = 90

# The subfolder of the watched folder that receives job and hand-over files.
# It is never read: what Substrakt wrote is no scan and no customer. A folder
# name the clerk sees, not a target name, so it may stand here.
OUTPUT = "Ausgabe"

State = Literal["new", "waiting", "approved", "duplicate", "error"]


class InboxEntry(BaseModel):
    """One file that arrived in the watched folder."""

    id: int
    import_id: int
    state: State
    file_path: str
    # The folder the file arrived in, which matters for a duplicate.
    folder: str
    file_name: str
    sha256: str
    customer: str | None
    profile: str
    kind: str | None
    # None for an entry that was not read.
    page_count: int | None
    values: list[ExtractionResult]
    timings: dict[str, int]
    duplicate_of: int | None
    # Another entry with the same identifying values; a person decides.
    possible_duplicate_of: int | None
    duplicate_decision: Literal["same", "new"] | None
    problem_key: str | None
    later_arrival: bool
    arrived_at: str
    # Values a person changed since the kind was last set; a value confirmed as
    # read is stored as a correction too, but is not listed here.
    changed: list[str] = []


class InboxImport(BaseModel):
    """One chosen folder; its entries carry its id as ``import_id``."""

    id: int
    folder: str
    started_at: str
    # Set once every file found so far was read; later arrivals come after it.
    finished_at: str | None


class Correction(BaseModel):
    """What a person changed on an entry: the kind, values by name, or both."""

    kind: str | None = None
    values: dict[str, str] = {}
    # Values a person confirmed as read: they keep text and location.
    confirmed: list[str] = []


class ProfileChoice(BaseModel):
    name: str
    title: str


class InboxSettings(BaseModel):
    """What is watched, and with which profile."""

    folder: str | None
    # Where approved jobs are written as files: OUTPUT inside the folder.
    handover_folder: str | None
    profile: str | None
    profiles: list[ProfileChoice]
    watching: bool
    # Days an entry is kept after its job is done.
    retention_days: int


def now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def account() -> str:
    """The operating-system account the sidecar runs under, which is the clerk's."""
    return getpass.getuser()


def _milliseconds(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)


def _recognise(doc: Document, profile: PipelineProfile) -> DocumentKind | None:
    """Decide the document kind among those the profile reads.

    A document that is clearly none of them, or could be two, gets no kind
    and waits for a person.
    """
    kinds = {name: document_kinds.load(name) for name in profile.kinds}
    return document_kinds.recognise(doc, kinds)


# Name of the corrected value (None for the kind), what stood there, what stands there now.
Change = tuple[str | None, str | None, str]


def _extract(doc: Document, kind: DocumentKind) -> list[ExtractionResult]:
    return run_extraction(doc, kind.fields, kind=kind).results


def _values_json(results: list[ExtractionResult]) -> str:
    return json.dumps([result.model_dump() for result in results], ensure_ascii=False)


def _spec(specs: dict[str, FieldSpec], name: str) -> FieldSpec:
    if name not in specs:
        raise CorrectionRefused("The kind has no value of that name.", reason="value-unknown")
    return specs[name]


def _with_values(
    kind: DocumentKind,
    results: list[ExtractionResult],
    values: dict[str, str],
    changes: list[Change],
) -> list[ExtractionResult]:
    """Replace the named values by what a person entered and note each change."""
    specs = {field.name: field for field in kind.fields}
    by_name = {result.field: result for result in results}
    for name, raw in values.items():
        value = raw.strip()
        spec = _spec(specs, name)
        if not value:
            raise CorrectionRefused("A corrected value must not be empty.", reason="value-empty")
        changes.append((name, by_name[name].value if name in by_name else None, value))
        by_name[name] = manual_result(spec, value)
    return list(by_name.values())


def _confirmed(
    kind: DocumentKind,
    results: list[ExtractionResult],
    names: list[str],
    changes: list[Change],
) -> list[ExtractionResult]:
    """Settle the named values as read; text, location and source stay."""
    specs = {field.name: field for field in kind.fields}
    by_name = {result.field: result for result in results}
    for name in names:
        spec = _spec(specs, name)
        read = by_name.get(name)
        if read is None or not read.value:
            raise CorrectionRefused(
                "Only a value that was read can be confirmed.", reason="value-empty"
            )
        # Settled as a typed value would be: a text that does not fit its type stays unclear.
        grounded = manual_result(spec, read.value).grounded
        by_name[name] = read.model_copy(update={"grounded": grounded})
        changes.append((name, read.value, read.value))
    return list(by_name.values())


def _entry(row: sqlite3.Row, changed: list[str]) -> InboxEntry:
    # Folder and name of an unreadable path are shown without its bytes.
    path = Path(row["file_path"].rpartition(_BYTES)[0] or row["file_path"])
    return InboxEntry(
        id=row["id"],
        import_id=row["import_id"],
        state=row["state"],
        file_path=row["file_path"],
        folder=str(path.parent),
        file_name=path.name,
        sha256=row["sha256"],
        customer=row["customer"],
        profile=row["profile"],
        kind=row["kind"],
        page_count=row["page_count"],
        values=json.loads(row["values_json"]),
        timings=json.loads(row["timings_json"]),
        duplicate_of=row["duplicate_of"],
        possible_duplicate_of=row["possible_duplicate_of"],
        duplicate_decision=row["duplicate_decision"],
        problem_key=row["problem_key"],
        later_arrival=bool(row["later_arrival"]),
        arrived_at=row["arrived_at"],
        changed=changed,
    )


def _storable(text: str) -> str:
    """A path or folder name as text the database can hold.

    A name that is no valid UTF-8 reaches Python with surrogates, which SQLite
    refuses to bind. Each such character becomes “?”: the entry then names
    the folder and what is readable of the name, and a person finds the file.
    """
    return text.encode("utf-8", "replace").decode("utf-8")


# No path of a file contains this in its middle or at its end.
_BYTES = "//"


def _stored_path(file: Path) -> str:
    """The path of a file as the database holds it, one text per file.

    The readable form alone would give two files one path: two names that
    differ only in unreadable bytes, or an unreadable name and a valid one
    with “?” in that place. A deletion would then reach the wrong file. The
    bytes of the path follow as hex, so the text is unique and leads back to
    the file.
    """
    text = str(file)
    shown = _storable(text)
    if shown == text:
        return text
    return shown + _BYTES + text.encode("utf-8", "surrogatepass").hex()


def _real_path(stored: str) -> Path:
    """The file a stored path stands for."""
    shown, mark, raw = stored.rpartition(_BYTES)
    if mark and shown:
        return Path(bytes.fromhex(raw).decode("utf-8", "surrogatepass"))
    return Path(stored)


def _page_count(path: Path) -> int:
    """Pages of a PDF or frames of an image, without reading their content.

    A file that cannot be opened counts as none; the parser then reports what
    is wrong with it under its own key.
    """
    try:
        if detect_format(path) == "pdf":
            with PDFIUM_LOCK:
                pdf = pypdfium2.PdfDocument(path)
                try:
                    return len(pdf)
                finally:
                    pdf.close()
        with Image.open(path) as image:
            return getattr(image, "n_frames", 1)
    except Exception:
        return 0


class Inbox:
    """The watched folder, its poll loop and the persisted entries."""

    def __init__(
        self, database: Path, store: DocumentStore, roots: list[Path], interval: float = POLL_INTERVAL
    ) -> None:
        # Shared with the job queue, which approves entries of this inbox.
        self.db = Session(database)
        self._poll_lock = threading.Lock()
        self._store = store
        self._roots = roots
        self._interval = interval
        # File revision at the last look, and since when it has not changed.
        self._seen: dict[Path, tuple[tuple[int, int], float]] = {}
        # Revisions already taken in this run; avoids hashing on every poll.
        self._taken: dict[Path, tuple[int, int]] = {}
        # Further work of the loop, run after every look at the folder.
        self.chores: list[Callable[[], None]] = []
        self._stop = threading.Event()
        # The entry of the file the loop is taking, once it is written.
        self._taking: int | None = None
        self._thread: threading.Thread | None = None
        # An entry still new was being read when the application ended. Reading
        # it again could end the application again, at every start.
        with self.db.transaction() as conn:
            interrupted = conn.execute(
                "UPDATE inbox_entry SET state = 'error', problem_key = ? WHERE state = 'new'",
                (ReadingInterrupted.key,),
            ).rowcount
        if interrupted:
            log.error("Inbox: an entry was left unfinished by the last run and is not read again")

    # --- Database ----------------------------------------------------------

    def _current_import(self) -> sqlite3.Row | None:
        rows = self.db.query("SELECT * FROM inbox_import ORDER BY id DESC LIMIT 1")
        return rows[0] if rows else None

    def _changed(self, entry_id: int | None = None) -> dict[int, list[str]]:
        """Names of values a person changed, per entry.

        A new kind reads the file again, so only corrections after the last
        change of kind count.
        """
        changed: dict[int, list[str]] = {}
        for row in self.db.query(
            "SELECT DISTINCT c.entry_id, c.value_name FROM inbox_correction c "
            "WHERE (? IS NULL OR c.entry_id = ?) AND c.value_name IS NOT NULL "
            "AND c.before IS NOT c.after AND c.id > COALESCE((SELECT MAX(k.id) "
            "FROM inbox_correction k WHERE k.entry_id = c.entry_id AND k.value_name IS NULL), 0) "
            "ORDER BY c.id",
            entry_id,
            entry_id,
        ):
            changed.setdefault(row["entry_id"], []).append(row["value_name"])
        return changed

    def entries(self) -> list[InboxEntry]:
        changed = self._changed()
        return [
            _entry(row, changed.get(row["id"], []))
            for row in self.db.query("SELECT * FROM inbox_entry ORDER BY id")
        ]

    def imports(self) -> list[InboxImport]:
        return [
            InboxImport(**dict(row)) for row in self.db.query("SELECT * FROM inbox_import ORDER BY id")
        ]

    def entry(self, entry_id: int) -> InboxEntry:
        rows = self.db.query("SELECT * FROM inbox_entry WHERE id = ?", entry_id)
        if not rows:
            raise InboxEntryUnknown(f"No inbox entry {entry_id}.")
        return _entry(rows[0], self._changed(entry_id).get(entry_id, []))

    # --- Settings ----------------------------------------------------------

    def _setting(self, key: str) -> str | None:
        rows = self.db.query("SELECT value FROM app_setting WHERE key = ?", key)
        return rows[0]["value"] if rows else None

    def _keep_setting(self, key: str, value: str) -> None:
        self.db.write(
            "INSERT INTO app_setting (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            key,
            value,
        )

    def _folder_in_roots(self, raw: str) -> Path:
        """Resolve a folder a person chose and refuse one outside the read roots."""
        try:
            folder = Path(raw).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise FileNotFound("The folder cannot be resolved.") from exc
        if not folder.is_dir():
            raise FileNotFound("The chosen path is not a folder.")
        # Without read roots nothing limits the folder, so none is accepted.
        if not self._roots:
            raise PathNotAllowed("No directory is allowed for this session.")
        self._store.check_roots(folder)
        return folder

    def choose_profile(self, name: str) -> None:
        """Make a profile the active one; entries already read keep theirs."""
        pipeline_profiles.load(name)
        self._keep_setting(SETTING_PROFILE, name)

    def choose_folder(self, raw: str) -> None:
        """Start an import of a folder inside the read roots, with OUTPUT inside it."""
        folder = self._folder_in_roots(raw)
        pipeline_profiles.active(self._setting(SETTING_PROFILE))
        self._make_output(folder)

        current = self._current_import()
        if current is not None and Path(current["folder"]) == folder:
            return
        self.db.write(
            "INSERT INTO inbox_import (folder, started_at) VALUES (?, ?)", str(folder), now()
        )

    def _make_output(self, folder: Path) -> None:
        """Create OUTPUT in the folder, or use the one there; never touch a foreign file.

        A link is refused, because files written through it would land where
        the read roots do not reach or where nobody looks for them.
        """
        output = folder / OUTPUT
        if output.is_symlink():
            raise PathNotAllowed("The output folder is a link.")
        if output.exists() and not output.is_dir():
            raise OutputNameTaken("A file has the name of the output folder.")
        output.mkdir(exist_ok=True)
        self._store.check_roots(output.resolve(strict=True))

    def handover_folder(self) -> Path | None:
        """OUTPUT inside the watched folder; None without a folder or when it is no plain folder."""
        current = self._current_import()
        if current is None:
            return None
        output = Path(current["folder"]) / OUTPUT
        return output if output.is_dir() and not output.is_symlink() else None

    def choose_retention(self, days: int) -> None:
        self._keep_setting(SETTING_RETENTION, str(days))

    def retention_days(self) -> int:
        return int(self._setting(SETTING_RETENTION) or DEFAULT_RETENTION_DAYS)

    def settings(self) -> InboxSettings:
        current = self._current_import()
        titles = pipeline_profiles.titles()
        chosen = self._setting(SETTING_PROFILE)
        if chosen is None and len(titles) == 1:
            chosen = next(iter(titles))
        return InboxSettings(
            folder=current["folder"] if current is not None else None,
            handover_folder=(
                str(Path(current["folder"]) / OUTPUT) if current is not None else None
            ),
            profile=chosen,
            profiles=[ProfileChoice(name=name, title=title) for name, title in titles.items()],
            watching=current is not None and self._thread is not None and self._thread.is_alive(),
            retention_days=self.retention_days(),
        )

    # --- Loop --------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="inbox", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.db.close()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            for work in (self.poll, *self.chores):
                try:
                    work()
                except Exception:
                    # The loop must outlive any single failure; the next round retries.
                    log.exception("A step of the inbox loop failed")

    def poll(self) -> None:
        """Look at the folder once and take every file that has stopped changing."""
        with self._poll_lock:
            current = self._current_import()
            if current is None:
                return
            try:
                profile = pipeline_profiles.active(self._setting(SETTING_PROFILE))
            except SubstraktError as exc:
                log.error("Inbox paused, pipeline profile unusable: %s", exc.key)
                return
            folder = Path(current["folder"])
            settled = self._look(folder)
            self._forget_deleted(folder)
            for file in settled:
                revision = self._seen[file][0]
                if self._taken.get(file) != revision:
                    # Marked first: a file that fails here is not tried at every look.
                    self._taken[file] = revision
                    self._taking = None
                    try:
                        self._take(file, current, profile)
                    except Exception as exc:
                        # One file must never stop the loop for the files behind
                        # it. Neither name nor message: both may carry content.
                        log.error("Inbox: a file could not be taken (%s)", type(exc).__name__)
                        try:
                            self._record_failure(file, current, profile)
                        except Exception as again:
                            log.error(
                                "Inbox: the failure could not be recorded (%s)",
                                type(again).__name__,
                            )
            # The import is complete once no file is new or still changing.
            if len(settled) == len(self._seen) and current["finished_at"] is None:
                self.db.write(
                    "UPDATE inbox_import SET finished_at = ? WHERE id = ?", now(), current["id"]
                )

    def _look(self, folder: Path) -> list[Path]:
        """Remember each file's revision; return those unchanged since the last look."""
        # shortcut: a writer that pauses longer than one poll interval looks
        # finished, and the half file is read and ends as an entry in state
        # error or with wrong values; the complete file arrives as a new entry
        # because its hash differs. Upgrade to several unchanged looks or a
        # minimum age when a scanner at the customer writes that slowly.
        seen: dict[Path, tuple[tuple[int, int], float]] = {}
        settled = []
        for file in sorted(folder.rglob("*")):
            if file.suffix.lower() not in WATCHED_SUFFIXES:
                continue
            # casefold: on Windows and macOS „ausgabe“ is the same folder.
            if file.relative_to(folder).parts[0].casefold() == OUTPUT.casefold():
                continue
            try:
                if not file.is_file():
                    continue
                revision = yaml_model.state(file)
            except OSError:
                # Gone or unreadable between listing and looking; the next poll decides.
                continue
            before = self._seen.get(file)
            unchanged = before is not None and before[0] == revision
            seen[file] = (revision, before[1] if unchanged and before else time.perf_counter())
            if unchanged:
                settled.append(file)
        self._seen = seen
        return settled

    # --- Taking one file ---------------------------------------------------

    def _record_failure(self, file: Path, current: sqlite3.Row, profile: PipelineProfile) -> None:
        """A file that could not be taken becomes an entry a person sees.

        Without it the file would be passed over until the next start with
        nothing but a line in the log.
        """
        if self._taking is not None:
            # The entry exists; one that was still being read must not stay new.
            self.db.write(
                "UPDATE inbox_entry SET state = 'error', problem_key = ? "
                "WHERE id = ? AND state = 'new'",
                SubstraktError.key,
                self._taking,
            )
            return
        self.db.write(
            "INSERT INTO inbox_entry (import_id, state, problem_key, file_path, sha256, profile, "
            "later_arrival, arrived_at) VALUES (?, 'error', ?, ?, '', ?, ?, ?)",
            current["id"],
            SubstraktError.key,
            _stored_path(file),
            profile.name,
            current["finished_at"] is not None,
            now(),
        )

    def _take(self, file: Path, current: sqlite3.Row, profile: PipelineProfile) -> None:
        """Record a settled file: skip a known one, mark a duplicate, read a new one."""
        stored = _stored_path(file)
        problem = FileNameUnreadable.key if stored != str(file) else None
        # Roots and size are checked before a single byte is read: hashing
        # first would read a file of any size, and one a link reaches outside
        # the read roots, and leave the hash of that file in the database.
        sha, path = "", None
        try:
            path = self._store.validate_path(str(file))
            sha = file_hash(path)
        except SubstraktError as exc:
            problem = problem or exc.key
        except OSError:
            problem = problem or FileNotFound.key
        known = self.db.query(
            "SELECT id FROM inbox_entry WHERE file_path = ? AND sha256 = ?", stored, sha
        )
        if known:
            return
        if self.db.query(
            "SELECT 1 FROM inbox_deleted WHERE file_path = ? AND sha256 = ?", stored, sha
        ):
            return
        first = self.db.query(
            "SELECT id FROM inbox_entry WHERE sha256 = ? AND sha256 != '' "
            "AND state NOT IN ('duplicate', 'error') AND file_path != ? ORDER BY id LIMIT 1",
            sha,
            stored,
        )
        customer = profile.customer_of(file, Path(current["folder"]))
        entry_id = self.db.write(
            "INSERT INTO inbox_entry (import_id, state, file_path, sha256, customer, profile, "
            "duplicate_of, later_arrival, arrived_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            current["id"],
            "duplicate" if first else "new",
            stored,
            sha,
            _storable(customer) if customer else customer,
            profile.name,
            first[0]["id"] if first else None,
            current["finished_at"] is not None,
            now(),
        )
        self._taking = entry_id
        if problem or path is None:
            # A refused file is an entry a person sees, never a silent gap.
            self._fail(entry_id, problem or FileNotFound.key)
        elif not first:
            self._read(entry_id, file, path, sha, profile)

    def _read(
        self, entry_id: int, file: Path, path: Path, sha: str, profile: PipelineProfile
    ) -> None:
        """Parse and extract one file; any failure ends in state error, never in a retry."""
        started = time.perf_counter()
        timings = {"stable_ms": _milliseconds(self._seen[file][1])}
        try:
            pages = _page_count(path)
            if pages > MAX_INBOX_PAGES:
                raise DocumentTooManyPages(
                    f"The file has {pages} pages; the inbox reads up to {MAX_INBOX_PAGES}.",
                    pages=pages,
                    limit=MAX_INBOX_PAGES,
                )
            doc = self._store.parse(path, sha)
            timings["parse_ms"] = _milliseconds(started)
            extraction_started = time.perf_counter()
            kind = _recognise(doc, profile)
            results = _extract(doc, kind) if kind else []
            timings["extraction_ms"] = _milliseconds(extraction_started)
        except SubstraktError as exc:
            self._fail(entry_id, exc.key)
            return
        except Exception:
            # Details stay in the local log; the entry carries only the key.
            log.exception("Inbox entry %d could not be read", entry_id)
            self._fail(entry_id, SubstraktError.key)
            return
        timings["total_ms"] = _milliseconds(started)
        self.db.write(
            "UPDATE inbox_entry SET state = 'waiting', kind = ?, page_count = ?, "
            "values_json = ?, comparison_key = ?, timings_json = ? WHERE id = ?",
            kind.name if kind else None,
            doc.meta.page_count,
            _values_json(results),
            comparison_key(kind, results),
            json.dumps(timings),
            entry_id,
        )
        self._mark_possible_duplicate(entry_id)

    def _fail(self, entry_id: int, problem_key: str) -> None:
        log.info("Inbox entry %d: %s", entry_id, problem_key)
        self.db.write(
            "UPDATE inbox_entry SET state = 'error', problem_key = ? WHERE id = ?",
            problem_key,
            entry_id,
        )

    # --- Corrections -------------------------------------------------------

    def correct(self, entry_id: int, correction: Correction) -> InboxEntry:
        """Store what a person changed and keep what stood there before."""
        entry = self.entry(entry_id)
        if entry.state != "waiting":
            raise CorrectionRefused(
                "Only an entry that waits for review can be corrected.", reason="entry-not-waiting"
            )
        kind_name = correction.kind or entry.kind
        if kind_name is None or kind_name not in pipeline_profiles.load(entry.profile).kinds:
            raise CorrectionRefused(
                "The profile of this entry does not read that kind.", reason="kind-not-in-profile"
            )
        kind = document_kinds.load(kind_name)
        changes: list[Change] = []
        results = entry.values
        if kind_name != entry.kind:
            results = self._read_again(entry, kind)
            changes.append((None, entry.kind, kind_name))
        results = _with_values(kind, results, correction.values, changes)
        results = _confirmed(kind, results, correction.confirmed, changes)

        corrected_at = now()
        with self.db.transaction() as conn:
            # The conditions are part of the write: after an approval between
            # the look above and this line the entry would show another value
            # than its job, and after another correction this one would
            # overwrite it with a "before" that no longer stood there.
            changed = conn.execute(
                "UPDATE inbox_entry SET kind = ?, values_json = ?, comparison_key = ? "
                "WHERE id = ? AND state = 'waiting' AND kind IS ? AND values_json = ?",
                (
                    kind_name,
                    _values_json(results),
                    comparison_key(kind, results),
                    entry_id,
                    entry.kind,
                    _values_json(entry.values),
                ),
            ).rowcount
            if not changed:
                waiting = conn.execute(
                    "SELECT 1 FROM inbox_entry WHERE id = ? AND state = 'waiting'", (entry_id,)
                ).fetchone()
                if waiting:
                    raise CorrectionRefused(
                        "The entry changed since it was read.", reason="entry-changed"
                    )
                raise CorrectionRefused(
                    "Only an entry that waits for review can be corrected.",
                    reason="entry-not-waiting",
                )
            conn.executemany(
                "INSERT INTO inbox_correction "
                "(entry_id, value_name, before, after, corrected_at, account) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(entry_id, *change, corrected_at, account()) for change in changes],
            )
        # The correction may have made this entry equal to another one, or
        # ended that; the same holds for the entries that pointed to this one.
        self._mark_possible_duplicate(entry_id)
        self._mark_those_pointing_to(entry_id)
        return self.entry(entry_id)

    def _read_again(self, entry: InboxEntry, kind: DocumentKind) -> list[ExtractionResult]:
        """Read the file with the kind a person chose; the file must be the one that arrived."""
        path = self._store.validate_path(entry.file_path)
        if file_hash(path) != entry.sha256:
            raise FileChanged("The file changed since it was read.")
        return _extract(self._store.parse(path, entry.sha256), kind)

    # --- Possible duplicates -----------------------------------------------

    def _mark_possible_duplicate(self, entry_id: int) -> None:
        """Point the entry to another one with the same comparison key, or end the mark.

        The other entry has other file content; the same content is a certain
        duplicate and never gets here. An entry that points to this one is
        not its counterpart, or two entries would wait for each other.
        """
        with self.db.transaction() as conn:
            entry = conn.execute(
                "SELECT sha256, comparison_key, possible_duplicate_of FROM inbox_entry "
                "WHERE id = ?",
                (entry_id,),
            ).fetchone()
            other = conn.execute(
                "SELECT id FROM inbox_entry WHERE comparison_key = ? AND id != ? AND sha256 != ? "
                "AND state IN ('waiting', 'approved') "
                "AND possible_duplicate_of IS NOT ? ORDER BY id LIMIT 1",
                (entry["comparison_key"], entry_id, entry["sha256"], entry_id),
            ).fetchone()
            found = other["id"] if other and entry["comparison_key"] else None
            if found != entry["possible_duplicate_of"]:
                # A decision was about the other entry; it does not carry over.
                conn.execute(
                    "UPDATE inbox_entry SET possible_duplicate_of = ?, duplicate_decision = NULL, "
                    "duplicate_decided_by = NULL, duplicate_decided_at = NULL "
                    "WHERE id = ? AND state = 'waiting'",
                    (found, entry_id),
                )

    def _mark_those_pointing_to(self, entry_id: int) -> None:
        for row in self.db.query(
            "SELECT id FROM inbox_entry WHERE possible_duplicate_of = ? AND state = 'waiting'",
            entry_id,
        ):
            self._mark_possible_duplicate(row["id"])

    def decide_duplicate(self, entry_id: int, same: bool) -> InboxEntry:
        """Store a person's decision about a possible duplicate.

        "Same document" makes the entry a duplicate of the other one: it leaves
        the waiting list and can get no job. "New document" lets it be approved.

        A duplicate never gets a job, so no retention period would ever reach
        what it read. With the decision "same" it therefore keeps what an
        entry with the same bytes keeps, and no value, kind or correction;
        the decision is final.
        """
        entry = self.entry(entry_id)
        if entry.state != "waiting" or entry.possible_duplicate_of is None:
            raise CorrectionRefused(
                "The entry is not marked as a possible duplicate.", reason="no-possible-duplicate"
            )
        decided = (
            "same" if same else "new",
            account(),
            now(),
            "duplicate" if same else "waiting",
            same,
            entry_id,
        )
        with self.db.transaction() as conn:
            # The condition is part of the write: an approval between the look
            # above and this line must not end as a job whose entry is a
            # duplicate without values.
            changed = conn.execute(
                "UPDATE inbox_entry SET duplicate_decision = ?, duplicate_decided_by = ?, "
                "duplicate_decided_at = ?, state = ?, "
                "duplicate_of = CASE WHEN ? THEN possible_duplicate_of END "
                "WHERE id = ? AND state = 'waiting' AND possible_duplicate_of IS NOT NULL",
                decided,
            ).rowcount
            if not changed:
                raise CorrectionRefused(
                    "The entry is not marked as a possible duplicate.",
                    reason="no-possible-duplicate",
                )
            if same:
                conn.execute(
                    "UPDATE inbox_entry SET kind = NULL, page_count = NULL, values_json = '[]', "
                    "comparison_key = NULL, timings_json = '{}' WHERE id = ?",
                    (entry_id,),
                )
                conn.execute("DELETE FROM inbox_correction WHERE entry_id = ?", (entry_id,))
        if same:
            # As after a deletion: the log still holds the values.
            self.db.query("PRAGMA wal_checkpoint(TRUNCATE)")
            self._mark_those_pointing_to(entry_id)
        return self.entry(entry_id)

    # --- Deleting ----------------------------------------------------------

    def scan_to_delete(self, entry: InboxEntry) -> Path | None:
        """The scanned file of an entry, if it is still the file that was read.

        Only the stored path is ever returned, and only while its content has
        the stored hash; a file of the same name elsewhere is never touched.
        """
        if entry.problem_key == FileNameUnreadable.key:
            # Refused, not passed over: the person asked for a file to go, and
            # the stored path of such a file is not a name to delete by.
            raise FileNameUnreadable("A file with an unreadable name is not removed.")
        path = Path(entry.file_path)
        if not path.is_file():
            return None
        if file_hash(path) != entry.sha256:
            raise FileChanged("The file changed since it was read.")
        return path

    def delete(self, entry: InboxEntry, keep_marker: bool) -> None:
        """Remove the entry; corrections, job and transitions go with it.

        While the file stays in the watched folder, a marker of path and hash
        without any value keeps it from being read again.
        """
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM inbox_entry WHERE id = ?", (entry.id,))
            if keep_marker:
                conn.execute(
                    "INSERT OR REPLACE INTO inbox_deleted (file_path, sha256, deleted_at) "
                    "VALUES (?, ?, ?)",
                    (entry.file_path, entry.sha256, now()),
                )
        # The write-ahead log still holds the deleted rows; fold it into the
        # database, where secure_delete has overwritten them, and empty it.
        self.db.query("PRAGMA wal_checkpoint(TRUNCATE)")

    def _forget_deleted(self, folder: Path) -> None:
        """Drop the marker of a deleted entry once its file is gone from that path."""
        # A share that is unreachable must not look like files that were removed.
        if not folder.is_dir():
            return
        for row in self.db.query("SELECT file_path FROM inbox_deleted"):
            if not os.path.lexists(_real_path(row["file_path"])):
                self.db.write("DELETE FROM inbox_deleted WHERE file_path = ?", row["file_path"])
