"""Tests for db."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from substrakt.db import current_version, migrate, open_database
from substrakt.db.migrate import _steps

TABLES = {
    "document_type",
    "field",
    "field_block",
    "fingerprint",
    "extraction_run",
    "correction",
    "export_profile",
    "audit_log",
    "app_setting",
    "inbox_import",
    "inbox_entry",
    "inbox_correction",
    "job",
    "job_transition",
    "inbox_deleted",
}


def test_migrations_are_gapless() -> None:
    steps = _steps()
    assert steps, "At least one migration is required"
    assert [n for n, _ in steps] == list(range(1, len(steps) + 1))


def test_all_tables_created(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "test.db")
    try:
        existing = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert existing >= TABLES, f"Fehlend: {TABLES - existing}"
    finally:
        conn.close()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    conn = open_database(path)
    try:
        version = current_version(conn)
        assert version == len(_steps())

        assert migrate(conn) == version
        assert migrate(conn) == version
    finally:
        conn.close()

    
    conn = open_database(path)
    try:
        assert current_version(conn) == version
    finally:
        conn.close()


def test_inbox_migration_keeps_an_existing_database_and_runs_once(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    before_inbox = [file for number, file in _steps() if number <= 2]
    conn = sqlite3.connect(path)
    for file in before_inbox:
        conn.executescript(file.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO document_type (name, created_at, updated_at) "
        "VALUES ('Vorlage', '2026-10-15T10:00:00+02:00', '2026-10-15T10:00:00+02:00')"
    )
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    for _ in range(2):
        conn = open_database(path)
        try:
            assert current_version(conn) == len(_steps())
            assert [row["name"] for row in conn.execute("SELECT name FROM document_type")] == [
                "Vorlage"
            ]
            assert conn.execute("SELECT COUNT(*) FROM inbox_entry").fetchone()[0] == 0
        finally:
            conn.close()


def test_inbox_table_rejects_an_unknown_state_and_a_file_known_twice(tmp_path: Path) -> None:
    insert = (
        "INSERT INTO inbox_entry (import_id, state, file_path, sha256, profile, arrived_at) "
        "VALUES (1, ?, ?, 'abc', 'p', '2026-11-10T10:00:00+01:00')"
    )
    conn = open_database(tmp_path / "test.db")
    try:
        conn.execute(
            "INSERT INTO inbox_import (id, folder, started_at) "
            "VALUES (1, '/scans', '2026-11-10T10:00:00+01:00')"
        )
        conn.execute(insert, ("waiting", "/scans/a.pdf"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("vielleicht", "/scans/b.pdf"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("waiting", "/scans/a.pdf"))
    finally:
        conn.close()


def test_jobs_migration_keeps_the_entries_of_an_existing_inbox(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    for number, file in _steps():
        if number <= 3:
            conn.executescript(file.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO inbox_import (id, folder, started_at) "
        "VALUES (1, '/scans', '2026-11-10T10:00:00+01:00')"
    )
    insert = (
        "INSERT INTO inbox_entry (id, import_id, state, file_path, sha256, profile, kind, "
        "values_json, duplicate_of, arrived_at) "
        "VALUES (?, 1, ?, ?, 'abc', 'p', ?, ?, ?, '2026-11-10T10:00:00+01:00')"
    )
    conn.execute(insert, (1, "waiting", "/scans/a.pdf", "invoice", '[{"field": "n"}]', None))
    conn.execute(insert, (2, "duplicate", "/scans/b.pdf", None, "[]", 1))
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()

    for _ in range(2):
        conn = open_database(path)
        try:
            assert current_version(conn) == len(_steps())
            rows = conn.execute(
                "SELECT id, state, file_path, kind, page_count, values_json, duplicate_of "
                "FROM inbox_entry ORDER BY id"
            ).fetchall()
            assert [tuple(row) for row in rows] == [
                (1, "waiting", "/scans/a.pdf", "invoice", None, '[{"field": "n"}]', None),
                (2, "duplicate", "/scans/b.pdf", None, None, "[]", 1),
            ]
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            conn.close()

    conn = open_database(path)
    try:
        with conn:
            conn.execute("UPDATE inbox_entry SET state = 'approved' WHERE id = 1")
            conn.execute("DELETE FROM inbox_entry WHERE id = 1")
        assert conn.execute("SELECT duplicate_of FROM inbox_entry").fetchone()[0] is None
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(inbox_entry)")}
        assert {"idx_inbox_sha", "idx_inbox_import"} <= indexes
    finally:
        conn.close()


def test_privacy_migration_keeps_transitions_and_corrections_stored_before_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    for number, file in _steps():
        if number <= 4:
            conn.executescript(file.read_text(encoding="utf-8"))
    at = "2026-11-10T10:00:00+01:00"
    conn.execute("INSERT INTO inbox_import (id, folder, started_at) VALUES (1, '/scans', ?)", (at,))
    conn.execute(
        "INSERT INTO inbox_entry (id, import_id, state, file_path, sha256, profile, arrived_at) "
        "VALUES (1, 1, 'approved', '/scans/a.pdf', 'abc', 'p', ?)",
        (at,),
    )
    conn.execute(
        "INSERT INTO inbox_correction (entry_id, value_name, after, corrected_at) "
        "VALUES (1, 'n', '7', ?)",
        (at,),
    )
    conn.execute(
        "INSERT INTO job (id, entry_id, idempotency_key, state, file_json) "
        "VALUES ('j', 1, 'k', 'pending', '{}')"
    )
    conn.execute(
        "INSERT INTO job_transition (job_id, to_state, reason, at) "
        "VALUES ('j', 'pending', 'approved', ?)",
        (at,),
    )
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()

    for _ in range(2):
        conn = open_database(path)
        try:
            assert current_version(conn) == len(_steps())
            transition = conn.execute("SELECT reason, at, account FROM job_transition").fetchone()
            assert tuple(transition) == ("approved", at, None)
            assert conn.execute("SELECT account FROM inbox_correction").fetchone()[0] is None
            assert conn.execute("SELECT COUNT(*) FROM inbox_deleted").fetchone()[0] == 0
            assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
            # Migration 006: a job stored before it names no hand-over file.
            assert conn.execute("SELECT format_file FROM job").fetchone()[0] is None
        finally:
            conn.close()


def test_possible_duplicate_migration_keeps_entries_and_accepts_only_two_decisions(
    tmp_path: Path,
) -> None:
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    for number, file in _steps():
        if number <= 6:
            conn.executescript(file.read_text(encoding="utf-8"))
    at = "2026-11-10T10:00:00+01:00"
    conn.execute("INSERT INTO inbox_import (id, folder, started_at) VALUES (1, '/scans', ?)", (at,))
    for entry_id, name in ((1, "a"), (2, "b")):
        conn.execute(
            "INSERT INTO inbox_entry (id, import_id, state, file_path, sha256, profile, arrived_at) "
            "VALUES (?, 1, 'waiting', ?, ?, 'p', ?)",
            (entry_id, f"/scans/{name}.pdf", name, at),
        )
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()

    conn = open_database(path)
    try:
        assert current_version(conn) == len(_steps())
        row = conn.execute(
            "SELECT comparison_key, possible_duplicate_of, duplicate_decision FROM inbox_entry"
        ).fetchone()
        assert tuple(row) == (None, None, None)
        with conn:
            conn.execute(
                "UPDATE inbox_entry SET possible_duplicate_of = 1, duplicate_decision = 'new' "
                "WHERE id = 2"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE inbox_entry SET duplicate_decision = 'maybe' WHERE id = 2")
        with conn:
            conn.execute("DELETE FROM inbox_entry WHERE id = 1")
        assert conn.execute("SELECT possible_duplicate_of FROM inbox_entry").fetchone()[0] is None
    finally:
        conn.close()


def test_foreign_keys_work(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "test.db")
    try:
        conn.execute(
            "INSERT INTO document_type (id, name, created_at, updated_at) "
            "VALUES (1, 'Eingangsrechnung', '2026-07-27T10:00:00+02:00', "
            "'2026-07-27T10:00:00+02:00')"
        )
        conn.execute(
            "INSERT INTO field (document_type_id, name, question) "
            "VALUES (1, 'invoice_number', 'Wie lautet die Rechnungsnummer?')"
        )
        conn.commit()

        assert conn.execute("SELECT count(*) FROM field").fetchone()[0] == 1

        conn.execute("DELETE FROM document_type WHERE id = 1")
        conn.commit()

        assert conn.execute("SELECT count(*) FROM field").fetchone()[0] == 0, (
            "The field should have cascaded — is PRAGMA foreign_keys missing?"
        )
    finally:
        conn.close()


def test_checks(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "test.db")
    try:
        conn.execute(
            "INSERT INTO document_type (id, name, created_at, updated_at) "
            "VALUES (1, 'Typ', '2026-07-27T10:00:00+02:00', '2026-07-27T10:00:00+02:00')"
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO field (document_type_id, name, extractor) "
                "VALUES (1, 'a', 'zauberei')"
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO audit_log (occurred_at, action, target, result, mode) "
                "VALUES ('2026-07-27T10:00:00+02:00', 'export', 'x', 'vielleicht', 'airgap')"
            )
    finally:
        conn.close()


def test_audit_table_accepts_the_statuses_the_shell_writes(tmp_path: Path) -> None:
    """`allowed` and `denied` are what `src-tauri/src/egress.rs` records."""
    insert = (
        "INSERT INTO audit_log (occurred_at, action, target, result, mode) "
        "VALUES ('2026-11-10T10:00:00+01:00', 'export', 'https://example.com', ?, 'airgap')"
    )
    conn = open_database(tmp_path / "test.db")
    try:
        conn.execute(insert, ("allowed",))
        conn.execute(insert, ("denied",))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(insert, ("refused",))
        stored = [row[0] for row in conn.execute("SELECT result FROM audit_log ORDER BY id")]
        assert stored == ["allowed", "denied"]
    finally:
        conn.close()


def test_duplicate_field_name_abgelehnt(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "test.db")
    try:
        conn.execute(
            "INSERT INTO document_type (id, name, created_at, updated_at) "
            "VALUES (1, 'Typ', '2026-07-27T10:00:00+02:00', '2026-07-27T10:00:00+02:00')"
        )
        conn.execute("INSERT INTO field (document_type_id, name) VALUES (1, 'amount')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO field (document_type_id, name) VALUES (1, 'amount')")
    finally:
        conn.close()
