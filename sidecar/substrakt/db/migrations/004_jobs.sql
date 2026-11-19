-- Corrections, approval and the job queue.
--
-- Review ends in an approval by a person, and an approval creates exactly one
-- job. A job stores the approved values under the names of the target, never
-- document text or a page image. The writer of a hand-over format reads only
-- this table, so nothing that no person approved can leave.
--
-- Everything that hangs on an inbox entry references it with ON DELETE
-- CASCADE: deleting the entry removes its corrections, its job and the
-- transitions of that job.

BEGIN;

-- SQLite cannot change a CHECK, so inbox_entry is rebuilt with the new state
-- approved and the page count that a job needs for its page range.
CREATE TABLE inbox_entry_new (
    id            INTEGER PRIMARY KEY,
    import_id     INTEGER NOT NULL REFERENCES inbox_import(id) ON DELETE CASCADE,
    -- new: found and being read. waiting: read, waits for a person.
    -- approved: a person approved it and a job exists.
    -- duplicate: content already known, not read. error: could not be read.
    state         TEXT    NOT NULL
                  CHECK (state IN ('new','waiting','approved','duplicate','error')),
    file_path     TEXT    NOT NULL,
    sha256        TEXT    NOT NULL,
    -- NULL when the file lies outside a customer folder.
    customer      TEXT,
    -- The profile the entry was read with; later changes do not reach it.
    profile       TEXT    NOT NULL,
    -- NULL when no kind was recognised.
    kind          TEXT,
    -- NULL for an entry that was read before this migration or not at all.
    page_count    INTEGER,
    -- Extracted and corrected values with their locations, a JSON list.
    values_json   TEXT    NOT NULL DEFAULT '[]',
    -- Milliseconds per step, a JSON object.
    timings_json  TEXT    NOT NULL DEFAULT '{}',
    -- The first entry with the same content, for state duplicate. It names
    -- the new table: a reference to the old one would be set to NULL when
    -- that is dropped, and the rename below carries this one along.
    duplicate_of  INTEGER REFERENCES inbox_entry_new(id) ON DELETE SET NULL,
    -- Stable problem key, for state error.
    problem_key   TEXT,
    later_arrival INTEGER NOT NULL DEFAULT 0 CHECK (later_arrival IN (0, 1)),
    arrived_at    TEXT    NOT NULL,
    -- A file is known by where it lies and what it contains.
    UNIQUE (file_path, sha256)
);

INSERT INTO inbox_entry_new (
    id, import_id, state, file_path, sha256, customer, profile, kind, values_json,
    timings_json, duplicate_of, problem_key, later_arrival, arrived_at
)
SELECT id, import_id, state, file_path, sha256, customer, profile, kind, values_json,
       timings_json, duplicate_of, problem_key, later_arrival, arrived_at
FROM inbox_entry ORDER BY id;

DROP TABLE inbox_entry;
ALTER TABLE inbox_entry_new RENAME TO inbox_entry;

CREATE INDEX idx_inbox_sha    ON inbox_entry(sha256);
CREATE INDEX idx_inbox_import ON inbox_entry(import_id);

-- What a person changed on an entry. The entry holds the current values;
-- this table keeps what stood there before. Who changed it is added with
-- criterion Z6.5.
CREATE TABLE inbox_correction (
    id           INTEGER PRIMARY KEY,
    entry_id     INTEGER NOT NULL REFERENCES inbox_entry(id) ON DELETE CASCADE,
    -- Name of the corrected value; NULL when the document kind was corrected.
    value_name   TEXT,
    before       TEXT,
    after        TEXT    NOT NULL,
    corrected_at TEXT    NOT NULL
);

CREATE INDEX idx_correction_entry ON inbox_correction(entry_id);

CREATE TABLE job (
    -- A random id, so that a deleted job never lends its file name to a new one.
    id              TEXT    PRIMARY KEY,
    -- One approval, one job.
    entry_id        INTEGER NOT NULL UNIQUE REFERENCES inbox_entry(id) ON DELETE CASCADE,
    -- SHA-256 over file hash, kind and approved values: the same content
    -- approved again finds this row instead of creating a second job.
    idempotency_key TEXT    NOT NULL UNIQUE,
    state           TEXT    NOT NULL
                    CHECK (state IN ('pending','handed_over','done','failed')),
    -- The job file as JSON; its schema is docs/job-format.md.
    file_json       TEXT    NOT NULL,
    -- Where the job file was written; NULL until it was handed over.
    handover_path   TEXT
);

-- Every change of state, including the creation (from_state NULL).
CREATE TABLE job_transition (
    id         INTEGER PRIMARY KEY,
    job_id     TEXT    NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    from_state TEXT,
    to_state   TEXT    NOT NULL,
    reason     TEXT    NOT NULL,
    at         TEXT    NOT NULL
);

CREATE INDEX idx_transition_job ON job_transition(job_id);

COMMIT;
