"""What a hostile or broken file in the watched folder, or a broken audit spool, must not do.

The four cases come from the security review of the inbox and the audit
take-over (criterion Z4.8). Each test fails without its correction.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from conftest import Desk, put, variant

from substrakt import audit, inbox, store
from substrakt.db.session import Session
from substrakt.errors import FileNameUnreadable, PathNotAllowed
from substrakt.jobs import Jobs

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"

needs_byte_names = pytest.mark.skipif(
    sys.platform in ("win32", "darwin"), reason="the file system refuses a name that is no UTF-8"
)


def watched(desk: Desk) -> None:
    desk.inbox.choose_folder(str(desk.folder))


def states(desk: Desk) -> dict[str, tuple[str, str | None]]:
    return {e.file_name: (e.state, e.problem_key) for e in desk.inbox.entries()}


# --- 1. A file must never stop the loop ---------------------------------------


@needs_byte_names
def test_inbox_file_name_that_is_no_text_becomes_an_error_entry_and_stops_nothing(
    desk: Desk, invoice: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    (desk.folder / "Adler").mkdir()
    bad = os.fsencode(str(desk.folder / "Adler")) + b"/geheim\xff.pdf"
    with open(bad, "wb") as file:
        file.write(variant(invoice, 1))
    # A customer folder whose name is no text, with a readable file in it.
    os.mkdir(os.fsencode(str(desk.folder)) + b"/Kunde\xfe")
    with open(os.fsencode(str(desk.folder)) + b"/Kunde\xfe/scan.pdf", "wb") as file:
        file.write(variant(invoice, 2))
    put(desk, "Zeller/scan.pdf", variant(invoice, 3))
    watched(desk)

    with caplog.at_level(logging.DEBUG):
        for _ in range(4):
            desk.inbox.poll()  # must not raise

    entries = desk.inbox.entries()
    by_customer = {e.customer: (e.state, e.problem_key) for e in entries}
    # The files behind the bad name are read, for every customer.
    assert by_customer["Zeller"] == ("waiting", None)
    assert by_customer["Adler"] == ("error", "file-name-unreadable")
    assert by_customer["Kunde?"] == ("error", "file-name-unreadable")
    # One entry per file, not one per look, and none after a restart either.
    assert len(entries) == 3
    desk.restart()
    watched(desk)
    desk.settle()
    assert len(desk.inbox.entries()) == 3
    assert "geheim" not in caplog.text


def test_inbox_file_that_fails_unexpectedly_is_not_tried_at_every_look_and_stops_nothing(
    desk: Desk, invoice: bytes, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    put(desk, "Adler/kaputt.pdf", variant(invoice, 1))
    put(desk, "Zeller/scan.pdf", variant(invoice, 2))
    watched(desk)
    validate, calls = desk.store.validate_path, []

    def failing(raw: str) -> Path:
        calls.append(Path(raw).name)
        if raw.endswith("kaputt.pdf"):
            raise RuntimeError("geheimer Inhalt")
        return validate(raw)

    monkeypatch.setattr(desk.store, "validate_path", failing)
    with caplog.at_level(logging.DEBUG):
        for _ in range(4):
            desk.inbox.poll()

    # The file that failed is an entry a person sees, not only a line in the log.
    assert states(desk) == {
        "kaputt.pdf": ("error", "internal-error"),
        "scan.pdf": ("waiting", None),
    }
    assert calls.count("kaputt.pdf") == 1
    assert "RuntimeError" in caplog.text
    assert "geheimer Inhalt" not in caplog.text and "kaputt" not in caplog.text


def test_inbox_file_that_fails_after_its_entry_was_written_does_not_stay_new(
    desk: Desk, invoice: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(desk, "Adler/kaputt.pdf", invoice)
    watched(desk)

    def failing(*_arguments: object) -> None:
        raise RuntimeError("geheimer Inhalt")

    monkeypatch.setattr(desk.inbox, "_read", failing)
    desk.settle()
    desk.settle()

    assert states(desk) == {"kaputt.pdf": ("error", "internal-error")}


def raw(folder: Path, name: bytes, content: bytes) -> None:
    folder.mkdir(exist_ok=True)
    with open(os.fsencode(str(folder)) + b"/" + name, "wb") as file:
        file.write(content)


@needs_byte_names
def test_inbox_two_files_never_share_one_stored_path(desk: Desk, invoice: bytes) -> None:
    adler = desk.folder / "Adler"
    raw(adler, b"a\xff.pdf", variant(invoice, 1))
    raw(adler, b"a\xfe.pdf", variant(invoice, 2))
    raw(adler, b"b\xff.pdf", variant(invoice, 3))
    raw(adler, b"b\xfe.pdf", variant(invoice, 3))
    watched(desk)
    desk.settle()
    # A valid name that equals the readable form of an unreadable one, same bytes.
    put(desk, "Adler/a?.pdf", variant(invoice, 1))
    desk.settle()

    entries = desk.inbox.entries()
    assert len(entries) == 5, "one entry per file on the disk"
    assert len({e.file_path for e in entries}) == 5
    assert sorted(e.file_name for e in entries) == ["a?.pdf"] * 3 + ["b?.pdf"] * 2
    assert {e.folder for e in entries} == {str(adler)}
    assert sum(e.problem_key == "file-name-unreadable" for e in entries) == 4


@needs_byte_names
def test_inbox_delete_never_removes_a_file_for_an_entry_with_an_unreadable_name(
    desk: Desk, invoice: bytes
) -> None:
    adler = desk.folder / "Adler"
    raw(adler, b"a\xff.pdf", invoice)
    watched(desk)
    desk.settle()
    put(desk, "Adler/a?.pdf", invoice)
    desk.settle()
    [unreadable] = [e for e in desk.inbox.entries() if e.problem_key == "file-name-unreadable"]

    # The wish is refused under a key, not passed over.
    with pytest.raises(FileNameUnreadable):
        Jobs(desk.inbox).delete_entry(unreadable.id, delete_file=True)

    assert (adler / "a?.pdf").exists(), "the valid file of the same readable name stays"
    assert len(os.listdir(os.fsencode(str(adler)))) == 2
    assert len(desk.inbox.entries()) == 2, "the entry stays when its file could not go"


@needs_byte_names
def test_inbox_delete_marker_of_an_unreadable_name_stays_while_the_file_is_there(
    desk: Desk, invoice: bytes
) -> None:
    adler = desk.folder / "Adler"
    raw(adler, b"a\xff.pdf", invoice)
    watched(desk)
    desk.settle()
    [entry] = desk.inbox.entries()

    def markers() -> int:
        return desk.inbox.db.query("SELECT count(*) AS c FROM inbox_deleted")[0]["c"]

    Jobs(desk.inbox).delete_entry(entry.id)
    desk.settle()
    assert markers() == 1
    desk.restart()
    watched(desk)
    desk.settle()
    assert desk.inbox.entries() == [], "the deleted entry does not come back after a restart"

    os.unlink(os.fsencode(str(adler)) + b"/a\xff.pdf")
    desk.settle()
    assert markers() == 0, "the marker goes with the file"


@needs_byte_names
def test_inbox_file_renamed_after_an_unreadable_name_is_read_and_is_no_duplicate_of_the_error(
    desk: Desk, invoice: bytes
) -> None:
    adler = desk.folder / "Adler"
    raw(adler, b"M\xfcller.pdf", invoice)  # a Latin-1 name, as a scanner writes it
    watched(desk)
    desk.settle()
    assert states(desk) == {"M?ller.pdf": ("error", "file-name-unreadable")}

    os.rename(os.fsencode(str(adler)) + b"/M\xfcller.pdf", adler / "Mueller.pdf")
    desk.settle()
    desk.settle()
    assert states(desk)["Mueller.pdf"] == ("waiting", None)
    assert desk.parsed == {"Mueller.pdf": 1}

    # A further copy is a duplicate of the entry that was read, not of the error.
    put(desk, "Adler/Kopie.pdf", invoice)
    desk.settle()
    by_name = {e.file_name: e for e in desk.inbox.entries()}
    assert by_name["Kopie.pdf"].state == "duplicate"
    assert by_name["Kopie.pdf"].duplicate_of == by_name["Mueller.pdf"].id


def test_inbox_same_bytes_as_an_error_entry_end_as_an_error_again_and_not_as_its_duplicate(
    desk: Desk, invoice: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(desk, "Adler/lang.pdf", invoice)
    put(desk, "Adler/kaputt.pdf", b"%PDF-1.4 no document")
    watched(desk)
    monkeypatch.setattr(inbox, "MAX_INBOX_PAGES", 0)
    desk.settle()
    put(desk, "Zeller/lang.pdf", invoice)
    put(desk, "Zeller/kaputt.pdf", b"%PDF-1.4 no document")
    desk.settle()

    entries = desk.inbox.entries()
    assert [e.duplicate_of for e in entries] == [None] * 4
    assert {e.state for e in entries} == {"error"}
    by_customer = {(e.customer, e.file_name): e.problem_key for e in entries}
    assert by_customer["Zeller", "lang.pdf"] == "document-too-many-pages"
    assert by_customer["Zeller", "kaputt.pdf"] == by_customer["Adler", "kaputt.pdf"] is not None


# --- 2. Check first, then hash ------------------------------------------------


def test_inbox_file_outside_the_roots_or_over_the_size_limit_is_refused_before_it_is_hashed(
    desk: Desk, invoice: bytes, tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "secret.pdf"
    outside.write_bytes(variant(invoice, 1))
    (desk.folder / "Adler").mkdir()
    (desk.folder / "Adler" / "link.pdf").symlink_to(outside)
    put(desk, "Adler/gross.pdf", variant(invoice, 2) + b" " * 2000)
    put(desk, "Adler/scan.pdf", variant(invoice, 3))
    monkeypatch.setattr(store, "MAX_FILE_BYTES", len(invoice) + 1000)
    hashed = []
    real_hash = inbox.file_hash
    monkeypatch.setattr(inbox, "file_hash", lambda path: hashed.append(path.name) or real_hash(path))
    watched(desk)

    desk.settle()

    assert states(desk) == {
        "link.pdf": ("error", "path-not-allowed"),
        "gross.pdf": ("error", "file-too-large"),
        "scan.pdf": ("waiting", None),
    }
    # Not one byte of a refused file was read, and no hash of it is stored.
    assert hashed == ["scan.pdf"]
    by_name = {e.file_name: e.sha256 for e in desk.inbox.entries()}
    assert by_name["link.pdf"] == "" and by_name["gross.pdf"] == ""
    assert store.file_hash(outside) not in desk.database.read_bytes().decode("latin-1")

    # A refused file is refused once, not at every look and not after a restart.
    desk.settle()
    desk.restart()
    watched(desk)
    desk.settle()
    assert len(desk.inbox.entries()) == 3


# --- 3. Page limit, and no second reading after a crash -----------------------


def test_inbox_file_with_more_pages_than_the_limit_is_not_read(
    desk: Desk, invoice: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(desk, "Adler/lang.pdf", invoice)
    watched(desk)
    assert inbox._page_count(desk.folder / "Adler" / "lang.pdf") == 1
    monkeypatch.setattr(inbox, "MAX_INBOX_PAGES", 0)

    desk.settle()

    assert states(desk) == {"lang.pdf": ("error", "document-too-many-pages")}
    assert desk.parsed == {}, "the parser, and with it text recognition, never started"

    # Within the limit the same file is read.
    monkeypatch.setattr(inbox, "MAX_INBOX_PAGES", 1)
    put(desk, "Adler/kurz.pdf", variant(invoice, 1))
    desk.settle()
    assert states(desk)["kurz.pdf"] == ("waiting", None)


def test_inbox_entry_that_a_crash_left_unfinished_is_not_read_again(
    desk: Desk, invoice: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    put(desk, "Meier/scan.pdf", invoice)
    watched(desk)
    desk.settle()
    desk.inbox.stop()
    conn = sqlite3.connect(desk.database)
    with conn:
        conn.execute("UPDATE inbox_entry SET state = 'new', values_json = '[]'")
    conn.close()

    with caplog.at_level(logging.DEBUG):
        for _ in range(2):  # a file that ends the process must not end it at every start
            desk.restart()
            watched(desk)
            desk.settle()

    assert states(desk) == {"scan.pdf": ("error", "reading-interrupted")}
    assert desk.parsed == {"scan.pdf": 1}
    assert "scan.pdf" not in caplog.text


def test_inbox_new_problem_keys_have_texts_in_both_languages() -> None:
    for dictionary in ("de.ts", "en.ts"):
        text = (ROOT / "src" / "i18n" / dictionary).read_text(encoding="utf-8")
        for key in ("file-name-unreadable", "document-too-many-pages", "reading-interrupted"):
            assert f"'{key}':" in text, (dictionary, key)


# --- 4. A broken audit spool --------------------------------------------------


GOOD = (FIXTURES / "egress_audit.jsonl").read_text(encoding="utf-8").splitlines()[0]
TARGET = "https://geheim.example.com/pfad"
ATTEMPT = (
    '{"occurred_at":1794300000,"action":"x","target":"' + TARGET + '","bytes":0,'
    '"result":"denied","mode":"airgap"}'
)


@pytest.mark.parametrize("bad", [
    b"\xff\xfe no text",
    ATTEMPT.replace("1794300000", "9" * 17).encode(),  # a time no calendar holds
    ATTEMPT.replace('"bytes":0', '"bytes":' + "9" * 30).encode(),  # more than SQLite stores
    ATTEMPT.replace('"bytes":0', '"bytes":-1').encode(),
    ATTEMPT.replace(TARGET, "\\ud800").encode(),  # a lone surrogate cannot be stored
    b"not json",
    ATTEMPT[:40].encode(),
])
def test_audit_spool_with_a_broken_line_is_taken_without_it_and_leaves_nothing_behind(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, bad: bytes
) -> None:
    (tmp_path / audit.SPOOL).write_bytes(GOOD.encode() + b"\n" + bad + b"\n" + GOOD.encode() + b"\n")
    db = Session(tmp_path / "substrakt.db")

    with caplog.at_level(logging.DEBUG):
        assert audit.ingest(db, tmp_path) == 2
    assert not (tmp_path / "egress-audit.taken").exists()
    assert audit.ingest(db, tmp_path) == 0
    assert len(db.query("SELECT * FROM audit_log")) == 2
    assert "1 lines of the spool" in caplog.text
    assert "geheim" not in caplog.text


def test_audit_spool_that_cannot_be_taken_never_raises(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Something stands where the taken file belongs and cannot be read as a file.
    (tmp_path / "egress-audit.taken").mkdir()
    (tmp_path / audit.SPOOL).write_text(GOOD + "\n", encoding="utf-8")
    db = Session(tmp_path / "substrakt.db")

    with caplog.at_level(logging.ERROR):
        assert audit.ingest(db, tmp_path) == 0
    assert "could not be taken" in caplog.text


def test_ausgabe_link_out_of_the_read_roots_is_refused_and_nothing_is_written_through_it(
    desk: Desk, invoice: bytes, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (desk.folder / "Ausgabe").symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathNotAllowed):
        desk.inbox.choose_folder(str(desk.folder))
    assert desk.inbox.settings().folder is None

    # A link inside the read roots is refused too: files go only into a plain folder.
    (desk.folder / "Ausgabe").unlink()
    inside = desk.root / "elsewhere"
    inside.mkdir()
    (desk.folder / "Ausgabe").symlink_to(inside, target_is_directory=True)
    with pytest.raises(PathNotAllowed):
        desk.inbox.choose_folder(str(desk.folder))

    # A link put in place after the choice is not written through either.
    (desk.folder / "Ausgabe").unlink()
    desk.inbox.choose_folder(str(desk.folder))
    (desk.folder / "Ausgabe").rmdir()
    (desk.folder / "Ausgabe").symlink_to(outside, target_is_directory=True)
    put(desk, "Meier/scan.pdf", invoice)
    desk.settle()
    [entry] = desk.inbox.entries()
    jobs = Jobs(desk.inbox)
    job = jobs.approve(entry.id)
    assert (job.state, job.handover_path) == ("pending", None)
    assert desk.inbox.handover_folder() is None
    assert list(outside.iterdir()) == [] and list(inside.iterdir()) == []
