# Job file format

Status: 2026-11-19

This document describes the file that the application writes into the
folder `Ausgabe` inside the watched folder for every approved document. The schema is generated from
the model `JobFile` in `sidecar/substrakt/jobs.py` and lies next to it as
`sidecar/substrakt/job.schema.json`; `tests/sidecar/test_jobs.py` rejects a
schema file that no longer matches the model and a key that this document
does not name.

## When a file is written

A job exists only after a person approved an inbox entry. An approval is
refused while a value that the profile expects for the kind is open or not
unambiguous. One approval creates one job; approving the same entry again,
or the same content under another entry, returns the first job.

The file is written into `Ausgabe`, the subfolder that choosing the watched
folder creates; it must be a plain folder, not a link, inside the read roots
of the session, and the inbox never reads it, so a job file never comes back
as a scan. While `Ausgabe` is missing or no plain folder, the job stays
pending. A file that already has the name `<id>.json` or `.<id>.json.tmp` is
foreign and is never replaced: the job ends as failed with the reason
`hand-over-name-taken`. The content goes into `.<id>.json.tmp` in the same
folder, is flushed and synced, and is then renamed to `<id>.json`. A reader
that takes `*.json` therefore never sees half a file. If writing fails, the
temporary file is removed and the job ends as failed.

The job file is not the hand-over format of a target. The target of the
profile chooses a writer that reads jobs and produces that format. A profile
with a block `hand_over` names its format there; its jobs stay pending until
a person starts a run for the customer, and the run writes the file of the
format and the job files together (`docs/gdv-hand-over.md`, section
“From approval to file”). A profile without the block has no writer: its job
ends as failed with the reason `target-without-writer` and no file is written.

## Version 1

The file is one JSON object in UTF-8. Unknown keys are not allowed.

| Key | Type | Content |
|---|---|---|
| `version` | integer | `1`. Raised when a key is added, removed or changes its meaning. |
| `id` | string | Unique id of the job, 32 hexadecimal characters. The file is named after it. |
| `idempotency_key` | string | SHA-256 over file hash, kind and values. Equal for the same approved content. |
| `approved_at` | string | Time of the approval, ISO 8601 with offset. |
| `profile` | string | Name of the pipeline profile the document was read with. |
| `target` | string | Target of that profile. It chooses the hand-over format. |
| `kind` | string | Document kind. |
| `customer` | string or null | Customer folder the file lay in; null outside a customer folder. |
| `file` | object | `path`: where the scanned file lies. `sha256`: its hash as it was read. The file is not copied. |
| `pages` | object | `first` and `last` page of the document in the file, counted from 1. |
| `values` | object | The approved values by their name in the target, as the profile maps them. Every value the profile requires is there; a value the profile lists as optional is there only when it was read unambiguously. |

Each entry of `values` is an object with `text`, the value as it stands on
the paper or as a person entered it, and `normalized`, an ISO date, a number
or cleaned text, or null when the value has no such form.

The settings of the hand-over format, the optional block `hand_over` of the
profile, are not copied into the job file. A writer loads the profile by the
name in `profile` and reads the block there, so a broker number or an
addressee stands in one place and a corrected profile reaches jobs that
already exist.

The file carries values, never document text or a page image. `pages` always
covers the whole file, because splitting a scan into several documents is
not built.

## Example

```json
{
  "version": 1,
  "id": "3f0c2a9d5b7e4c1a8d6f0b2e4a6c8e01",
  "idempotency_key": "9b1d…",
  "approved_at": "2026-11-10T14:03:21+01:00",
  "profile": "scans",
  "target": "test_target",
  "kind": "invoice",
  "customer": "Meier",
  "file": {
    "path": "/scans/Meier/policy.pdf",
    "sha256": "5e88…"
  },
  "pages": { "first": 1, "last": 1 },
  "values": {
    "Nummer": { "text": "2026-0147", "normalized": "2026-0147" }
  }
}
```

## States of a job

A job is in one of four states and moves only along these transitions:

| From | To | When |
|---|---|---|
| — | `pending` | A person approved the entry (`approved`). |
| `pending` | `handed_over` | The job file was written (`job-file-written`). |
| `pending` | `failed` | The target has no writer (`target-without-writer`), the file could not be written (`handover-write-failed`), or a hand-over run held the job back, failed its read-back or lacked settings (`hand-over-held-back`, `hand-over-read-back-failed`, `hand-over-settings-invalid`, each followed by what was missing). |
| `handed_over` | `done` | The hand-over was taken up by the target. |
| `handed_over` | `failed` | The target rejected it. |
| `failed` | `pending` | A person released the job again (`released`). |

Every transition is stored with its time and its reason in the table
`job_transition`; an approval and a release also store the account of the
person. Deleting an entry removes its job, its transitions, the job file and
the file of the hand-over format the job was written into. The job files of
the other jobs of that file are removed too, and those that are not done fail with the reason `hand-over-file-removed` and
wait for a person to release them. A failed job stays failed until a person releases it; the
queue retries nothing on its own. A pending job waits while no hand-over
folder is chosen. Nothing sets `done` yet: that call arrives with the screen
that shows jobs.
