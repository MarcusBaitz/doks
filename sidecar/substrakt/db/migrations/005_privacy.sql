-- Who approved, and what a deletion leaves behind.
--
-- The broker is promised a record of who approved and that a deleted entry
-- is gone. Both need a place in the schema.

BEGIN;

-- The operating-system account of the person, set on an approval and on the
-- release of a failed job; NULL where the application itself moved the job.
ALTER TABLE job_transition ADD COLUMN account TEXT;

-- The same for a correction. NULL for corrections stored before this
-- migration.
ALTER TABLE inbox_correction ADD COLUMN account TEXT;

-- A deleted entry leaves its path and hash and nothing else. The folder is
-- still watched, and without this row the file would be read again at the
-- next look. The row goes when the file itself is gone from that path.
CREATE TABLE inbox_deleted (
    file_path  TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    PRIMARY KEY (file_path, sha256)
);

COMMIT;
