# Changelog

All notable changes to Substrakt are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Substrakt has no
released version yet; the manifests carry `0.1.0` as a placeholder. Until the
first release, changes are grouped by development stage.

## [Unreleased]

### Changed

- The application ships one neutral example way of working,
  `insurance_folder.yml` with the target „Beispielziel“, instead of the
  profile of the first pilot customer. A customer's profile, kinds and GDV
  tables are copied into the data directory (`docs/configuration.md`,
  section “Customer setup”); `npm run walk-through` takes another profile
  from `WALK_THROUGH_PROFILE`.
- Every selection (the filters on Overview, „Erkannt als“ in Review, the way
  of working and the retention period in Settings) takes its colours from the
  theme, so an opened list is readable in the dark theme too.
- In „Weitere Angaben“ every value that still waits for a look carries a „?“
  in the warn colour where a settled value has its ✓; both marks have a label,
  so the state does not rest on colour alone.
- The frame on the page is always the one the question speaks of: a click on
  another row no longer leaves the question over a foreign frame, and a value
  without a place in the document says so instead of pointing to a mark.
- A date is typed as digits and the points are set by themselves; an
  impossible or incomplete date is not sent, and a hint beside the field names
  the form TT.MM.JJJJ while the typed text stays.
- Every value in „Weitere Angaben“ can be corrected in its own row: a click
  opens an input with the current value, Enter saves only that row, Escape
  closes it unchanged. When the corrections in the rows settle every open
  value, „Beleg freigeben“ is enabled.
- Settings has one folder: choosing the watched folder creates its subfolder
  `Ausgabe`, and job and hand-over files are written there. The separate
  hand-over folder and its line in Settings are gone. `Ausgabe` is never read,
  so nothing Substrakt writes becomes an entry or a customer. An existing
  `Ausgabe` is used as it is, a file named `Ausgabe` refuses the folder with
  the reason beside the folder line, and a foreign file in `Ausgabe` is never
  replaced. After a change of folder, the files in the old `Ausgabe` stay.
- Settings says less: the subtitle „Wenig zu tun — das ist Absicht.“ is gone,
  and under „Arbeitsweise“ one line „Ordnerstruktur: Kundenname/Belege“
  replaces the lines for the customer, every kind and the target.
- „Ordner einlesen“ on Overview opens the question „Welcher Ordner soll
  eingelesen werden?“ instead of jumping to Settings: it describes the way of
  working in words, names the chosen folder, and „Einlesen starten“ leads back
  to Overview, which shows the reading. Esc and the back link leave without
  storing anything.
- Every line of Settings takes effect when it is changed; the button
  „Einstellungen speichern“ is gone. „Gespeichert.“ appears beside the changed
  line, and the page is titled „Einstellungen“ like the sidebar.
- The place „Vorlagen“ is now „Belegarten“ (“Document kinds”) and lists only
  the kinds of the watched folder. The path for documents read by hand (setup
  assistant, „Von Hand gelesen“, „Ergebnis sichern“ and its review screen) is
  hidden; its code stays for stage 3. Leaving a kind with unsaved changes asks
  first, and Settings says „Arbeitsweise“ instead of „Profil“.
- Overview says „Alles läuft“ only while nothing failed; otherwise the status
  line names the documents with an error in the warn colour. The three count
  tiles are gone: the waiting count stands once in the headline, whose button
  is the next step. Every document row opens across its whole width, a waiting
  one in Review and any other read-only below the row, and an import card shows
  only the last folder name.
- „Prüfen“ asks for a look at every unclear value: „Beleg freigeben“ stays
  disabled until each one was confirmed or corrected, and Enter settles only
  the active value, never the document. Selecting a value zooms the document
  to the text column of its place. A document without a recognised kind offers the kinds in the
  panel with „Damit lesen“, and the other values are headed „Weitere
  Angaben“ instead of „Alles Übrige wurde sicher erkannt“.
- The same keys work on every place: Enter presses the one dark button and
  Escape goes back to Overview, from a kind back to „Belegarten“. Enter never
  approves a document and never decides that it is the same as one read
  before; that takes a click or the focused button. Every input and selection
  shows its focus ring, and each subtitle under a heading is one sentence.

### Added

- `npm run walk-through` prepares a throwaway watched folder with synthetic
  documents for three customers and a data directory with a synthetic
  hand-over profile, and starts the application against them, so that a
  person can walk the pilot path in the real window
  (`docs/development.md`, section “Walk-through”).
- Hand-over of the broker pilot: Overview leads to a simulation that shows per
  customer and contract what would be handed over and from which document,
  naming every refused value before the run; one button writes the files.
  Afterwards a person reports per customer whether the import worked, and a
  failed hand-over can be released again. Amounts on Overview carry the
  currency.
- Overview and Settings of the broker pilot: Settings chooses the watched
  folder, the profile, the hand-over folder and the retention period and
  describes the active profile in plain words; Overview shows one entry per
  import with customers, documents, later arrivals and duplicates while it
  fills, and its counts run like an odometer.
- Templates lists the kinds of documents the watched folder reads, and a
  clerk renames, removes or adds a value of a kind there. The change is
  stored as an override file beside the shipped kind and applies from the
  next document read, without a restart; values already read stay as they
  are.
- `LICENSE` (Apache-2.0), `NOTICE`, `SECURITY.md`, `CONTRIBUTING.md`, this
  changelog, `.editorconfig`, and issue and pull request templates.
- Release readiness report in `docs/release-readiness.md`.
- Architecture diagram in `docs/architecture/`, as SVG with a Mermaid source.
- Synthetic evaluation corpus `corpus/evaluation/v1` (84 PDFs, Git LFS) and a
  reproducible comparison with a cloud OCR service on that corpus.
- `npm start` sets up the development environment, fetches models and starts
  the app in one command.
- Document kinds are described in YAML files; the core has no invoice
  knowledge in code.
- Document kinds for insurance policies, contract changes and premium
  invoices. The kind of a document is recognised from the rules in these
  files; a document that fits no kind or two kinds goes to review.
- A synthetic corpus of insurance documents with ground truth
  (`npm run corpus`) and an evaluation that fails on a wrong value without a
  review flag (`bench/insurance_kinds.py`).
- A writer for GDV files (`sidecar/substrakt/gdv/`): approved policies and
  premium invoices of one customer become one file, codes come from mapping
  tables kept as files, and every file is read back before it gets its name.
  For a profile with a block `hand_over`, approval refuses a document the
  file could not take, and a run per customer writes the file
  (`POST /jobs/hand-over`). No screen starts it yet. See
  `docs/gdv-hand-over.md`. After an independent review of a written
  file the key field carries the policy number without special characters,
  as the record tables require, and `bench/gdv_sample.py` writes a file for
  the next review.
- Policies and contract changes read the annual premium as a value of its
  own, `annual_premium`; `premium` is the amount per payment period.
- `npm run bench` reports the time per step from file to reviewable result.
- English interface, switchable under Settings → Language; German stays the
  default.
- `tests/frontend/places.test.tsx` checks the word list in both languages and
  rejects German copy in the English interface.
- Broker pilot: architecture decision in `docs/decisions.md`.
- The licence gate checks the model repositories named in
  `scripts/fetch-models.sh` against the policy; Gemma 4 weights are admitted
  as Apache-2.0, Gemma 3, 3n and older stay forbidden.
- Watched folder in the sidecar: a chosen folder is read once per document
  and kept as an inbox across restarts, duplicates by content are recognised
  and not read again. No screen uses it yet.
- Pipeline profiles as YAML files, overridable in the data directory, with a
  shipped profile for the broker pilot.
- Corrections, approval and a job queue in the sidecar: corrections are
  stored with the inbox entry, an approval is refused while a required value
  is open or unclear and otherwise creates exactly one job, and every change
  of a job's state is stored. The job file format is documented in
  `docs/job-format.md`. No screen uses it yet, and no hand-over format
  is written yet.
- The watched folder recognises the kind of each document among the kinds of
  the active profile.
- Review shows the entries of the watched folder that wait for a person:
  the document, the recognised kind, which can be changed, one open value at
  a time with its place on the page, and the approval. A possible duplicate
  is shown next to the document read first and is decided before it can be
  approved. A refusal shows its reason and the entry as it stands now.
  „Stimmt so“ confirms a value as read: it keeps its place on the page and
  does not count as changed by a person. „vergleichen“ on Overview opens
  exactly that entry beside the document read first; a file with the same
  content is shown beside it with nothing to decide.
- An inbox entry can be deleted with its values, corrections, job and job
  file; the scanned file only on request. Entries whose job is done are
  deleted after a retention period, 90 days unless set otherwise. A job is done
  only when a person reports that the import of its file worked.
- Every approval, every release of a failed job and every correction
  records the operating-system account and the time.
- Egress attempts are stored durably in the audit table and survive a
  restart.
- A pipeline profile can list optional values; the shipped profile no longer
  waits for a premium a policy does not print.
- Deleting an entry, by hand or by retention, also removes the GDV file
  that holds its contract; the other contracts of that file wait to be
  handed over again.
- A document with the same identifying values as one already read, but
  other file content, is marked as a possible duplicate. It is read as
  usual and cannot be approved until a person has decided whether it is the
  same document. Each kind file names its identifying values.
- A document decided to be the same as one already read keeps none of
  its values or corrections; the decision cannot be taken back.
- Half-written files that a crash left in the hand-over folder are
  removed at start and when the folder is chosen.

### Changed

- Overview lists the read documents newest first with the customer name
  bold, shows three documents per customer with a link to all of them, and
  never hides one that waits for a person. A period filter („Zuletzt
  eingelesen“, 3 days, 1 week, 1 month, 3 months) replaces the filter by
  customer and works together with the state filter and the search.
- The documentation no longer claims that extraction runs are stored or that
  egress attempts are logged durably; neither is built yet.
- Documentation, agent rules, code, database schema, API and error keys,
  scripts, licence policy and CI are English; the interface stays German by
  default.
- Renamed commands and settings: `npm run corpus` (was `korpus`),
  `scripts/start.sh --fresh` (was `--neu`), `SUBSTRAKT_MODE` (was
  `SUBSTRAKT_MODUS`), policy keys `mode` and `inference_server`, and the CI
  job `licenses`.
- granite-docling is downloaded from a pinned Hugging Face revision instead
  of `main`.
- Ambiguous field assignments now require review instead of being accepted
  silently.

### Fixed

- Overview offers the hand-over, the report of the import and the release
  of a failed hand-over while other documents still wait, as links below the
  count of approved documents; before, a contract change that waits for good
  hid them.
- A refused approval names why the document cannot be handed over, for
  example an insurer or payment mode without an entry in the table, instead
  of only saying that it cannot.
- Moving to the next document in Review no longer shows the error that the
  document is no longer open, and no error text starts with the name of a
  program class.
- Deleting an entry while its customer's hand-over was being written could
  leave the written file behind; the deletion now waits for the hand-over.
- In development mode the sidecar log no longer contains the text of PDF
  documents: libraries are kept at INFO.
- A value confirmed in review although no location was found is now part of
  the saved result; before, it was left out without notice.
- The application stays responsive while a scanned document is being read.
- On Windows the sidecar's check for its parent process no longer ends the
  application.
- Ruff now really rejects network libraries in the sidecar; the ban had been
  configured but inactive.
- The status recorded for a refused outbound attempt is one the audit table
  accepts.
- One file in the watched folder can no longer stop the reading of all
  others: a name that is no valid text, a link out of the allowed folders, a
  file that is too large or has too many pages, and a file whose reading was
  interrupted each become an entry marked as an error.
- A damaged line in the record of outbound attempts no longer keeps the
  application from starting; the line is skipped and the others are stored.

### Removed

- `samples/transportschein-aok.pdf`, a scanned official form with fictitious
  data that no code used.

## Design language v2 — 30 July 2026

### Changed

- The interface is organised as four places (Overview, Review, Templates,
  Settings) instead of one workbench; setting up a template is a guided path.
- Colour gate: components use semantic tokens from `src/design/tokens.css`.
- Word gate: technical terms stay out of the four everyday screens.

## Stage 2 — 28 July 2026

### Added

- Normalisers and German extractors for amounts, dates, VAT IDs and IBANs.
- Grounding and confidence for every extracted value.
- Field sets persisted in SQLite.
- Tesseract OCR for pages without a text layer.
- Manual values where no recognition can read the document.

## Stage 1 — 28 July 2026

### Added

- Tauri v2 shell, Python sidecar on `127.0.0.1` with session token and stdin
  watchdog, and the egress chokepoint `Egress::request` with Air-gap as
  default.
- PDF parser and coordinate conversion, checked on both sides against one
  shared fixture.
- Document viewer with overlays.
- Egress, licence, colour and coordinate gates in CI.

### Fixed

- Path checks were ineffective because the started sidecar received no read
  roots; image overlays did not rotate with the page.

## Stage 0 — 28 July 2026

### Added

- Measurements of OCR, a document VLM on CPU, and server throughput,
  recorded under `docs/measurements/`.
