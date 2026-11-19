"""One SQLite connection that several threads of one component share.

The inbox loop writes while requests read and approve, so every statement
runs under one lock. A connection of its own per component would work too,
but an approval changes an entry and creates a job in one transaction, and
that needs both on the same connection.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from substrakt.db.migrate import open_database


class Session:
    def __init__(self, database: Path) -> None:
        self._conn = open_database(database)
        self._lock = threading.Lock()

    def query(self, sql: str, *arguments: object) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, arguments).fetchall()

    def write(self, sql: str, *arguments: object) -> int:
        """Run one statement in its own transaction and return the new row id."""
        with self.transaction() as conn:
            return conn.execute(sql, arguments).lastrowid or 0

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Several statements that are stored together or not at all."""
        with self._lock, self._conn:
            yield self._conn

    def close(self) -> None:
        with self._lock:
            self._conn.close()
