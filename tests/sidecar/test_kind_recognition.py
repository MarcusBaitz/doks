"""Tests for recognising the document kind from the rules in the YAML files.

The property that matters is the negative one: a document that fits no kind,
or two kinds, gets no kind and goes to review instead of a guess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_document_kinds import document, write_kind

from substrakt import document_kinds
from substrakt.model import Document, DocumentMeta, ImageRect, Page, Word

CORPUS = Path(__file__).resolve().parents[2] / "corpus" / "out"
INSURANCE = CORPUS / "insurance"


def titled(title: str, rows: list[tuple[int, list[tuple[int, str]]]], height: int = 16) -> Document:
    """A page whose first line is printed larger than its body."""
    doc = document(rows)
    words = [
        Word(text=token, page=0, confidence=0.99,
             locator=ImageRect(page=0, x0=20 + 90 * i, x1=100 + 90 * i, y0=0, y1=height))
        for i, token in enumerate(title.split())
    ]
    return Document(
        id="test", filename="test.png", sha256="test", kind="image",
        pages=[Page(number=0, width=600, height=800)], words=[*words, *doc.words],
        meta=DocumentMeta(size_bytes=1, page_count=1, word_count=1, text_source="ocr"),
    )


POLICY_ROWS = [
    (40, [(20, "Versicherungsschein-Nr.: NV-1234"), (300, "Zahlweise: jährlich")]),
    (60, [(20, "Versicherungsbeginn: 01.01.2026"), (300, "Ablauf: 01.01.2027")]),
    (80, [(20, "Jahresbeitrag: 186,40 EUR")]),
    (100, [(20, "Es gelten die Bedingungen in der jeweils gültigen Fassung des Vertrags.")]),
]


def name_of(doc: Document) -> str | None:
    kind = document_kinds.recognise(doc)
    return kind.name if kind else None


def test_each_insurance_kind_is_recognised_by_its_heading() -> None:
    assert name_of(titled("Versicherungsschein", POLICY_ROWS)) == "policy"
    assert name_of(titled("Nachtrag zum Versicherungsschein", [
        *POLICY_ROWS, (120, [(20, "Änderung zum: 01.07.2026")])])) == "contract_change"
    assert name_of(titled("Beitragsrechnung", [
        (40, [(20, "Versicherungsschein-Nr.: NV-1234"), (300, "Rechnungsdatum: 02.12.2025")]),
        (60, [(20, "Nettobeitrag: 100,00 EUR"), (300, "Fällig am: 01.01.2026")]),
        (80, [(20, "Gesamtbeitrag: 119,00 EUR")]),
        (100, [(20, "Bitte überweisen Sie den Betrag bis zum genannten Tag auf unser Konto.")]),
    ])) == "premium_invoice"


def test_the_head_of_a_heading_decides_between_policy_and_contract_change() -> None:
    # Both headings name the policy; only the first word names the kind.
    scores = document_kinds.scores(titled("Nachtrag zum Versicherungsschein", POLICY_ROWS))
    assert scores["contract_change"] - scores["policy"] >= document_kinds.MARGIN


def test_a_policy_number_label_is_no_policy_heading() -> None:
    # “Versicherungsschein-Nr.” stands on every premium invoice.
    doc = titled("Versicherungsschein-Nr. NV-1234", [(40, [(20, "Mit freundlichen Grüßen Ihre Gesellschaft")])])
    assert name_of(doc) is None


def test_a_document_that_fits_no_kind_gets_none() -> None:
    doc = titled("Schadenmeldung", [
        (40, [(20, "Versicherungsschein-Nr.: NV-1234")]),
        (60, [(20, "Schadentag: 14.03.2026")]),
        (80, [(20, "Der Schaden wurde der Polizei gemeldet und dort aufgenommen und bestätigt.")]),
    ])
    assert name_of(doc) is None


def test_labels_alone_do_not_decide_between_two_kinds() -> None:
    # No heading: policy and contract change share their labels.
    assert name_of(document(POLICY_ROWS)) is None


def test_a_document_that_fits_two_kinds_gets_none() -> None:
    doc = titled("Versicherungsschein", [
        *POLICY_ROWS,
        (130, [(20, "Beitragsrechnung")]),
        (150, [(20, "Rechnungsdatum: 02.12.2025"), (300, "Fällig am: 01.01.2026")]),
        (170, [(20, "Nettobeitrag: 100,00 EUR"), (300, "Gesamtbeitrag: 119,00 EUR")]),
        (190, [(20, "Versicherungszeitraum: 01.01.2026 - 31.12.2026")]),
    ])
    scores = document_kinds.scores(doc)
    assert scores["policy"] >= 4 and scores["premium_invoice"] >= 4
    assert name_of(doc) is None


def test_recognition_follows_the_yaml_file_not_the_code(tmp_path: Path) -> None:
    write_kind(tmp_path, "delivery_note", """\
name: delivery_note
title: Lieferschein
recognition:
  title_patterns: ['Lieferschein']
  minimum: 4
fields:
  - name: delivery_note_number
    label_rule:
      patterns: ['Lieferschein-Nr\\.?']
      value: identifier
""")
    kinds = document_kinds.load_all(builtin=tmp_path)
    doc = titled("Lieferschein", [(40, [(20, "Lieferschein-Nr.: LS-20817")])])
    assert document_kinds.recognise(doc, kinds).name == "delivery_note"

    # The same document under a stricter file is no longer clear enough.
    write_kind(tmp_path, "delivery_note", (tmp_path / "delivery_note.yml").read_text().replace("minimum: 4", "minimum: 10"))
    assert document_kinds.recognise(doc, document_kinds.load_all(builtin=tmp_path)) is None


def test_a_commercial_invoice_is_not_taken_for_a_premium_invoice(store) -> None:
    doc = store.load(str(CORPUS / "rechnung_din5008.pdf"))
    assert name_of(doc) == "invoice"


def test_a_sheet_without_located_words_gets_no_kind(store) -> None:
    assert name_of(store.load(str(CORPUS / "positionen.xlsx"))) is None


@pytest.mark.parametrize("file", ["neither_claim_report.pdf", "both_policy_and_invoice.pdf"])
def test_corpus_documents_outside_the_kinds_go_to_review(store, file: str) -> None:
    assert name_of(store.load(str(INSURANCE / file))) is None


def test_no_text_layer_document_of_the_corpus_gets_a_wrong_kind(store) -> None:
    entries = json.loads((INSURANCE / "truth.json").read_text(encoding="utf-8"))
    documents = [e for e in entries if e["kind"] and not e["scan"]]
    assert len(documents) == 60
    for entry in documents:
        assert name_of(store.load(str(INSURANCE / entry["file"]))) == entry["kind"], entry["file"]
