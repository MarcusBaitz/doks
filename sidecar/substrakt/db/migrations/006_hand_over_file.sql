-- The file of the hand-over format a job went into.
--
-- A hand-over run writes the jobs of one customer into one file, so several
-- jobs name the same path. Deleting an entry must remove that file too, and
-- only the stored path says which one it is.

BEGIN;

-- NULL until a run wrote the job, and again after the file was removed.
ALTER TABLE job ADD COLUMN format_file TEXT;

CREATE INDEX idx_job_format_file ON job(format_file);

COMMIT;
