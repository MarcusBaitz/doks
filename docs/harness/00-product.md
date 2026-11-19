# Product and status

Status: 2026-11-19

This file applies to every change to Substrakt. It places a task within the
product, its promises and its development stages; the source documents are
listed in [`docs/README.md`](../README.md) and are not copied here.

## What Substrakt is

Substrakt is a cross-platform desktop application for intelligent document
extraction. It runs entirely locally and is meant for clerks, not developers.
The target hardware is a standard laptop with 16 GB RAM and no GPU; Windows,
macOS and Linux are supported.

A technical decision that needs a GPU, an external service or developer
knowledge in daily use therefore misses the target profile. This is not an
optimisation for later but the yardstick for every stage.

## The two promises

The binding wording is in [`docs/decisions.md`](../decisions.md):

**1. Nothing leaves the infrastructure.** No document content, no model
call, no telemetry. In case of doubt this promise beats every other
requirement, including convenience and accuracy. If a requirement collides
with it, locality wins, and the conflict is named explicitly instead of being
quietly built around.

**2. Fully permissive licences.** This applies to code *and* model weights
alike. An Apache-2.0 library that loads a CC-BY-NC model is a violation.
Enforced through [`licenses/policy.toml`](../../licenses/policy.toml).

The egress gate in `eslint.config.js`, `sidecar/pyproject.toml` and
`scripts/check-egress.sh` enforces the first promise. The licence gate in
`scripts/check-licenses.py`, `licenses/policy.toml` and `src-tauri/deny.toml`
enforces the second. Both are product properties, not style rules.

## Development stages

| Stage | Content | Status |
|---|---|---|
| 0 | Measurements of OCR, VLM and server throughput | completed 28 July 2026; protocols under `docs/measurements/` |
| 1 | Foundation: parser, coordinates, viewer, sidecar and gates | completed 28 July 2026 |
| 2 | Normalisation, extractors, grounding, confidence, field sets in SQLite, Tesseract OCR and manual values | completed 28 July 2026 |
| — | Design language v2: four places instead of a workbench, colour and word gate | done 30 July 2026 |
| — | Document types as YAML files; the core has no invoice knowledge in code | done 15 October 2026 |
| — | Preparation for public release: licence, project files, English documentation, English code, customer material split into a private repository | in progress since 15 October 2026; see `docs/release-readiness.md` |
| — | Broker pilot: watched folder, inbox, review with approval, hand-over as a GDV file | in progress since 10 November 2026 |
| 3 | LLM integration with llama.cpp, template recognition and folder watching | open; the pilot takes folder watching and rule-based kind recognition out of it |
| 4 | Export, batch, installer and air-gap CI test | open |

The next product stage is therefore stage 3. A task may implement open points
of that stage if its brief names them; it must not treat their mere absence
as a regression.

## Broker pilot

A first pilot runs with an insurance broker. The clerk puts scanned
policies, contract changes and premium invoices into a folder per customer;
the application reads them, the clerk corrects and approves, and the
approved contracts leave as a GDV file that the broker's management program
reads with its own import. A person imports that file; nothing operates
another program by remote control.

Which program receives the file is set in a pipeline profile, not in code.
The core ships one neutral example profile, `insurance_folder.yml`, whose
target has no writer. The customer's material (its profile, its goal
contracts, its research and the screenshots of its walk-throughs) lives in a
private repository and is installed into the data directory
(`docs/configuration.md`, section “Customer setup”). No file of the core
names the customer or its target program, and the public state is produced
as described in `docs/release-readiness.md`.

Built so far, in the sidecar only: a chosen folder is watched, every document
in it is read once with its kind recognised and kept as an inbox entry across
restarts, and a pipeline profile says which folder level names the customer.
A person's corrections are stored with the entry, an approval creates exactly
one job, and the job queue stores every transition. An approval and a
release record the account of the person, an entry can be deleted with
everything that hangs on it, and entries whose job is done go after a
retention period. A job becomes done only when a person reports on Overview
that the import of its customer's file worked, so retention deletes only what
a person confirmed. A document with the identifying values of one already
read is marked as a possible duplicate and waits for a person's decision.
Settings chooses the watched folder, whose subfolder `Ausgabe` receives the
hand-over, the way of working and the retention period; Overview shows one
entry per import with its customers, documents, later arrivals and
duplicates while it fills. Review shows one waiting entry at a time: the
document, the recognised kind, which a person can change, the one value that
is open, and the approval; for a possible duplicate both documents side by
side and the decision first. Templates lists the kinds the watched folder
reads and lets a person rename, remove or add a value of a kind; the change
is written as an override file and applies from the next document read.
Overview leads to a simulation of the hand-over per customer and contract,
with every value a format refuses named before the run; one button starts
the run, and afterwards a person reports per customer whether the import
worked, done or failed with a reason. A failed hand-over is released again
and leads back to the simulation. The GDV writer with mapping tables and its
own read-back is connected to the job queue: for a profile with a block
`hand_over`, the approved jobs of one customer leave as one GDV file when a
run is started for that customer (`docs/gdv-hand-over.md`). The shipped
profile has no such block, because encoding, record separator and broker
number are facts only the broker and the vendor of the target program have;
its jobs end as failed with the reason that the target has no writer. No
file has been imported into a target program yet, and no text may claim
that one reads these files.

Outside the pilot, and not to be built along the way: an LLM path, any cloud
mode, matching against master data of the target program, splitting a scan
into several documents, the installer, and BiPRO delivery of the document.

## Deliberately open

- `src/api/types.ts` is maintained by hand. Generating it from `openapi.json`
  is still deliberately missing; new contracts must be kept in sync on both
  sides by hand until then.
- An LLM path and automatic template recognition are planned for stage 3.
  There is no LLM client yet on which new rules or supposed fixes could
  rely.
- Export, batch, installer and the full air-gap CI test belong to stage 4.
  Existing preparatory tables or endpoints do not change this product status.
- The tables `extraction_run`, `correction`, `export_profile`, `fingerprint`
  and `field_block` are created by the first migration and used by no
  application code. What a document opened by hand yields lives in the
  frontend's memory and is gone after a reload; only the inbox of the watched
  folder stores what it read.
- The egress chokepoint checks a target and returns it; no request is sent
  through it and no command calls it. Every attempt would be stored durably
  in `audit_log`, but since nothing calls the chokepoint the table stays
  empty in use.
- The switch to English is done for code, schema, scripts and
  documentation. German remains where `docs/harness/08-writing.md` keeps it:
  the German interface, synthetic sample content, the frozen evaluation
  corpus and the raw JSON files under `docs/measurements/`.

## Reading the sources

`README.md` is the entry point. `docs/decisions.md` holds the binding
decisions, `docs/design/design-language.md` the visible language, and
`docs/status.md` the lessons from stage 1.

`docs/status.md` is outdated in scope: stage 2, design language v2 and the
document type files are done. Its sections “What CI revealed”, “What the first start
revealed” and “Wrong assumptions” remain valid because they
document measured classes of failure and working rules.

Measurements are under `docs/measurements/`. Figures without a measurement
remain estimates; an estimate does not become a promise by repetition.
