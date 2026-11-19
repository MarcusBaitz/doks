# Sidecar

Status: 2026-11-19

This file applies to changes under `sidecar/` and to contracts that reach
from the Python sidecar into the frontend. It keeps errors, endpoints,
migrations and dependencies together so that no process boundary is changed
only halfway.

## Error contract

Errors leave the sidecar as RFC 9457 `application/problem+json` with a stable
`key`, never as a stack trace. `sidecar/substrakt/errors.py`
defines the domain errors; the stack trace belongs only in the local log,
because technical internals and document contents must not reach the
interface.

The frontend resolves the key through the active dictionary in `src/i18n/`.
A new domain error is therefore complete only when its stable key and the
matching German and English interface texts exist together. The TestClient
case belongs in `tests/sidecar/test_api.py`.

Error messages and logs never quote document contents. File name, hash and
technical details are enough for diagnosis; contents of a document would
otherwise form an unnecessary second data trail through log files.

## No network path of its own

The sidecar talks only to the local process and imports no network library
for outbound traffic. Ruff forbids the runtime imports `requests`,
`urllib.request` and `httpx` under
`[tool.ruff.lint.flake8-tidy-imports.banned-api]`. The table only acts
because `TID251` is in `select`; without that rule the ban is silently
inactive, which `tests/sidecar/test_egress_ban.py` rejects by running Ruff on
a module with each banned import. `scripts/check-egress.sh` additionally
finds imports that slipped past the linter through a comment.

## Blocking work

An endpoint that parses, runs OCR, extracts or renders is a plain `def`, not
`async def`. FastAPI runs a plain function in its thread pool; an `async def`
that calls the parser would hold the event loop, and the status request and
the viewer would wait for the whole OCR run. PDFium is not thread-safe, so
every call into pypdfium2 holds `PDFIUM_LOCK` from
`sidecar/substrakt/parsers/__init__.py`; a new call site without the lock can
crash the process under concurrent requests.

The parent check in `app.py` has a platform branch: `os.kill(pid, 0)` probes a
process on POSIX and terminates it on Windows, where the sidecar waits on a
process handle instead. The Windows branch is tested by patching the platform
and has not run on Windows.

`httpx` is allowed only as a development dependency for the FastAPI
TestClient. A runtime call belongs in the Rust shell's egress chokepoint,
because only there do mode, allowlist and audit log act together.

## Adding an endpoint completely

A new endpoint passes through five places. None of them is generated:

1. The Pydantic model goes into `sidecar/substrakt/model.py` or
   `sidecar/substrakt/db/models.py`, depending on responsibility.
2. The FastAPI endpoint goes into `sidecar/substrakt/app.py` and names its
   `response_model`.
3. The matching TypeScript type is added to `src/api/types.ts` by hand.
   OpenAPI type generation is deliberately still open.
4. `src-tauri/src/bridge.rs` gets the Tauri command, and
   `src-tauri/src/lib.rs` registers it in `invoke_handler`.
5. `src/api/client.ts` wraps the call for the frontend.

This chain keeps port and session token out of the frontend. The egress gate
rejects a supposedly shorter path via `fetch`; API tests and typecheck secure
the contract on both language sides.

## Document kinds

Knowledge about a document kind belongs in its YAML file under
`sidecar/substrakt/document_kinds/`, not in Python. `labels.py` and
`fields.py` work generically with what `DocumentKind` delivers from the file;
`invoice.yml` is the pattern. A new label or document kind is therefore a
file change; the 84-PDF run measures whether recognition changes as a result
(see `docs/document-types.md`, section „Measuring a change“).

A key goes into the Pydantic model `DocumentKind` or `LabelRule` first.
Then `document_kind.schema.json` is regenerated with
`document_kinds.write_schema()`; `tests/sidecar/test_document_kinds.py` rejects
an outdated schema file. If a new key reaches the frontend,
`src/api/types.ts` is updated by hand.

A custom parser is the exception, for when the core is not enough: a module
under `document_kinds/parser/` with `read(doc, field, kind)`, named in the
YAML file with `parser:`. A second parser for the same kind, or a parser that
loads code from the user directory, would destroy the reviewability of the
file. Invalid files end as `document-kind-invalid`; its texts are in both
dictionaries under `src/i18n/`.

Templates changes the values of a kind through `sidecar/substrakt/kind_values.py`,
the one place that writes a kind file. It never edits the shipped file: the
changed kind is validated with Pydantic and written through a temporary name
and `os.replace` into `<data dir>/document_kinds/`, where it replaces the
shipped one at the next load. A rename changes only the label, so a profile,
a waiting entry and a job still find the value by its name. A new value
becomes a `text` label rule named after the label as it stands in the
document. A removed value leaves `same_document` and every profile that
expects it, written the same way into `<data dir>/pipeline_profiles/`, so the
profile stays valid and reading goes on; a removal that would leave a profile
without a value for the kind is refused. Values already stored with an entry
are never rewritten. A refusal ends as `kind-change-refused` with a `reason`
and writes nothing; `tests/sidecar/test_kind_override.py` holds the cases.

## Inbox and pipeline profiles

`sidecar/substrakt/inbox.py` holds the watched folder: a thread polls the
chosen folder, takes a file once size and modification time are unchanged
across two looks, and writes an entry to `inbox_entry`. An entry stores path,
SHA-256, customer, profile, kind, values with locations and step timings. A
column for document text or a page image would break the persistence boundary;
`tests/sidecar/test_inbox.py` pins the column list and rejects a BLOB.

A file is known by path and hash, so a restart reads nothing twice. Content
that was already read becomes an entry in state `duplicate` that points to
the first one and is not parsed. An entry in state `error` or `duplicate`
is never that first one: a file renamed after `file-name-unreadable` is read
normally, and the bytes of any other error end as an error again, not as
its duplicate. A file that cannot be read becomes an entry
in state `error` with the problem key of the error; it is never retried by
itself, and the loop goes on. The folder must lie inside `SUBSTRAKT_ROOTS`,
and without roots nothing is watched.

A file in the folder comes from a scanner or a share, not from the
application, so nothing about it is trusted. Roots and size are checked
before a byte is read, and only the checked path is hashed: a link that
leaves the read roots or a file over the size limit ends as an entry in
state `error` with an empty hash. A file with more pages than
`MAX_INBOX_PAGES` in `config.py` is not parsed and ends as
`document-too-many-pages`, because one thread reads for every customer; the
number is an assumption, not a measurement. A name that is no valid text
ends as `file-name-unreadable`. Its stored path is the readable form, with
“?” for each unreadable character, followed by `//` and the bytes of the
path as hex (`_stored_path`): no path of a file contains `//` there, so two
files never share one stored path, and `_real_path` leads back to the file. An entry found in state `new` at start was being read
when the process ended; it becomes `reading-interrupted` and is not read
again, since the same file could end the process at every start. Whatever
else fails for one file is logged with the class of the error only and
becomes an entry in state `error` with the key `internal-error`, written in
its own `try`, and the loop goes on with the next file; every refused file
is tried once, not at every look. `tests/sidecar/test_inbox_hardening.py` holds one test per case.

`audit.ingest` follows the same rule for the spool of the shell: a line that
is no text, has a time out of range or a number SQLite cannot hold is
skipped and counted in the log without its content, the other lines are
stored, and the function never raises, because the sidecar calls it at
start.

Choosing the watched folder (`Inbox.choose_folder`) creates its subfolder
`Ausgabe` (`OUTPUT` in `inbox.py`) when it is missing and uses an existing
one as it is, without renaming or emptying it; it is the only place approved
jobs are written to, so Settings has one folder setting, not two. The loop
never reads anything under `Ausgabe`, compared casefolded because Windows
and macOS do not distinguish case: what Substrakt writes is no scan and must
never become an entry, a customer or a count, also after a restart. An
`Ausgabe` that is a link is refused with `path-not-allowed`, and it must
resolve inside the read roots, because files written through a link would
land where the roots do not reach. A file named `Ausgabe` refuses the choice
with `output-name-taken` and keeps its bytes. `Inbox.handover_folder`
returns `Ausgabe` only while it is a plain folder; otherwise jobs stay
pending. When the watched folder changes, the files in the former `Ausgabe`
stay where they are, and a hand-over folder stored by an older version
(setting `handover_folder`) is ignored.

The same paper scanned twice has different content. Which values identify a
document stands in the kind file under `same_document`; a name of such a
value in Python would put knowledge of a kind into the core, and
`tests/sidecar/test_value_duplicates.py` greps for it.
`sidecar/substrakt/comparison.py` turns kind and values into a hash that is
stored on the entry, and only when every value was read unambiguously. An
entry whose hash equals that of another entry with other content is read
normally and gets `possible_duplicate_of`; it is never discarded by itself.
A correction recomputes the hash and the mark, also for the entries that
pointed to the corrected one. `Inbox.decide_duplicate` stores a person's
decision with account and time: “same” makes the entry a duplicate, “new”
lets it be approved; until then `jobs.job_file` refuses the approval. The
state it requires is a condition of its UPDATE, not only a look before it,
so a decision that meets an entry approved in between changes nothing. A
duplicate never gets a job, so the retention period never reaches it. With
“same” the entry therefore loses its values, kind, comparison hash and
corrections, also from freed pages, and keeps what an entry with the same
bytes keeps; the decision is final. A place that makes an entry a duplicate
and leaves its values would store them without an end.

What a folder means comes from a pipeline profile, one YAML file under
`sidecar/substrakt/pipeline_profiles/`, overridable by a file of the same
name in `<data dir>/pipeline_profiles/`. It names the folder level of the
customer, the document kinds, the expected values with their names in the
target, and the target. The name of a target application stands in a profile
file and nowhere in Python, Rust or TypeScript; a test greps the code for the
titles of the shipped profiles. For the same reason no profile name is a
default in code: the chosen profile is active, or the only one there is.

A kind lists its values under `values`, which an approval requires, and
under `optional`, which go along when they were read unambiguously and never
block an approval. A format writer sees both as one list of names.

A key goes into the Pydantic model `PipelineProfile` first; then
`pipeline_profile.schema.json` is regenerated with
`pipeline_profiles.write_schema()`, and `docs/pipeline-profiles.md`
names the key; `tests/sidecar/test_second_profile.py` rejects a key the
guide does not name and a worked example that differs from the shipped
profile. A profile that names a kind without a
file, or a value the kind does not read, ends as `pipeline-profile-invalid`
when it is loaded, not when a document arrives.

## Approval and jobs

`sidecar/substrakt/jobs.py` holds the only way out. `Jobs.approve` refuses an
entry while a value that its profile expects for the kind is open or not
grounded, and otherwise stores the job, its first transition and the state
`approved` of the entry in one transaction. That the entry still waits is a
condition of this UPDATE: a decision “same document” stored after the
approval looked refuses the approval, and no job is created. The UPDATE runs
before the job is inserted, so an entry deleted after the approval looked
ends as `entry-not-waiting`, not as a broken reference. A second approval of the same
entry returns the first job; the same content under another entry finds the
job by its idempotency key and becomes a duplicate of the first entry.

A job moves only along the table `TRANSITIONS`: pending, handed over, done or
failed, and from failed back to pending when a person releases it. `Jobs.move`
is the one function that changes a state, and it stores every change in
`job_transition` with time and reason. A new state or a second place that
writes `job.state` would let a job skip the record.

The job file is written by `write_job_file` through a temporary name, fsync
and `os.replace`, into `Ausgabe` of the watched folder. A file that already
has the name `<id>.json` or the temporary name is foreign and is never
replaced: the temporary file is opened with mode `x`, and the job fails with
`hand-over-name-taken`, as a GDV file fails on a taken name. Writers of hand-over formats are registered
by target name in `WRITERS`; a target without one ends as a failed job and
writes nothing. A key goes into the model `JobFile` first; then
`job.schema.json` is regenerated with `jobs.write_schema()` and
`docs/job-format.md` names the key, which `tests/sidecar/test_jobs.py`
checks.

Corrections live in `Inbox.correct`: the entry holds the current values, the
table `inbox_correction` what stood there before. That the entry still waits
is a condition of its UPDATE, for values and for a corrected kind alike, and
the mark of a possible duplicate moves only on a waiting entry: a correction
that meets an entry approved in between is refused and records nothing. Kind
and values as the correction read them are conditions too: a correction that
meets another one stored in between is refused with `entry-changed`, so every
“before” in `inbox_correction` is what stood there. A corrected kind reads the
file again and must be a kind of the entry's profile. A value under
`confirmed` keeps text, location and source and is settled as a typed value
would be, so a text that does not fit its type stays unclear; its row in
`inbox_correction` has the same before and after, records account and time,
and does not count as changed. Everything that hangs
on an entry references it with `ON DELETE CASCADE`.

## GDV hand-over

`sidecar/substrakt/gdv/` writes approved jobs of one customer as one GDV
file. `writer.py` is the only place with the record layout; every position
comes from the record tables of release 01.12.2023, named in its header and
in `docs/gdv-hand-over.md`. `reader.py` reads every file back before it
gets its name and imports nothing from the package, so that a slip in one
transcription shows; `tests/sidecar/test_gdv.py` rejects an import and holds
a third table of positions.

Insurer number, line of business code and payment mode code come from the
YAML files under `gdv/tables/`, replaceable in `<data dir>/gdv/`; encoding,
record separator, broker number and sender come from the block `hand_over`
of the pipeline profile and have no default in code. A value without an
entry, or one that does not fit its field, is never guessed or cut: the
contract is not written and the result names the item.

`sidecar/substrakt/hand_over.py` stands between the job queue and a format.
It names the formats (`FORMATS`), refuses an approval the format could not
write, and runs the hand-over for one customer when a person starts it;
`jobs.py` only takes its two functions in the constructor. A new format is a
module with `check`, `hand_over` and `PART` and one entry in `FORMATS`; the target
application still stands only in the profile.

## Deletion, retention and the record of who approved

A hand-over run and a deletion hold the same lock, `Jobs.handover_lock`, and
a deletion reads what its job points to only inside it. Otherwise a run that
is writing would leave a file with a contract whose entry is already gone.
For the same reason a run stores `job.format_file` for every job of a file
before it writes the job files. If one of them cannot be written, the file
of the format goes as a whole and all its jobs fail, so that no file with a
contract stays that no job points to.

`Jobs.delete_entry` is the one way an entry goes. It removes the job file
and the file of the hand-over format the job was written into (the column
`job.format_file`, only that stored path), removes the job files of the other
jobs of that file and fails those that are not done so that a person hands
them over again, then removes the entry, and SQLite removes corrections, job and transitions with it.
The database runs with `secure_delete`, and the write-ahead log is folded in
after a deletion, so a deleted value is not left in freed pages;
`tests/sidecar/test_privacy.py` searches the database files for it. The
scanned file stays unless the caller asks for it to go, and then only the
stored path is removed and only while its content has the stored hash.
For an entry with `file-name-unreadable` no file is ever removed: the wish
is refused with that key and the entry stays.

A file that is still being written has a name of its own: `TEMPORARY` in
`jobs.py` for a job file, `PART` in the module of a format. Both writers
open it with mode `x` before they write and remove it on any later
exception, so a foreign file under that name keeps its bytes and the job
fails with `hand-over-name-taken`. What a crash leaves has values and no job that
points to it, so `hand_over.clear_leftovers` removes files of exactly these
names from the current `Ausgabe`, at start and when the watched folder is
chosen, inside the same lock; a former `Ausgabe` is not cleaned. A format that writes under another temporary name
needs its own `PART`, or its leftovers stay.

Because the folder is still watched, a deleted entry whose file stays leaves
a row in `inbox_deleted` with path, SHA-256 and time, and no value. Without
it the file would be read again at the next look. The row goes when the file
is gone from that path; for an unreadable name that is the real path behind
the stored one. A second way to delete an entry would skip the job
file or this marker.

The retention period is the setting `retention_days`; its default is
`DEFAULT_RETENTION_DAYS` in `inbox.py`, 90 days, an assumption the owner has
not confirmed. `Jobs.keep_retention` deletes, at start and once a day, every
entry whose job has been done for longer, through `delete_entry`. It never
removes a scanned file. A job moves to `done` only through the report of a
person on Overview that the import of its customer's file worked
(`POST /jobs/hand-over/result`, through `Jobs.move`), so retention deletes
nothing that no person confirmed.

An approval, a release of a failed job and a correction store
`getpass.getuser()` and the time. Transitions the application takes itself
have no account.

Logs hold keys, ids and timings, never a value. `logging_setup.configure`
keeps every library at INFO even in development, because the PDF parser
writes each text token at DEBUG. The test `no_content_in_logs` runs the path
with every refusal and searches the log file, the problem responses and
every file outside the database and the job file for the values.

## Migrations

Schema changes are not improvised at runtime. They get a new file
`sidecar/substrakt/db/migrations/NNN_name.sql`, a gap-free three-digit number
and a short reason in the header. The pattern is `002_output_format.sql`.

Migrations are meant to be idempotent and run through `PRAGMA user_version`
exactly once, in numerical order and in one transaction. An error must not
leave the database half-migrated. Tests in `tests/sidecar/test_db.py` check
fresh setup, order and repetition.

Exception for the English switch only: by the owner's decision of
15 October 2026, the existing migrations 001 and 002 are rewritten in place
with English names, as if they had been English from the start, and no
renaming migration is added. Substrakt has no released version, so only
development databases are affected; they are deleted and rebuilt. After that
switch the rule above applies again without exception.

SQLite stores types, fields, inbox entries and jobs, not loaded document contents;
the prepared table for runs is written by no code. This boundary comes from
`sidecar/substrakt/store.py` and keeps the data trail small; a migration must
not shift it in passing. The pilot's inbox stores values and locations, never
text or images (`docs/harness/01-architecture.md`, section “Job and hand-over
boundary”).

## Style and tests

Ruff checks `E`, `F`, `I`, `UP`, `B`, `SIM` and `RUF`. `RUF001` to `RUF003`
are deliberately disabled, because characters such as „…“, dashes and
multiplication signs are correct typography in German interface texts and in
the German sample content of synthetic documents.

Sidecar tests are under `tests/sidecar/`. `test_api.py` shows the pattern for
endpoints with the FastAPI TestClient; `test_fields.py` shows the domain
checks of field definitions. Property-style tests use `random.Random(seed)`,
so that failures stay reproducible and Hypothesis under MPL-2.0 does not open
an additional licence question.

The tests run without manually set `SUBSTRAKT_DEV=1`:
`tests/sidecar/conftest.py` sets the necessary environment at module level,
before `app.py` loads its configuration during collection. A fixture would be
too late at that point.

## Dependencies

Before every new runtime dependency, `licenses/policy.toml` is read and the
licence, including transitive packages, is checked. The licence is written as
a comment next to the entry in `sidecar/pyproject.toml`; the policy and
`docs/decisions.md` are updated with the reason.

The licence gate treats runtime and development differently: whatever ends up
in the bundle must be on the allowlist; development tools are checked against
the denylist. Moving a package between `dependencies` and `dependency-groups`
requires an explicit new assessment.
