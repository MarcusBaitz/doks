"""Domain errors returned as RFC 9457 ``application/problem+json``.

The frontend receives a stable key and resolves it to translated interface
text. Stack traces remain in the local log, and messages never quote document
contents so that logs do not become a second data trail.
"""

from __future__ import annotations

from typing import Any

BASE = "https://substrakt.local/problem/"


class SubstraktError(Exception):
    """Base class for errors that may cross the sidecar boundary."""

    key: str = "internal-error"
    status: int = 500
    title: str = "Internal error"

    def __init__(self, detail: str = "", **fields: Any) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.fields = fields

    def as_problem(self) -> dict[str, Any]:
        problem: dict[str, Any] = {
            "type": BASE + self.key,
            "title": self.title,
            "status": self.status,
            "key": self.key,
        }
        if self.detail:
            problem["detail"] = self.detail
        problem.update(self.fields)
        return problem


class FileNotFound(SubstraktError):
    key = "file-not-found"
    status = 404
    title = "File not found"


class FormatNotSupported(SubstraktError):
    key = "format-not-supported"
    status = 415
    title = "File format is not supported"


class FileTooLarge(SubstraktError):
    key = "file-too-large"
    status = 413
    title = "File is too large"


class DocumentCorrupt(SubstraktError):
    key = "document-corrupt"
    status = 422
    title = "Document is corrupt or unreadable"


class DocumentPasswordProtected(SubstraktError):
    key = "document-password-protected"
    status = 422
    title = "Document is password protected"


class DocumentEmpty(SubstraktError):
    key = "document-empty"
    status = 422
    title = "Document contains no usable content"


class UnknownDocument(SubstraktError):
    key = "unknown-document"
    status = 404
    title = "Document is not loaded in this session"


class PageNotFound(SubstraktError):
    key = "page-not-found"
    status = 404
    title = "Page does not exist"


class NotAuthorized(SubstraktError):
    key = "not-authorized"
    status = 401
    title = "Session token is invalid"


class PathNotAllowed(SubstraktError):
    """Reject paths outside the roots granted by the Rust shell."""

    key = "path-not-allowed"
    status = 403
    title = "Access to this path is not allowed"


class OutputNameTaken(SubstraktError):
    """A file, not a folder, has the name of the output folder; it is never replaced."""

    key = "output-name-taken"
    status = 409
    title = "A file has the name of the output folder"


class EgressDenied(SubstraktError):
    key = "egress-denied"
    status = 403
    title = "Network access is not allowed in the current mode"


class DocumentKindInvalid(SubstraktError):
    """A document-kind YAML file violates the packaged schema."""

    key = "document-kind-invalid"
    status = 500
    title = "Document-kind description is invalid"


class DocumentKindUnknown(SubstraktError):
    key = "document-kind-unknown"
    status = 404
    title = "Document kind is not described"


class PipelineProfileInvalid(SubstraktError):
    """A pipeline-profile YAML file violates the packaged schema."""

    key = "pipeline-profile-invalid"
    status = 500
    title = "Pipeline-profile description is invalid"


class HandOverTableInvalid(SubstraktError):
    """A mapping table of a hand-over format is missing or violates its schema."""

    key = "hand-over-table-invalid"
    status = 500
    title = "Mapping table of the hand-over is invalid"


class PipelineProfileUnknown(SubstraktError):
    """No profile of that name exists, or none is chosen among several."""

    key = "pipeline-profile-unknown"
    status = 404
    title = "Pipeline profile is not described"


class FileNameUnreadable(SubstraktError):
    """The name of a file in the watched folder is no valid text and cannot be stored."""

    key = "file-name-unreadable"
    status = 422
    title = "File name cannot be read"


class DocumentTooManyPages(SubstraktError):
    """A file has more pages than the inbox reads in the background."""

    key = "document-too-many-pages"
    status = 413
    title = "Document has too many pages"


class ReadingInterrupted(SubstraktError):
    """The application ended while this file was being read; it is not read again by itself."""

    key = "reading-interrupted"
    status = 500
    title = "Reading was interrupted"


class InboxEntryUnknown(SubstraktError):
    key = "inbox-entry-unknown"
    status = 404
    title = "Inbox entry does not exist"


class CorrectionRefused(SubstraktError):
    """The entry is closed, or the correction names a kind or value it cannot have."""

    key = "correction-refused"
    status = 409
    title = "Correction is not possible"


class KindChangeRefused(SubstraktError):
    """A changed list of values has an empty or repeated name, or leaves too little."""

    key = "kind-change-refused"
    status = 409
    title = "The values of the document kind were not changed"


class ApprovalRefused(SubstraktError):
    """A required value is open or not unambiguous, or the entry cannot be approved."""

    key = "approval-refused"
    status = 409
    title = "Approval is not possible"


class JobUnknown(SubstraktError):
    key = "job-unknown"
    status = 404
    title = "Job does not exist"


class JobTransitionInvalid(SubstraktError):
    """A job moves only along the transitions the job queue names."""

    key = "job-transition-invalid"
    status = 409
    title = "Job cannot change to this state"


class ImportReasonMissing(SubstraktError):
    """A failed import is reported without the reason a person saw."""

    key = "import-reason-missing"
    status = 422
    title = "A failed import needs a reason"


class FileChanged(SubstraktError):
    """The file at the stored path is no longer the one that was read."""

    key = "file-changed"
    status = 409
    title = "File changed since it was read"
