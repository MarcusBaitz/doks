# Architecture

Status: 2026-11-19

This file applies to changes to process boundaries, data flows, persistence,
coordinates and the directory structure. It condenses the architecture rules
from `README.md` and `docs/decisions.md` and names the gates that enforce
their boundaries. The diagram is in `docs/architecture/`.

## Three processes, one direction

```text
React frontend  ──invoke──▶  Rust shell  ──HTTP 127.0.0.1──▶  Python sidecar
   (no fetch)               (chokepoint)    (bearer token)
```

The frontend knows neither the random sidecar port nor the session token.
Every backend call goes through `src/api/client.ts`, a Tauri command in
`src-tauri/src/bridge.rs` and only then to the sidecar. This direction keeps
token, port and network policy out of the browser context.

The egress gate made of ESLint, Ruff and `scripts/check-egress.sh` rejects
direct network paths in frontend and sidecar. A convenient second path is
therefore not a helper module but a breach of the locality promise.

## Egress chokepoint and operating modes

Outbound traffic runs exclusively through `Egress::request` in
`src-tauri/src/egress.rs`. The local connection to the sidecar on
`127.0.0.1` is not egress and stays in `bridge.rs` and `sidecar.rs`.

- **Air-gap** is the default. Outbound connections are refused; the local
  sidecar remains reachable.
- **On-premise** additionally allows targets from an administratively
  maintained allowlist, including a vLLM server in the customer network.
- **Cloud** exists only after explicit unlocking. A machine-wide policy can
  narrow the mode; the user cannot widen it.

An inference server outside the customer network is not allowed in any mode.
`src-tauri/src/policy.rs` falls back to Air-gap when the policy is missing or
broken.

These modes are a design that the code carries only in part.
`Egress::request` checks a target against mode and allowlist and returns the
validated URL; it sends nothing, and no command calls it yet. Cloud has no
unlock mechanism, and nothing checks that an allowlisted host lies inside the
customer network. The first outbound call must close both before it is built.

Every allowed and every refused attempt must be stored durably, because the
promise has to be provable. The shell appends each attempt as one JSON line
to the spool file `egress-audit.jsonl` in the data directory and syncs it
before `Egress::request` returns; an attempt that cannot be written stays in
memory and is written with the next one. The sidecar owns the database and
moves the lines into the table `audit_log`, at start and at every look of the
inbox loop (`sidecar/substrakt/audit.py`). A file was chosen over a call to
the sidecar because it is durable at the moment of the attempt, also while
the sidecar is not running. The shell records `allowed` and `denied`, the
words the table accepts; a Rust test reads the CHECK from the migration, and
a fixture shared by a Rust and a Python test holds the form of a line.

## Coordinates

Rectangles are always stored in document coordinates, never in screen
pixels. Only then do locations stay on the same document point under zoom,
window scaling, retina ratio and rotation.

The conversion lives in exactly two places:

- `sidecar/substrakt/parsers/pdf.py` converts pdfplumber coordinates into
  PDF points.
- `src/viewer/coords.ts` converts document coordinates for display.

Both sides are checked against `tests/sidecar/fixtures/coordinates.json`:
Python in `tests/sidecar/test_coordinates.py`, TypeScript in
`tests/frontend/coords.test.ts`. This coordinate gate rejects diverging
formulas. A third conversion site or stored screen pixels would bypass the
shared safeguard.

## Persistence

SQLite persists document types, field definitions, the entries of the
inbox with their corrections, the jobs with their transitions, and the
egress attempts of the shell. The migrations are under `sidecar/substrakt/db/migrations/` and are
applied in order through `PRAGMA user_version`. An inbox entry holds what a
document from the watched folder yielded: values with locations, never text
or images. The table `extraction_run` and five further prepared tables exist,
but no code reads or writes them; what a document opened by hand yields still
lives in the frontend's memory.

Loaded documents and their contents stay exclusively in the memory of
`sidecar/substrakt/store.py`. That keeps the data trail small and is part of
the locality promise. A new file store for document contents therefore needs
an explicit architecture decision, not just a new table.

## Job and hand-over boundary

The broker pilot adds persistence and a way out, and both have a fixed
boundary. The decision is in `docs/decisions.md`, section “Broker pilot
architecture”. The watched folder, the inbox and the pipeline profile exist
in the sidecar, and so do corrections, approval and the job queue. The
writer of a hand-over format is not built yet; the format of the job file
is in `docs/job-format.md`.

- **An inbox entry and a job store values, not content.** State, file path,
  SHA-256, document kind, values with their locations, corrections and step
  timings go into SQLite. Document text and page images do not; the file
  stays where the scanner put it. A column that holds text or an image would
  reverse the rule above and needs the owner's decision.
- **The job record separates reading, review and hand-over.** Reading ends in
  an inbox entry, review in an approval, and an approval creates exactly one
  job. The writer of a hand-over format reads only jobs, so nothing that no
  person approved can leave.
- **The hand-over is a folder, not a connection.** Approved jobs are written
  as files into the subfolder `Ausgabe` of the watched folder, inside the
  read roots and in the customer network; the inbox never reads it, so what
  Substrakt writes never comes back as a scan, and a foreign file there is
  never replaced. The
  sidecar still binds to `127.0.0.1` and opens no network path; a listener, a
  client or an upload for the hand-over would be a second way around the
  egress chokepoint, and both egress gates would have to reject it.
- **Nothing operates another program.** A person imports the file in
  the target program. An agent, a VM or automation of a foreign interface is not part
  of the architecture.
- **Knowledge about the target lives in a profile file.** Folder structure,
  expected values and the target stand in a pipeline profile built like a
  document kind file; a target name in Python, Rust or TypeScript outside the
  writer of that format would undo the separation, as a document-kind term in
  code does.

Document kinds are not database rows but YAML files under
`sidecar/substrakt/document_kinds/`, overridable by files of the same name in
`<data dir>/document_kinds/`. They hold the domain knowledge of a kind (values,
labels, titles, legal forms) so that the core gets by without invoice
knowledge in code. The assistant's templates stay in SQLite; the distinction
is in `docs/decisions.md`, section “Document kinds as YAML files”. A
document-kind term in Python code instead of in the YAML file would undo this
separation.

## Hard architecture rules

**No model name is hard-coded.** Models are meant to be swappable;
repository, revision, SHA-256, licence and licence URL belong in a later
registry entry, and not in a document-kind file either; its schema rejects
unknown keys. The registry itself is planned for stage 3 and not built yet.

**No quantisation method is hard-coded.** GGUF locally and
compressed-tensors or AWQ on the server are properties of a later registry
entry. Otherwise a technical packaging would couple the entire execution
path.

**No PyTorch in the bundle.** The target device has no GPU, and PyTorch
would add about 1.5 to 4 GB for the framework alone. The licence gate lists
`torch`, `torchvision` and `torchaudio` as forbidden by name; ML runs on ONNX
Runtime or llama.cpp.

**No network access in standard operation.** Models, fonts, updates,
telemetry and crash reports are not fetched at runtime. Shell and CI set
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; the egress gate rejects
additional paths.

## Directory map

```text
src/                    React frontend
  App.tsx               entry and switching between the four places
  places/               Overview, Review, Templates, Template view,
                        Settings and the assistant with its steps
  shell/Sidebar.tsx     navigation between places
  ui/                   shared components and formatting
  viewer/               viewer, overlays and coords.ts
  api/                  Tauri client and hand-written types
  i18n/                 German and English texts, context and language storage
  design/               tokens.css and theme
  state/session.ts      session state
  results/save.ts       saving results
src-tauri/src/          Rust shell
  lib.rs                start-up, state and plugins
  sidecar.rs            start, handshake, read roots and stdin watchdog
  bridge.rs             Tauri commands and local sidecar bridge
  egress.rs             the only chokepoint for outbound traffic
  policy.rs             machine-wide policy
sidecar/substrakt/      Python backend
  app.py                FastAPI endpoints
  config.py             token, read roots and limits
  errors.py             problem+json with a stable key
  model.py              document model
  store.py              loaded documents, in memory
  parsers/              PDF, images, spreadsheets and OCR
  index/words.py        word bounding-box index
  extraction/           fields, extractors, normalisation, grounding and
                        generic label search
  inbox.py              watched folder, poll loop, persisted entries and
                        corrections
  jobs.py               approval, job queue, transitions, the job file,
                        deletion and retention
  audit.py              egress attempts of the shell into audit_log
  yaml_model.py         reading of kind and profile files, schema files
  pipeline_profiles/    one YAML file per pipeline: folder level of the
                        customer, kinds, expected values and target
  hand_over.py          hand-over runs per customer between job queue and
                        the writer of a format
  gdv/                  writer and independent reader of the GDV hand-over
                        format, mapping tables as YAML under tables/
  document_kinds/       one YAML file per document kind, schema, loader and
                        parser/ for at most one custom parser per kind
  db/                   migrations, persisted types and the shared session
tests/frontend/         Vitest including coordinates and the four places
tests/sidecar/          pytest and the shared coordinate fixture
corpus/                 synthetic test corpus; never commit corpus/echt/
bench/run.py            performance budgets
licenses/policy.toml    licence rules as single source of truth
docs/                   documentation, decisions, status, design,
                        measurements and plans
  contracts/            goal contracts of the core, when there are any;
                        a customer's contracts live in its private
                        repository
models/                 local model weights; not in the repository
```
