"""Document-kind knowledge stored as validated YAML rather than Python code.

Bundled files may be replaced, but not merged, by a same-named file in the
user data directory. A kind may select at most one bundled custom parser.
Model and quantization choices do not belong in document-kind data.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import statistics
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from substrakt import yaml_model
from substrakt.errors import DocumentKindInvalid, DocumentKindUnknown
from substrakt.extraction import extractors, normalization
from substrakt.extraction.fields import FieldSpec
from substrakt.extraction.labels import (
    BOUNDARY,
    Assignment,
    LabelContext,
    LabelRule,
    anchor_pattern,
    box,
)
from substrakt.index.words import build_lines
from substrakt.model import Document, ImageRect, PdfRect

BUILTIN = Path(__file__).parent
PARSER_PACKAGE = f"{__name__}.parser"
EXTENSION = ".yml"

# Used for fields of a template when no kind was recognised.
DEFAULT = "invoice"

# Recognition weighs a kind's title against its labels. A title counts as much
# as three labels, because two kinds of one trade share most of their labels.
TITLE_WEIGHT = 3
# The best kind must lead the second-best by this much; a closer result is a
# document that fits two kinds, and that goes to review instead of a guess.
MARGIN = 2
# A heading is printed larger than the body text by at least this factor.
HEADING_FACTOR = 1.2

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

# Configured by app.py so implicit default access sees user overrides.
_custom: Path | None = None

Parser = Callable[[Document, FieldSpec, "DocumentKind"], Assignment | None]


class Recognition(BaseModel):
    """Features used to recognize a document of this kind."""

    model_config = ConfigDict(extra="forbid")

    titles: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Canonical value mapped to printed document titles",
    )
    title_patterns: list[str] = Field(
        default_factory=list,
        description="Regular expressions for the heading that names this kind",
    )
    minimum: int = Field(
        default=4,
        ge=1,
        description="Score a document must reach: 3 for the heading, 1 per field label found",
    )


class DocumentKind(BaseModel):
    """A complete document-kind definition from YAML."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Must equal the file name without its extension")
    title: str = Field(description="Display name for the interface")
    description: str = ""
    recognition: Recognition = Field(default_factory=Recognition)
    legal_forms: list[str] = Field(
        default_factory=list,
        description="Patterns that identify legal forms in company names",
    )
    boundaries: list[str] = Field(
        default_factory=list,
        description="Labels that end another field's search area",
    )
    fields: list[FieldSpec] = Field(min_length=1)
    parser: str | None = Field(
        default=None,
        description="Bundled module name under substrakt/document_kinds/parser/",
    )
    same_document: list[str] = Field(
        default_factory=list,
        description=(
            "Values that identify one document of this kind. Two files with different "
            "content whose values all agree are a possible duplicate that a person "
            "decides. Empty: documents of this kind are never compared by values."
        ),
    )

    _context: LabelContext | None = PrivateAttr(default=None)

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_field_keys(cls, raw: Any) -> Any:
        """Reject field-key typos in human-authored YAML."""
        if isinstance(raw, dict) and isinstance(raw.get("fields"), list):
            allowed = set(FieldSpec.model_fields)
            for index, field in enumerate(raw["fields"]):
                if isinstance(field, dict) and (unknown := sorted(set(field) - allowed)):
                    raise ValueError(
                        f"fields.{index}: unknown keys {', '.join(unknown)}"
                    )
        return raw

    @model_validator(mode="after")
    def _consistent(self) -> DocumentKind:
        if not _NAME.match(self.name):
            raise ValueError(
                f"name {self.name!r}: use lowercase letters, digits and underscores"
            )
        names = [f.name for f in self.fields]
        if duplicates := sorted({n for n in names if names.count(n) > 1}):
            raise ValueError(f"Duplicate field names: {', '.join(duplicates)}")
        if unknown := sorted(set(self.same_document) - set(names)):
            raise ValueError(f"same_document: not a value of the kind: {', '.join(unknown)}")
        for patterns in [*self.legal_forms, *self.boundaries, *self.recognition.title_patterns]:
            try:
                re.compile(patterns)
            except re.error as exc:
                raise ValueError(f"Pattern {patterns!r} is not a valid regular expression: {exc}") from None
        for field in self.fields:
            if field.normalization and field.normalization not in normalization.NORMALIZERS:
                raise ValueError(f"{field.name}: unknown normalization {field.normalization!r}")
            if field.extractor and field.extractor not in extractors.EXTRACTORS and field.extractor != "document_field":
                raise ValueError(f"{field.name}: unknown extractor {field.extractor!r}")
            if field.regex:
                try:
                    re.compile(field.regex)
                except re.error as exc:
                    raise ValueError(f"{field.name}: invalid regex: {exc}") from None
            rule = field.label_rule
            if rule and rule.value == "title" and not self.recognition.titles:
                raise ValueError(f"{field.name}: value: title requires recognition.titles")
            if rule and rule.value == "company" and not self.legal_forms:
                raise ValueError(f"{field.name}: value: company requires legal_forms")
        if self.parser is not None:
            # Report a bad parser at load time rather than on the first document.
            _load_parser(self.parser)
        return self

    def rule_for(self, name: str) -> LabelRule | None:
        return next((f.label_rule for f in self.fields if f.name == name), None)

    def context(self) -> LabelContext:
        """Compile labels, legal forms and titles once per file revision."""
        if self._context is None:
            anchors = {
                f.name: anchor_pattern(tuple(f.label_rule.patterns))
                for f in self.fields
                if f.label_rule and f.label_rule.patterns
            }
            if self.boundaries:
                anchors[BOUNDARY] = anchor_pattern(tuple(self.boundaries))
            legal_form = (
                re.compile(r"\b(?:" + "|".join(self.legal_forms) + r")\b", re.I)
                if self.legal_forms
                else re.compile(r"(?!)")
            )
            title = {
                printed.lower(): canonical_value
                for canonical_value, printed_values in self.recognition.titles.items()
                for printed in printed_values
            }
            self._context = LabelContext(anchors=anchors, legal_form=legal_form, title=title)
        return self._context

    def title_pattern(self) -> re.Pattern[str] | None:
        patterns = self.recognition.title_patterns
        return anchor_pattern(tuple(patterns)) if patterns else None

    def read_with_parser(self, doc: Document, field: FieldSpec) -> Assignment | None:
        """Ask the custom parser; ``None`` delegates back to the core."""
        if self.parser is None:
            return None
        return _load_parser(self.parser)(doc, field, self)


@lru_cache(maxsize=16)
def _load_parser(name: str) -> Parser:
    """Find a bundled parser after validating its import-safe name."""
    if not _NAME.match(name):
        raise ValueError(f"parser {name!r}: use lowercase letters, digits and underscores")
    module_name = f"{PARSER_PACKAGE}.{name}"
    try:
        found = importlib.util.find_spec(module_name)
    except (ModuleNotFoundError, ValueError):
        found = None
    if found is None:
        raise ValueError(f"parser {name!r} does not exist under substrakt/document_kinds/parser/")
    module = importlib.import_module(module_name)
    read = getattr(module, "read", None)
    if not callable(read):
        raise ValueError(f"parser {name!r} has no read(doc, field, kind) function")
    return read


# --- Loading --------------------------------------------------------------


@lru_cache(maxsize=64)
def _read(path: Path, _revision: tuple[int, int]) -> DocumentKind:
    """Read and validate a file; ``_revision`` invalidates the cache."""
    return yaml_model.read(path, DocumentKind, DocumentKindInvalid)


def configure(custom: Path | None) -> None:
    """Set the user override directory during application startup."""
    global _custom
    _custom = custom


def custom_directory() -> Path | None:
    return _custom


def _sources(builtin: Path, custom: Path | None) -> dict[str, Path]:
    return yaml_model.sources(builtin, custom if custom is not None else _custom)


def load_all(builtin: Path = BUILTIN, custom: Path | None = None) -> dict[str, DocumentKind]:
    """Load all kinds by name and report any invalid file."""
    return {
        name: _read(path, yaml_model.state(path))
        for name, path in sorted(_sources(builtin, custom).items())
    }


def load(name: str, builtin: Path = BUILTIN, custom: Path | None = None) -> DocumentKind:
    """Load one kind by name without reading unrelated files."""
    path = _sources(builtin, custom).get(name)
    if path is None:
        raise DocumentKindUnknown(f"No file named {name}{EXTENSION}", kind=name)
    return _read(path, yaml_model.state(path))


def default() -> DocumentKind:
    return load(DEFAULT)


# --- Recognition ----------------------------------------------------------


def _evidence(doc: Document, kinds: dict[str, DocumentKind]) -> tuple[dict[str, int], set[str]]:
    """Return every kind's score and the kinds whose heading the page carries."""
    result = dict.fromkeys(kinds, 0)
    words = [w for w in doc.words_on_page(0) if isinstance(w.locator, (ImageRect, PdfRect))]
    lines = build_lines(words, doc.kind == "image")
    if not lines:
        return result, set()
    heights = [max(box(w)[3] - box(w)[1] for w in line) for line in lines]
    body = statistics.median(heights)
    texts = [" ".join(w.text for w in line) for line in lines]

    titled: set[str] = set()
    for text, height in zip(texts, heights, strict=True):
        found = [
            (match.start(), -match.end(), name)
            for name, kind in kinds.items()
            if (pattern := kind.title_pattern()) and (match := pattern.search(text))
        ]
        if not found:
            continue
        # The head of a heading names the kind: a change “to the policy” is a
        # contract change, although its heading also names the policy. Of two
        # that start at the same place the longer one wins.
        start, end, name = min(found)
        heading = height >= HEADING_FACTOR * body
        alone = start == 0 and -end == len(text)
        if heading or alone:
            titled.add(name)

    for name, kind in kinds.items():
        anchors = kind.context().anchors
        labels = sum(
            1
            for field in kind.fields
            if (pattern := anchors.get(field.name)) and any(pattern.search(text) for text in texts)
        )
        result[name] = TITLE_WEIGHT * (name in titled) + labels
    return result, titled


def scores(doc: Document, kinds: dict[str, DocumentKind] | None = None) -> dict[str, int]:
    """Score the first page against every kind's heading and field labels.

    Only the first page counts: a scan may hold several documents, and the
    heading of a document stands on its first page.
    """
    return _evidence(doc, load_all() if kinds is None else kinds)[0]


def recognise(doc: Document, kinds: dict[str, DocumentKind] | None = None) -> DocumentKind | None:
    """Return the one kind a document clearly is, or ``None`` for review."""
    kinds = load_all() if kinds is None else kinds
    found, titled = _evidence(doc, kinds)
    # Two headings of two kinds on one page are two documents in one scan;
    # the labels of the longer one must not outvote the other.
    if not found or len(titled) > 1:
        return None
    ranked = sorted(found.items(), key=lambda item: -item[1])
    (best, score), second = ranked[0], ranked[1][1] if len(ranked) > 1 else 0
    if score < kinds[best].recognition.minimum or score - second < MARGIN:
        return None
    return kinds[best]


SCHEMA_FILE = BUILTIN / "document_kind.schema.json"


def schema_text() -> str:
    """Generate the editor schema from the authoritative Pydantic model."""
    return yaml_model.schema_text(DocumentKind)


def write_schema(target: Path = SCHEMA_FILE) -> None:
    target.write_text(schema_text(), encoding="utf-8")


def schema_is_current(file: Path = SCHEMA_FILE) -> bool:
    return file.is_file() and file.read_text(encoding="utf-8") == schema_text()
