"""Tests for conftest."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("SUBSTRAKT_DEV", "1")
os.environ.setdefault("SUBSTRAKT_MODE", "airgap")

# Keep test data out of the user's application-data directory.
if "SUBSTRAKT_DATA_DIR" not in os.environ:
    _data = Path(tempfile.mkdtemp(prefix="substrakt-test-"))
    os.environ["SUBSTRAKT_DATA_DIR"] = str(_data)
    os.environ.setdefault("SUBSTRAKT_LOG_DIR", str(_data / "logs"))


# --- Shared fixtures -------------------------------------------------------


import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "corpus" / "out"


@pytest.fixture(scope="session", autouse=True)
def corpus() -> Path:
    """Generate the corpus if it is missing."""
    # The insurance folder came later; an older corpus lacks it.
    if not all((CORPUS / file).exists() for file in ("rechnung_din5008.pdf", "insurance/truth.json")):
        subprocess.run(
            [sys.executable, str(ROOT / "corpus" / "generate.py")],
            check=True,
            capture_output=True,
        )
    return CORPUS


@pytest.fixture
def store():
    from substrakt.config import load
    from substrakt.store import DocumentStore

    return DocumentStore(load())


# --- Inbox -----------------------------------------------------------------
#
# Shared by test_inbox.py and test_jobs.py: real files, a real database.

import dataclasses  # noqa: E402
from collections import Counter  # noqa: E402

from substrakt import document_kinds, pipeline_profiles  # noqa: E402
from substrakt import jobs as jobs_module  # noqa: E402
from substrakt.config import load as load_config  # noqa: E402
from substrakt.inbox import OUTPUT, Inbox, InboxEntry  # noqa: E402
from substrakt.jobs import JobFile, Jobs  # noqa: E402
from substrakt.store import DocumentStore  # noqa: E402

PROFILE = """\
name: {name}
title: Test
target: test_target
customer_folder_level: {level}
kinds:
  invoice:
    values:
      document_number: Nummer
"""


class Desk:
    """A read root with a watched folder, and an inbox that can be restarted."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.folder = root / "scans"
        self.folder.mkdir()
        self.database = root / "data" / "substrakt.db"
        config = dataclasses.replace(load_config(), allowed_roots=[root])
        self.store = DocumentStore(config)
        # Counts every attempt to parse a file, successful or not.
        self.parsed: Counter[str] = Counter()
        parse = self.store.parse

        def counting(path: Path, sha: str):
            self.parsed[path.name] += 1
            return parse(path, sha)

        self.store.parse = counting  # type: ignore[method-assign]
        self.inbox = self.restart()

    def restart(self) -> Inbox:
        """A new inbox on the same database, as after a restart of the sidecar."""
        self.inbox = Inbox(self.database, self.store, [self.root])
        return self.inbox

    def settle(self) -> None:
        """Two looks: the second finds every file unchanged and takes it."""
        self.inbox.poll()
        self.inbox.poll()

    def entries(self) -> dict[str, object]:
        """Entries by path relative to the watched folder."""
        return {
            str(Path(e.file_path).relative_to(self.folder)): e for e in self.inbox.entries()
        }


@pytest.fixture
def invoice(corpus: Path) -> bytes:
    return (corpus / "rechnung_din5008.pdf").read_bytes()


@pytest.fixture
def desk(tmp_path: Path):
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    # A second kind with the values of the first, so that a kind can be corrected.
    kinds = tmp_path / "kinds"
    kinds.mkdir()
    invoice_kind = (Path(document_kinds.__file__).parent / "invoice.yml").read_text("utf-8")
    (kinds / "credit_note.yml").write_text(
        invoice_kind.replace("name: invoice", "name: credit_note", 1), encoding="utf-8"
    )
    user_kinds = document_kinds.custom_directory()
    document_kinds.configure(kinds)
    (profiles / "scans.yml").write_text(PROFILE.format(name="scans", level=1), encoding="utf-8")
    (profiles / "flat.yml").write_text(PROFILE.format(name="flat", level="null"), encoding="utf-8")
    pipeline_profiles.configure(profiles)
    desk = Desk(tmp_path)
    desk.inbox.choose_profile("scans")
    yield desk
    pipeline_profiles.configure(None)
    document_kinds.configure(user_kinds)


def put(desk: Desk, relative: str, content: bytes) -> Path:
    file = desk.folder / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)
    return file


def variant(invoice: bytes, number: int) -> bytes:
    """The same document with different bytes, so that it is no duplicate."""
    return invoice + f"\n%variant {number}\n".encode()


# Requires a value the sample invoice does not carry (sender) next to two it does.
STRICT = PROFILE.format(name="strict", level=1) + (
    "      document_date: Datum\n      sender: Absender\n"
)
TWO_KINDS = PROFILE.format(name="two_kinds", level=1) + (
    "  credit_note:\n    values:\n      document_number: Nummer\n"
)


class Queue:
    """A desk with its output folder, a job queue and one entry that waits."""

    def __init__(self, desk: Desk, invoice: bytes, profile: str = "scans") -> None:
        self.desk = desk
        self.invoice = invoice
        profiles = desk.root / "profiles"
        (profiles / "strict.yml").write_text(STRICT, encoding="utf-8")
        (profiles / "two_kinds.yml").write_text(TWO_KINDS, encoding="utf-8")
        desk.inbox.choose_profile(profile)
        desk.inbox.choose_folder(str(desk.folder))
        self.handover = desk.folder / OUTPUT
        self.jobs = Jobs(desk.inbox)
        self.entry = self.arrive("Meier/policy.pdf", 1)

    def arrive(self, relative: str, number: int) -> InboxEntry:
        put(self.desk, relative, variant(self.invoice, number))
        self.desk.settle()
        return self.desk.entries()[relative]  # type: ignore[return-value]

    def files(self) -> list[str]:
        return sorted(file.name for file in self.handover.iterdir())


@pytest.fixture
def queue(desk: Desk, invoice: bytes) -> Queue:
    return Queue(desk, invoice)


@pytest.fixture
def writer(monkeypatch: pytest.MonkeyPatch) -> list[JobFile]:
    """Register a writer for the target of the test profiles; returns what it received."""
    received: list[JobFile] = []
    monkeypatch.setitem(jobs_module.WRITERS, "test_target", lambda file, _: received.append(file))
    return received


@pytest.fixture
def unrecognised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every document is unclear, as one that could be two kinds is."""
    monkeypatch.setattr(document_kinds, "recognise", lambda doc, kinds=None: None)
