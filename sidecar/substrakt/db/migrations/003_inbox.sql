-- Inbox of the watched folder.
--
-- The broker pilot reads every document that arrives in a chosen folder and
-- keeps what it found across restarts. An entry stores where the file lies,
-- its SHA-256 and the values with their locations. It stores no document
-- text and no page image: the file stays where the scanner put it.
--
-- extraction_run from migration 001 was not reused: it has no state, no
-- path, no customer and no reference to a first entry, and it points to a
-- template (document_type), not to a document kind. The watched folder and
-- the chosen profile use the prepared key-value table app_setting.

-- One row each time the clerk chooses a folder. Everything found before
-- finished_at is set belongs to that import; what arrives afterwards is a
-- later arrival.
CREATE TABLE inbox_import (
    id          INTEGER PRIMARY KEY,
    folder      TEXT    NOT NULL,
    started_at  TEXT    NOT NULL,
    finished_at TEXT
);

CREATE TABLE inbox_entry (
    id            INTEGER PRIMARY KEY,
    import_id     INTEGER NOT NULL REFERENCES inbox_import(id) ON DELETE CASCADE,
    -- new: found and being read. waiting: read, waits for a person.
    -- duplicate: content already known, not read. error: could not be read.
    state         TEXT    NOT NULL CHECK (state IN ('new','waiting','duplicate','error')),
    file_path     TEXT    NOT NULL,
    sha256        TEXT    NOT NULL,
    -- NULL when the file lies outside a customer folder.
    customer      TEXT,
    -- The profile the entry was read with; later changes do not reach it.
    profile       TEXT    NOT NULL,
    -- NULL when no kind was recognised.
    kind          TEXT,
    -- Extracted values with their locations, a JSON list.
    values_json   TEXT    NOT NULL DEFAULT '[]',
    -- Milliseconds per step, a JSON object.
    timings_json  TEXT    NOT NULL DEFAULT '{}',
    -- The first entry with the same content, for state duplicate.
    duplicate_of  INTEGER REFERENCES inbox_entry(id) ON DELETE SET NULL,
    -- Stable problem key, for state error.
    problem_key   TEXT,
    later_arrival INTEGER NOT NULL DEFAULT 0 CHECK (later_arrival IN (0, 1)),
    arrived_at    TEXT    NOT NULL,
    -- A file is known by where it lies and what it contains.
    UNIQUE (file_path, sha256)
);

CREATE INDEX idx_inbox_sha    ON inbox_entry(sha256);
CREATE INDEX idx_inbox_import ON inbox_entry(import_id);
