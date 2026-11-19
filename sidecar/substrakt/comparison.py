"""The comparison key of a read document.

Two scans of the same paper are two files with different content. What they
share are the values that identify the document, and which values those are
is knowledge of the kind file (``same_document``), not of this module. The
key is a hash, so that it can be stored and looked up without becoming a
second place that holds the values.

A key exists only when every named value was read unambiguously. A value
that is missing or unclear gives no key and therefore no comparison: a
doubtful value must never mark, let alone discard, a document.
"""

from __future__ import annotations

import hashlib
import json

from substrakt.document_kinds import DocumentKind
from substrakt.extraction.fields import ExtractionResult


def comparable(value: str | float | bool) -> str:
    """The form in which two readings of one value are equal.

    Text is compared by its letters and digits only, without case: a scan
    reads "NV-HA 2162/6533" where another reads "NV-HA-2162-6533". Dates and
    numbers arrive normalised and are compared as they are.
    """
    if isinstance(value, str):
        return "".join(character for character in value.casefold() if character.isalnum())
    return repr(value)


def comparison_key(kind: DocumentKind | None, results: list[ExtractionResult]) -> str | None:
    """Hash kind and comparison values, or ``None`` when there is nothing to compare."""
    if kind is None or not kind.same_document:
        return None
    read = {result.field: result for result in results}
    forms = []
    for name in kind.same_document:
        result = read.get(name)
        if result is None or not result.value or not result.grounded:
            return None
        # The normalised value, so that "01.07.2026" and "1. Juli 2026" agree.
        forms.append(comparable(result.normalized if result.normalized is not None else result.value))
    if not all(forms):
        return None
    canonical = json.dumps([kind.name, forms], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
