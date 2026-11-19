# Binding decisions

A condensed version of the four foundation documents, reduced to what matters
when building. If this file and an original disagree, the original wins; the
originals are internal and not published (see [README](README.md)).

## The two promises

**1. Nothing leaves the infrastructure.** No document content, no model
call, no telemetry. In case of doubt this promise beats every other
requirement, including convenience and accuracy. If a requirement collides
with it, locality wins, and the conflict is named explicitly instead of being
quietly built around.

**2. Fully permissive licences.** This applies to code *and* model weights
alike. An Apache-2.0 library that loads a CC-BY-NC model is a violation.
Enforced through [`licenses/policy.toml`](../licenses/policy.toml).

## Target profile

A standard laptop, 16 GB RAM, **no GPU**, Windows/macOS/Linux. A design
decision that requires a GPU is wrong. The development machine has an
RTX 5070 Ti; it must not leak into any assumption.

## Stack

| Layer | Decision |
|---|---|
| Desktop shell | Tauri v2 (Rust) |
| Frontend | React + TypeScript + Vite, Tailwind |
| Viewer | PDF.js v6 with a self-built overlay |
| Backend | Python sidecar (FastAPI), 127.0.0.1, random port, bearer token |
| Inference | OpenAI-compatible HTTP only, with `response_format: json_schema` |
| Local LLM | llama.cpp (llama-server), GGUF |
| Server LLM | vLLM on a GPU **in the customer network**: the same client, a different address |
| PDF | pypdfium2 (rendering) + pdfplumber (word bounding boxes) |
| Excel | openpyxl, python-calamine for large files |
| Images | Pillow + scikit-image |
| OCR | **Tesseract 5** (primary, measured); RapidOCR not adopted |
| Fast extraction | GLiNER2 (`fastino/gliner2-base-v1`) + regex |
| LLM model | `ibm-granite/granite-4.0-micro` |
| Embeddings | `intfloat/multilingual-e5-small` |
| Grounding | rapidfuzz over the word bounding-box index |
| Persistence | SQLite |
| Bundling | PyInstaller |
| Icons / font | Lucide (ISC), Inter (OFL 1.1) |

## Architecture rules

**Egress chokepoint.** Outbound traffic runs through *one* central function
in the Rust layer. No `fetch` in the frontend, no scattered `requests` calls.
Whatever does not pass through this chokepoint does not exist. A CI test
starts the app in a sandbox without a network route; any request in Air-gap
mode makes the test fail. That is the real safeguard of the core promise.

**Three operating modes, strictly separated.** Air-gap (default, 127.0.0.1
only), On-premise (additionally an administratively maintained allowlist,
including a vLLM server in the customer network), Cloud (only after explicit
unlocking). Settable through a machine-wide policy file that the user cannot
override. An inference server outside the customer network is not allowed in
any mode.

**Coordinates are always document coordinates**, never screen pixels.
Conversion happens only when rendering. Zoom, window scaling and retina
displays must never move stored highlights.

**No model name hard-coded.** Models come from the registry and are
swappable. Every entry needs repository, revision, SHA-256, licence and
licence URL; an entry without these is rejected at start-up.

**Never hard-wire a quantisation method.** GGUF locally,
compressed-tensors/AWQ on the server: a property of the registry entry, not
a code path.

**No PyTorch in the bundle.** All ML runs on ONNX Runtime or llama.cpp.

**No network access at runtime in standard operation.** No model downloads,
no telemetry, no crash reports, no font CDN, no update checks without
explicit approval. Models are loaded with `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1`.

## Provenance is a core function, not an extra

Constrained decoding guarantees the *form* of the output, not its *truth*. A
model can deliver perfectly structured, schema-conformant and arithmetically
consistent JSON with invented values; the documented case is an invoice
amount that wanders from 42.50 to 45.20.

Therefore: **every extracted value needs a location in the document.** If
none is found above the threshold, the field is marked as “unsupported” and
put up for manual review, never silently output.

This also applies to VLM output: its bounding boxes are documented as
unreliable and must **never be taken over directly as provenance**. They count
as a hint and are checked back against the word index through fuzzy
grounding like any other value.

## Stage 0, measured on 28 July 2026

The four open questions are answered. In full in
[`measurements/README.md`](measurements/README.md); three decisions changed
as a result:

**Tesseract is the primary engine, not RapidOCR.** More accurate (98.9%
against 90.5%), more robust and faster. Decisive: RapidOCR's confidence
reports 97–99% where 87–90% is correct, which makes it useless as a trigger
for escalating the reading stage. Tesseract's word confidence is fit for
that, with a threshold around 85% as a starting point.

**The reading stage stays two-tier.** The third tier (document VLM) is viable
locally (13.6 s per page at 150 dpi) but does not pay off for printed
documents: Tesseract is more accurate and twelve times faster than a 7B VLM
on a dedicated GPU. It stays planned as a swappable module but does not
become the standard escalation. Not measured and therefore open: handwriting,
forms without lines, nested tables.

**150 dpi instead of 300.** For both reading paths. At 300 dpi Tesseract is
slower without being more accurate, and the VLM runs into repetition loops.

**The server variant serves path B, not the reading stage.** It remains
right, but not because vision models become usable there; rather because free
field extraction becomes interactive. For vision models VRAM is the limit,
not compute.

**Provenance is necessary, as measured.** Constrained decoding works with
multimodal models: 10 of 10 answers were schema-conformant, but only 57% of
the values were correct. An extractor that trusts schema validation ships
43% wrong values without a warning sign.

All other performance figures in the foundation documents without an
explicit measurement remain estimates and are treated as such.

## Labelled document fields, 14 October 2026

The sample document fields use the extractor `document_field`. It assigns
values through German and English labels and their spatial neighbourhood: to
the right of the label or in the cell below. Other labels limit the search.
Value types are checked before a value is taken over; differing candidates
stay open. That way a delivery date does not replace a missing document date,
and the next column heading does not become the document number. Locations
still come from the words actually read.

Net amount, tax and document type complement the earlier sample fields. The
sender can be read from the letterhead before the recipient; this heuristic
assignment stays subject to review. Explicit regions, manual values and
custom regex configurations keep their precedence. Custom field definitions
already saved are not overwritten automatically; the new rules are loaded
through the updated sample fields.

Weak, sparse or shaded OCR pages get at most a second Tesseract run: local
thresholding and page segmentation mode 11. The image dimensions stay
identical; the second run replaces the first only if its summed word
confidence is higher. No field value is repaired using expected values,
dictionaries or calculations. The confidence sum is a heuristic, not a
guarantee of correct characters or signs.

The repeated 84-PDF run is a regression on a corpus that had already been
examined. The original split names are kept for comparability but no longer
count as a blind test after this error analysis. A new quality statement
needs fresh, independent documents.

## Document kinds as YAML files, 15 October 2026

Domain knowledge about a document kind lives in exactly one YAML file, not in
code. `sidecar/substrakt/document_kinds/invoice.yml` holds the values,
display names, data types, normalisation, required values, label patterns,
boundaries, legal forms and the titles by which an invoice and a credit note
are recognised. The core of parser, word index, label search, normalisation
and grounding reads this description and knows no document kind itself; the
fixed tables `LABELS`, `TITLES` and `COMPANY` and the sample fields in
`fields.py` are gone. A new document kind is a new file.

Bundled files live in the package, custom ones under
`<data dir>/document_kinds/`. A custom file with the same name replaces the
bundled one completely; nothing is merged. Files are validated on load with
Pydantic against `DocumentKind`; unknown keys, invalid patterns and a `name`
that differs from the file name are rejected. An error leaves the sidecar as
`problem+json` with the key `document-kind-invalid`, file name and position,
without document text. The JSON schema `document_kind.schema.json` is
generated from the model and serves editors; a test keeps it in sync. YAML
is read exclusively with `yaml.safe_load`.

At most one custom parser per document kind, and only when the core is not
enough: `parser: <name>` refers to a bundled module under
`sidecar/substrakt/document_kinds/parser/` with the function
`read(doc, field, kind) -> Assignment | None`. `None` hands back to the core.
A file in the user directory can choose a parser but cannot bring code. The
invoice needs no parser of its own.

A document kind names neither a model nor a quantisation method; both belong
in the registry from stage 3 and are rejected as unknown keys.

**Relation to SQLite.** YAML is the source for document kinds, that is, for
general knowledge about a kind of document. The templates created with the
assistant stay in SQLite: they are a user's field set with marked regions on
a sample document, not general knowledge about a document kind. A value taken
from a document kind carries its label rule in the existing JSON part
`locator_json`; the schema does not change, so there is no migration. Older
sets without a rule that only carry `extractor="document_field"` still get the
rule from the document kind that knows a value of that name. As long as the
recognition from stage 3 is missing, that is the default document kind
`invoice`; the core runs a custom parser only when a document kind is passed
to it explicitly.

The 84-PDF run from `corpus/evaluation` produced byte-identical predictions
and review flags before and after the switch: 315 of 336 core fields, 730 of
756 fields, zero wrong values without a review flag. All nine old anchor
patterns, the legal-form pattern and the title assignment compile from the
YAML file to the same regular expressions.

PyYAML has since been a direct runtime dependency of the sidecar (MIT, as is
the bundled libyaml) and was already in the lock file transitively before.

## Broker pilot architecture, 10 November 2026

The first pilot is an insurance broker: the clerk puts scanned policies,
contract changes and premium invoices into a folder per customer, the
application reads them, the clerk corrects and approves, and the approved
contracts leave as a file that the broker's management program reads with
its own GDV import. Which program that is stands in a pipeline profile, and
the customer's material (its profile, contracts and research) is kept in a
private repository and installed into the data directory
([`configuration.md`](configuration.md), section “Customer setup”); the core
names neither.

**Substrakt stays the only application.** There is no second program next to
it, no agent, no Windows VM and no remote control of the target program's interface.
Remote control would need an unlocked desktop session and a licence answer
from the vendor, and it would act in the broker's portfolio without a person
looking; a file that a person imports needs none of that. Remote control is
reconsidered only if the vendor refuses the GDV import for these files.

**No code is shared with workspace.** The workspace pipeline is JavaScript
inside a server of about 14,000 lines, sends every document to an external
provider and stores no locations. A shared package is impossible across the
two languages, and calling workspace as a service would break the first
promise. Only the shape of its value definitions is taken over as an idea.

**The job record separates processing, review and hand-over.** Reading a
document ends in an inbox entry. Review works on that entry and ends in an
approval. An approval creates exactly one job, and the writer of the hand-over
format reads nothing but jobs. Each of the three parts can therefore fail,
be repeated and be tested without the other two, and a hand-over can never
contain a value that no person approved.

**Entries and jobs persist values, not content.** SQLite stores state, file
path, SHA-256, document kind, the values with their locations, corrections
and step timings. It stores no document text and no page image; the file
stays where the scanner put it, and the viewer reads it from there. The rule
that document content lives only in memory therefore stands unchanged. What
is new is that read values, which are personal data, are now at rest in
SQLite and in the job files; deletion and retention are part of the pilot,
not an afterthought.

**The hand-over is a folder inside the customer network.** An approved job is
written there as one JSON file by atomic rename, and the approved contracts
of a customer as one GDV file. The folder must lie inside the read roots. The
sidecar binds to `127.0.0.1` and may open no network path; a folder needs no
new service, no listener and no egress rule, so both egress gates stay as
they are. A person imports the GDV file in the target program and marks the hand-over
as done or failed; nothing is handed over twice by itself.

**GDV carries the values; the PDF is filed by hand.** The GDV data set
“VU-Vermittler” is a published fixed-width format (release 01.12.2023,
<https://www.gdv-online.de/vuvm/>, read on 10 November 2026) that foresees a
broker as sender and that broker management programs import. The pilot writes header
0001, address 0100, general contract part 0200, collection record 0400 for a
premium invoice and trailer 9999. BiPRO delivery of the document itself is
out of scope: the norms need a licence or membership, and the target program
would have to accept an additional provider. Unverified until a test import
into a test database of the target program: whether it accepts a file from a
non-insurer, by which key it finds a contract, and whether empty fields
overwrite stored values. Importing into a productive database needs that test
and the owner's explicit release.

**The sidecar polls the folder.** It uses the standard library while the
application runs and reads a file only after its size has stopped changing.
A watcher library would be a new dependency, and scanner shares deliver file
events unreliably. The limit is stated openly: nothing is read while the
application is closed.

**The customer comes from the folder, the duplicate from the hash.** The
first-level subfolder names the customer, so the pilot needs no master data.
The same SHA-256 is a certain duplicate. The same policy number, kind and
document date with different content is a possible duplicate that a person
decides, because a read value can be wrong and must never discard a document
by itself.

**Profiles and kinds are files.** A pipeline profile fixes folder structure,
expected values and target; it is built like a document kind file and can be
overridden in the data directory. One profile is active at a time. Everything
specific to a target program and to a broker stands in the profile and in the
writer of that hand-over format, nowhere else in code.

**The inbox has its own tables; the active profile has no default in code.**
Built on 10 November 2026 with migration 003. The prepared table
`extraction_run` was not reused for inbox entries: it has no state, no path,
no customer and no reference to a first entry, and it points to a template
instead of a document kind. The prepared key-value table `app_setting` holds
the chosen profile. A file is known by path and hash; a duplicate is a row of
its own that points to the first entry, so the clerk sees where it arrived.
Which profile is active is the clerk's choice or, if only one profile exists,
that one. A profile name as a default in code would put the name of a target
application there.

**An approval is the only source of a job, and a failed job waits for a
person.** Built on 10 November 2026 with migration 004. Whether an entry may
be approved is decided by the profile it was read with: every value the
profile expects for the kind must be read with a location or entered by a
person. The job gets a random id, because a counter would lend the file name
of a deleted job to a new one, and an idempotency key over file hash, kind
and values. A pending job waits while the folder `Ausgabe` of the watched folder is
missing or no plain folder; a failed
job is never retried by the queue, so a person sees every failure. The job
file does not copy the hand-over settings of the profile: a writer loads the
profile by name. Writers are registered by target name, and the table is
empty until the GDV writer exists, so today every job ends as failed with
the reason `target-without-writer`.

**A deleted entry leaves a marker of path and hash.** Built on
10 November 2026 with migration 005. The folder stays watched, so a file
whose entry was deleted would be read again at the next look. The marker
holds the path, the SHA-256 and the time of deletion, and no value read from
the document; it goes when the file is gone from that path. Deleting the
scanned file itself is a separate request and removes only the stored path
while its content has the stored hash. The retention period deletes entries
whose job has been done for longer than the set number of days; the default
of 90 days is an assumption the owner has not confirmed. No shipped code
marks a job as done yet, so retention deletes nothing today.

**A deleted contract takes its GDV file along.** Built on 10 November 2026
with migration 006. A GDV file holds the contracts of one customer that were
handed over together, and one contract cannot be cut out of a written file.
Deleting an entry, by a clerk or by retention, therefore removes the whole
file; the other contracts of that file that are not done fail with a reason
and are written again, without the deleted one, when a person releases them.
Contracts that are done keep their state. The job files of all contracts of
the removed file go with it.

**A match on read values is marked, and a person decides.** Built on
10 November 2026 with migration 007. Each kind file names the values that
identify a document; the entry stores a hash of kind and values, never a
second copy of the values. An entry with the hash of another entry and other
file content is read and marked. It cannot be approved until a person has
decided: the same document, which ends the entry without a job, or a new
one. An entry decided as the same document keeps no value and no
correction, because without a job no retention period would reach them;
that decision is final. A missing or unclear value gives no hash and no mark, because a
doubtful reading must not hold up or end a document.

**A profile separates required from optional values.** A policy prints the
premium per payment period or the annual premium. Listing both as required
would block every policy; so a kind lists values an approval waits for and
values that go along when they were read. Whether what was read is enough
for the target is decided by the check of the hand-over format.

**Egress attempts are spooled by the shell and stored by the sidecar.** The
attempt happens in the shell and the database belongs to the sidecar. A call
to the sidecar would lose the attempt whenever the sidecar is not running,
and a database driver in the shell would be a new dependency. The shell
therefore appends a synced line to a file in the data directory, and the
sidecar moves the lines into `audit_log`. An exit between storing and
removing the taken file stores those attempts twice, never too few.

**What is promised about privacy.** Provable properties of the product:
local processing, no transfer, minimal storage, deletion, a record of who
approved. Conformity with the GDPR is the duty of the broker as controller
and depends on his organisation; the product does not claim it.

### Where the documents claimed more than the code

The inventory found four statements that the code does not carry. The
documents now say what the code does, and a criterion of the pilot's goal
contract closed each gap:

| Statement | Code on 10 November 2026 | Closed by |
|---|---|---|
| SQLite persists extraction runs | The table `extraction_run` exists; no code writes to it. Results live in the frontend's memory | Z3.2 |
| Every allowed and refused egress attempt is logged | Attempts are buffered in the shell's memory and lost at exit; only refusals also reach the application log. The status `refused` would fail the table's CHECK | Z1.2, Z6.2 |
| Ruff forbids network imports in the sidecar | The ban is configured but its rule family is not selected; the grep gate catches the imports | Z1.3 |
| A CI test starts the app without a network route | No such test exists; the air-gap CI test is stage 4. The pilot adds a run with every non-loopback connection blocked | Z6.1 |

Repaired since with milestone M1: the shell records `denied`, a status the
table accepts (Z1.2), and Ruff rejects the network imports (Z1.3). The
Since milestone M4 the attempts are stored durably (Z6.2): the shell spools
them to a file at the moment of the attempt, and the sidecar moves them into
`audit_log`.

Two rules above are a design, not enforced code: the Cloud mode has no
unlock mechanism, and nothing checks that an allowlisted inference server
lies inside the customer network. No request is sent through the chokepoint
yet, so neither gap carries traffic today. Both have to be closed before the
first outbound call is built.

## Gemma 4 admitted, 10 November 2026

Gemma weights were forbidden as a family because the Gemma Terms of Use are
not an OSI licence. That is still true for Gemma 1, 1.1, 2, 3, 3n and the
variants named in the appendix of the terms: they bind every recipient to a
prohibited-use policy, which lists automated decisions in insurance among its
examples, and let Google restrict usage remotely. These stay forbidden by
name in [`licenses/policy.toml`](../licenses/policy.toml).

Gemma 4 has its own licence. Checked at the source on 10 November 2026:

| What | Where | Finding |
|---|---|---|
| Model card of the concrete weights | <https://huggingface.co/google/gemma-4-E4B-it/blob/4ecc2ba63bcac23ba4a767fc87025b1450f84c9c/README.md> | `license: apache-2.0`, `license_link` to the Gemma 4 licence; the repository is not gated |
| Quantised weights for llama.cpp | <https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf>, revision `4b4a2c1d584be7264f87aac328a1bc739ce81b6c` | the same licence and link in the card metadata |
| Licence text | <https://ai.google.dev/gemma/docs/gemma_4_license>, which redirects to <https://ai.google.dev/gemma/apache_2> | the Apache License 2.0 without an added clause; no reference to the terms of use or the prohibited-use policy |
| Terms of use of the older generations | <https://ai.google.dev/gemma/terms>, last modified 1 April 2026 | “For Gemma 4 terms, see the Gemma 4 license”; the appendix lists Gemma 1 to 3n and variants, not Gemma 4 |
| Other Gemma 4 repositories by Google | Hugging Face listing of `google/gemma-4-*`, 38 repositories | all tagged `apache-2.0`; the 35 listed `google/gemma-3-*` and `google/gemma-3n-*` repositories are all tagged `gemma` |

The weight repositories contain no licence file of their own; the licence is
stated in the card and its link. The policy therefore admits `google/gemma-4-*`
as Apache-2.0 and keeps every other `google/gemma-*` repository forbidden.
`scripts/check-licenses.py` reads the admission before the ban and applies
both to every repository that `scripts/fetch-models.sh` loads from.
`tests/sidecar/test_license_gate.py` holds a test for both cases; without the
admission Gemma 4 falls back to forbidden.

The admission says that the licence fits the second promise. It chooses no
model: nothing is fetched or bundled, the stack table above is unchanged, and
whether Gemma 4 is good and fast enough on the target laptop is unmeasured. A
quantisation published by someone else is a different repository with its
own card and needs its own check. As with every model, the licence is checked
again at the pinned revision when a registry entry is written.

## Interface clarity, 19 November 2026

An audit of the four places against fourteen design rules (R1 to R14 in
`.claude/skills/ui-expert/SKILL.md`) led to these decisions of the owner.

**The path for documents read by hand is hidden.** The setup assistant,
„Von Hand gelesen“, „Ergebnis sichern“ and their own review screen are not
reachable from any place: `src/App.tsx` has no view for them, and the code
stays for stage 3. A second workflow beside the watched folder gave
„Vorlage“ two meanings and put a dark button on something that has no effect
on the folder. Belegarten therefore lists only the kinds of the active
pipeline profile.

**Enter never approves.** Enter presses the one dark button of a screen
everywhere except the approval in Review and the decision „Derselbe Beleg“,
which are pressed only on the focused button. „Freigeben“ is active only when
every unclear value was confirmed or corrected once. With Enter pressed over
a series the approval would become a rubber stamp (automation bias,
Parasuraman and Manzey 2010), and training alone does not prevent that.

**One thing, one word.** The screen says „Belegart“ (“document kind”), never
„Vorlage“, and „Arbeitsweise“ (“way of working”) instead of „Profil“. The
name of a target application reaches the screen only as the title of a
profile file.

**Settings takes effect at once**, without a save button, as the language
choice already did.

## happy-dom for interface tests, 19 November 2026

Vitest ran the interface tests without a DOM, so no test could press Enter or
click a button, and the keyboard rules of the section “Interface clarity”
below had no proof. happy-dom 21 (MIT, transitive packages MIT and BSD-2-Clause)
is a development dependency for that, recorded under `[[development]]` in
[`licenses/policy.toml`](../licenses/policy.toml). It is chosen over jsdom
for its smaller tree; a test file opts in with
`// @vitest-environment happy-dom`, every other test keeps the Node
environment. Nothing of it is shipped.

## Output folder `Ausgabe`, 19 November 2026

Settings has one folder setting instead of two. Choosing the watched folder
creates its subfolder `Ausgabe` when it is missing, or uses the one there as
it is, and approved jobs are written there as job files and GDV files
This follows the points the owner found in
the real application on 19 November 2026: one folder to choose, and what
leaves lies next to what came in. The inbox never reads `Ausgabe`, compared without regard to case because
Windows and macOS do not distinguish it: what Substrakt writes is no scan
and must not become an entry or a customer. A foreign file is never
replaced: a file named `Ausgabe` refuses the choice with
`output-name-taken`, a link named `Ausgabe` is refused with
`path-not-allowed`, and a taken job file name fails the job with
`hand-over-name-taken`.

The owner decided on 19 November 2026 that the files in the former
`Ausgabe` stay where they are when the watched folder changes; nothing is
moved or deleted, because the application removes a file of the hand-over
only when a person deletes its entry, never because a setting changed. A hand-over folder stored by an older version is ignored;
a job written there keeps its stored path, so deleting its entry still
removes the job file. Settings names the structure of the active profile in
one line, „Ordnerstruktur: Kundenname/Belege“; the contract says
„Kundenname/Dokumente“, but the word gate forbids „Dokument“ on screen, so
the owner chose „Belege“ on the same day.
