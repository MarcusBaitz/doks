"""Move the egress attempts of the shell into the table ``audit_log``.

The Rust shell owns the egress chokepoint and appends every attempt, allowed
or refused, as one JSON line to a spool file in the data directory, synced at
the moment of the attempt. The database belongs to the sidecar, so the
sidecar takes the lines over: at start and at every look of the inbox loop.
The spool is renamed before it is read, so a line the shell appends meanwhile
lands in a new file and is taken next time.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from substrakt.db.session import Session

log = logging.getLogger(__name__)

# The name the shell writes; `AUDIT_FILE` in src-tauri/src/egress.rs.
SPOOL = "egress-audit.jsonl"
_TAKEN = "egress-audit.taken"


class Attempt(BaseModel):
    """One line of the spool, in the form `AuditEntry` of the shell has."""

    # Seconds since the epoch.
    occurred_at: int
    action: str
    target: str
    # What an INTEGER column of SQLite holds.
    bytes: int = Field(ge=0, le=2**63 - 1)
    result: Literal["allowed", "denied", "error"]
    mode: Literal["airgap", "onprem", "cloud"]


def _rows(file: Path) -> list[tuple]:
    """The lines of the spool as rows of ``audit_log``; a line that is none is skipped.

    A line torn by a crash, bytes that are no text, a time no calendar holds
    or a number SQLite cannot store must not keep the other lines out: the
    spool would stay behind and every later run would fail on it.
    """
    rows, skipped = [], 0
    for raw in file.read_bytes().splitlines():
        if not raw.strip():
            continue
        try:
            a = Attempt.model_validate_json(raw.decode("utf-8"))
            at = datetime.fromtimestamp(a.occurred_at, UTC).astimezone().isoformat()
            row = (at, a.action, a.target, a.bytes, a.result, a.mode)
            (a.action + a.target).encode("utf-8")  # a lone surrogate cannot be stored
        except (ValueError, OverflowError, OSError):
            # ValueError covers ValidationError and UnicodeError.
            skipped += 1
            continue
        rows.append(row)
    if skipped:
        # The count only: a line may hold a target.
        log.error("Egress audit: %d lines of the spool were unreadable and skipped", skipped)
    return rows


def ingest(db: Session, data_dir: Path) -> int:
    """Store the spooled attempts in ``audit_log``; return how many were stored.

    Never raises: the sidecar calls this at start, and a spool it cannot take
    must not keep the application from starting. What cannot be taken stays
    in the file for the next run.
    """
    taken = data_dir / _TAKEN
    try:
        # A file left by an interrupted run is finished before a new one is taken.
        if not taken.exists():
            (data_dir / SPOOL).replace(taken)
        attempts = _rows(taken)
        with db.transaction() as conn:
            conn.executemany(
                "INSERT INTO audit_log (occurred_at, action, target, bytes, result, mode) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                attempts,
            )
    except FileNotFoundError:
        return 0
    except Exception as exc:
        log.error("Egress audit: the spool could not be taken (%s)", type(exc).__name__)
        return 0
    # shortcut: an exit between the commit above and this line stores the same
    # attempts twice at the next start, never too few; give each line an id and
    # a unique column when a reader of the table needs exact counts.
    taken.unlink()
    return len(attempts)
