-- Possible duplicates by read values.
--
-- The same paper scanned twice gives two files with different content, which
-- the comparison by SHA-256 does not catch. A kind file names the values
-- that identify a document of that kind. An entry whose values equal those
-- of another entry is read normally and marked; a person decides whether it
-- is the same document, because a read value can be wrong.

BEGIN;

-- SHA-256 over kind and comparison values. NULL when the kind names none or
-- one of them was not read unambiguously. A hash, so that this column is no
-- second place that holds the values.
ALTER TABLE inbox_entry ADD COLUMN comparison_key TEXT;

-- The other entry with the same comparison key; the mark of a possible
-- duplicate. It ends when that entry is deleted.
ALTER TABLE inbox_entry ADD COLUMN possible_duplicate_of INTEGER
    REFERENCES inbox_entry(id) ON DELETE SET NULL;

-- What a person decided about the mark, by whom and when. NULL while open.
ALTER TABLE inbox_entry ADD COLUMN duplicate_decision TEXT
    CHECK (duplicate_decision IN ('same', 'new'));
ALTER TABLE inbox_entry ADD COLUMN duplicate_decided_by TEXT;
ALTER TABLE inbox_entry ADD COLUMN duplicate_decided_at TEXT;

CREATE INDEX idx_inbox_comparison ON inbox_entry(comparison_key);

COMMIT;
