"""Hand-over runs: the pending jobs of one customer leave as one file.

The job queue hands over one job at a time, a hand-over format such as GDV
wants the approved contracts of one customer in one file. This module stands
between the two. A profile with a block ``hand_over`` names its format there;
its jobs stay pending until a person starts a run for a customer, because the
content is to be shown before anything is written. A run calls the writer of
the format once per profile, and maps what the writer reports to the states
of the jobs:

- written: the job file is written beside it and the job is handed over;
- waiting or failed: the job fails with the reason, and nothing is written
  again by itself; a person releases it for the next run.

Which format exists is the only thing named here. Everything about a target
stays in its profile, and everything about a format in its writer.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from substrakt import gdv, pipeline_profiles
from substrakt.errors import ApprovalRefused, HandOverTableInvalid, PipelineProfileInvalid
from substrakt.inbox import Inbox
from substrakt.jobs import (
    REASON_NAME_TAKEN,
    REASON_WRITE_FAILED,
    REASON_WRITTEN,
    TEMPORARY,
    Job,
    JobFile,
    Jobs,
    write_job_file,
)

log = logging.getLogger(__name__)

# Format name in the block ``hand_over`` of a profile → its writer module,
# which offers ``check(job, profile)``, ``hand_over(jobs, folder, profile,
# customer=...)`` and ``PART``, the name of its file while it is written.
FORMATS: dict[str, Any] = {"gdv": gdv}

REASON_NOT_WRITABLE = "hand-over-held-back"
REASON_READ_BACK = "hand-over-read-back-failed"
REASON_SETTINGS = "hand-over-settings-invalid"
REASON_TABLE = "hand-over-table-invalid"
REASON_NO_CUSTOMER = "hand-over-without-customer"
REASON_NO_FOLDER = "hand-over-folder-missing"


def _profile(file: JobFile) -> dict[str, Any]:
    """The profile of a job as plain data, with one list of value names per kind.

    A writer finds a value by its name in the target. Whether the profile
    requires it for an approval is no concern of a format, so optional values
    stand in the same list.
    """
    profile = pipeline_profiles.load(file.profile).model_dump()
    for expected in profile["kinds"].values():
        expected["values"] |= expected.pop("optional")
    return profile


def _plain(job_id: str, file: JobFile) -> dict[str, Any]:
    """A job as the plain data a writer takes."""
    values = {name: value.model_dump() for name, value in file.values.items()}
    return {"id": job_id, "kind": file.kind, "values": values}


def in_runs(file: JobFile) -> bool:
    """Whether a job leaves in a run a person starts instead of by itself."""
    return _profile(file).get("hand_over") is not None


def check(file: JobFile) -> None:
    """Refuse an approval whose document the format could not write."""
    profile = _profile(file)
    writer = FORMATS.get((profile.get("hand_over") or {}).get("format"))
    if writer is None:
        return
    items = writer.check(_plain(file.id, file), profile)
    if items:
        # Item names only: the values themselves do not belong in an error message.
        raise ApprovalRefused(
            "The hand-over format cannot take this document.",
            reason="hand-over-not-possible",
            items=_names(items),
        )


def _names(items: list[dict[str, Any]]) -> list[str]:
    return [f"{i['item']}:{i['field']}" if "field" in i else i["item"] for i in items]


def clear_leftovers(jobs: Jobs, inbox: Inbox) -> None:
    """Remove what a crash left half-written in the output folder.

    Such a file holds values and no job points to it, so no deletion would
    find it. Only the two names a writer uses while it writes are removed,
    in this folder only, and never while a run is writing.
    """
    folder = inbox.handover_folder()
    if folder is None or not folder.is_dir():
        return
    patterns = [TEMPORARY, *(writer.PART for writer in FORMATS.values())]
    with jobs.handover_lock:
        for file in folder.iterdir():
            ours = any(pattern.fullmatch(file.name) for pattern in patterns)
            if ours and file.is_file() and not file.is_symlink():
                file.unlink()
                log.info("Removed a half-written file from the hand-over folder")


def _pending(jobs: Jobs, customer: str) -> dict[str, list[Job]]:
    """The pending jobs of one customer that wait for a run, by profile."""
    by_profile: dict[str, list[Job]] = {}
    for job in jobs.all():
        if job.state == "pending" and job.file.customer == customer and in_runs(job.file):
            by_profile.setdefault(job.file.profile, []).append(job)
    return by_profile


def _writer(profile: dict[str, Any]) -> Any:
    writer = FORMATS.get((profile.get("hand_over") or {}).get("format"))
    if writer is None:
        raise PipelineProfileInvalid("", error=[{"location": "hand_over.format"}])
    return writer


def _attempt(call: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
    """Call a writer; return its result, or the reason a whole run cannot go."""
    try:
        return call(), None
    except PipelineProfileInvalid as invalid:
        # The reason names the settings, never their content.
        keys = ", ".join(e["location"] for e in invalid.fields.get("error", []))
        return {}, f"{REASON_SETTINGS}: {keys}"
    except HandOverTableInvalid:
        return {}, REASON_TABLE
    except ValueError:
        return {}, REASON_NO_CUSTOMER
    except FileExistsError:
        # A foreign file has the temporary name of the format; it stays.
        return {}, REASON_NAME_TAKEN
    except OSError:
        log.exception("Hand-over run could not write its file")
        return {}, REASON_WRITE_FAILED


class Preview(BaseModel):
    """What a run for one customer would write now; nothing is written for it."""

    customer: str
    # Job ids the file would hold, one list per contract (one policy number).
    contracts: list[list[str]]
    # Job ids the file would leave out, with the items the writer names.
    waiting: dict[str, list[dict[str, Any]]]
    # Why no job of the customer could be written at all, as a reason key.
    problem: str | None


def simulate(jobs: Jobs, inbox: Inbox, customer: str) -> Preview:
    """The dry run of ``run``: the same jobs, the same build, no file."""
    preview = Preview(customer=customer, contracts=[], waiting={}, problem=None)
    if inbox.handover_folder() is None:
        preview.problem = REASON_NO_FOLDER
        return preview
    for group in _pending(jobs, customer).values():
        profile = _profile(group[0].file)
        plain = [_plain(job.id, job.file) for job in group]
        result, preview.problem = _attempt(
            lambda profile=profile, plain=plain: _writer(profile).simulate(plain, profile)
        )
        if preview.problem:
            return preview
        preview.waiting |= result["waiting"]
        preview.contracts += result["contracts"]
    return preview


def run(jobs: Jobs, inbox: Inbox, customer: str) -> list[Job]:
    """Write the pending jobs of one customer; return them in their new states.

    Without a hand-over folder nothing happens and the jobs stay pending.
    """
    folder = inbox.handover_folder()
    if folder is None:
        return []
    # One run at a time, and none while an entry is deleted: two runs must not
    # name the same file, and a deletion must find the file its job went into.
    with jobs.handover_lock:
        by_profile = _pending(jobs, customer)
        for group in by_profile.values():
            _run_profile(jobs, inbox, folder, customer, group)
    return [jobs.get(job.id) for group in by_profile.values() for job in group]


def _run_profile(
    jobs: Jobs, inbox: Inbox, folder: Path, customer: str, group: list[Job]
) -> None:
    move = jobs.move

    def fail(reason: str) -> None:
        for job in group:
            move(job.id, "failed", reason)

    profile = _profile(group[0].file)
    plain = [_plain(job.id, job.file) for job in group]
    result, reason = _attempt(
        lambda: _writer(profile).hand_over(plain, folder, profile, customer=customer)
    )
    if reason:
        return fail(reason)

    in_file = []
    for job in group:
        if job.id in result["waiting"]:
            names = ", ".join(_names(result["waiting"][job.id]))
            move(job.id, "failed", f"{REASON_NOT_WRITABLE}: {names}")
        elif job.id in result["failed"]:
            move(job.id, "failed", f"{REASON_READ_BACK}: {result['failed'][job.id]}")
        else:
            in_file.append(job)
    # Every job points to the file before anything else can fail: a file
    # with contracts that no job names would be found by no deletion.
    for job in in_file:
        inbox.db.write("UPDATE job SET format_file = ? WHERE id = ?", result["file"], job.id)
    job_files: list[Path] = []
    try:
        for job in in_file:
            job_files.append(write_job_file(folder, job.file))
    except OSError as exc:
        log.exception("A job of the hand-over run could not be handed over")
        failed = REASON_NAME_TAKEN if isinstance(exc, FileExistsError) else REASON_WRITE_FAILED
        # The file holds the contract of a job that failed, and a release
        # would write it into a second file. It goes as a whole, and all its
        # jobs are handed over again.
        try:
            for path in (Path(result["file"]), *job_files):
                path.unlink(missing_ok=True)
        except OSError:
            log.exception("The file of the failed hand-over run could not be removed")
        else:
            inbox.db.write(
                "UPDATE job SET format_file = NULL WHERE format_file = ?", result["file"]
            )
        for job in in_file:
            move(job.id, "failed", failed)
        return
    for job, written in zip(in_file, job_files, strict=True):
        inbox.db.write("UPDATE job SET handover_path = ? WHERE id = ?", str(written), job.id)
        move(job.id, "handed_over", REASON_WRITTEN)
