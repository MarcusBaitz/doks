#!/usr/bin/env python3
"""Evaluate kind recognition and extraction on the synthetic insurance corpus.

Reads every document of ``corpus/out/insurance`` through the production path
(store, recognition, extraction), compares each value with the ground truth
and counts, per kind, what a clerk would see: read correctly, sent to review,
missing — and the one outcome that must not happen, a wrong value delivered
without a review flag.

The corpus is synthetic. The figures say how the rules behave on layouts
somebody invented, not how they behave on an insurer's real documents.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

os.environ.setdefault("SUBSTRAKT_DEV", "1")

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus" / "out" / "insurance"
PROTOCOLS = ROOT / "docs" / "measurements"

# Outcomes of one value. Only WRONG breaks the promise of criterion Z2.5.
CORRECT = "correct"                # delivered without a flag and right
REVIEW_CORRECT = "review_correct"  # right, but sent to review
REVIEW_WRONG = "review_wrong"      # wrong, and sent to review
MISSING = "missing"                # printed, not found; the clerk is asked
ABSENT = "absent"                  # not printed and not delivered
WRONG = "wrong"                    # delivered without a flag, and wrong


@dataclass
class Value:
    file: str
    kind: str
    set: str
    scan: bool
    field: str
    outcome: str
    located: bool


@dataclass
class Recognised:
    file: str
    expected: str | None
    recognised: str | None
    set: str
    scan: bool


def truth() -> list[dict]:
    return json.loads((CORPUS / "truth.json").read_text(encoding="utf-8"))


def _same(field, result, expected) -> bool:
    """Compare in canonical form: ISO date, number, canonical term, or text."""
    rule = field.label_rule
    if field.json_type == "date" or (rule and rule.value == "term"):
        return result.normalized == expected
    if field.json_type == "number":
        return isinstance(result.normalized, float) and abs(result.normalized - expected) < 0.005
    return " ".join(str(result.value).split()).casefold() == " ".join(str(expected).split()).casefold()


def outcome(field, result, expected) -> str:
    delivered = result.grounded and result.value is not None
    if delivered:
        return CORRECT if expected is not None and _same(field, result, expected) else WRONG
    if expected is None:
        return ABSENT
    if result.value is None:
        return MISSING
    return REVIEW_CORRECT if _same(field, result, expected) else REVIEW_WRONG


def evaluate(entries: list[dict]) -> tuple[list[Recognised], list[Value]]:
    from substrakt import document_kinds
    from substrakt.config import load
    from substrakt.extraction.fields import extract
    from substrakt.model import ImageRect, PdfRect
    from substrakt.store import DocumentStore

    store = DocumentStore(load())
    kinds: list[Recognised] = []
    values: list[Value] = []
    for entry in entries:
        doc = store.load(str(CORPUS / entry["file"]))
        kind = document_kinds.recognise(doc)
        scan = bool(entry.get("scan"))
        group = entry.get("set", "other")
        kinds.append(Recognised(entry["file"], entry["kind"], kind.name if kind else None, group, scan))
        # Without the right kind no value is delivered: the document is in review.
        if kind is None or kind.name != entry["kind"]:
            continue
        run = extract(doc, kind.fields, kind=kind)
        for field, result in zip(kind.fields, run.results, strict=True):
            values.append(Value(
                entry["file"], kind.name, group, scan, field.name,
                outcome(field, result, entry["values"].get(field.name)),
                isinstance(result.locator, (ImageRect, PdfRect)),
            ))
    return kinds, values


def summary(kinds: list[Recognised], values: list[Value]) -> list[dict]:
    """One row per kind, set and source."""
    rows = []
    groups = sorted({(k.expected, k.set, k.scan) for k in kinds if k.expected})
    for kind, group, scan in groups:
        documents = [k for k in kinds if (k.expected, k.set, k.scan) == (kind, group, scan)]
        counts = Counter(v.outcome for v in values if (v.kind, v.set, v.scan) == (kind, group, scan))
        printed = sum(counts[o] for o in (CORRECT, REVIEW_CORRECT, REVIEW_WRONG, MISSING))
        rows.append({
            "kind": kind, "set": group, "source": "scan" if scan else "text layer",
            "documents": len(documents),
            "kind_recognised": sum(k.recognised == kind for k in documents),
            "kind_to_review": sum(k.recognised is None for k in documents),
            "kind_wrong": sum(k.recognised not in (None, kind) for k in documents),
            "values_printed": printed,
            **{o: counts[o] for o in (CORRECT, REVIEW_CORRECT, REVIEW_WRONG, MISSING, WRONG)},
            "share_correct": round(counts[CORRECT] / printed, 3) if printed else None,
            "share_right_value": round((counts[CORRECT] + counts[REVIEW_CORRECT]) / printed, 3) if printed else None,
        })
    return rows


def table(rows: list[dict]) -> str:
    lines = [
        "| Kind | Set | Source | Documents | Kind recognised | Kind to review | Kind wrong | Values printed | "
        "Correct | Right, in review | Wrong, in review | Missing | Wrong without flag | Share correct | "
        "Share right value |",
        "|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        share = "–" if r["share_correct"] is None else f"{r['share_correct']:.1%}"
        right = "–" if r["share_right_value"] is None else f"{r['share_right_value']:.1%}"
        lines.append(
            f"| {r['kind']} | {r['set']} | {r['source']} | {r['documents']} | {r['kind_recognised']} | "
            f"{r['kind_to_review']} | {r['kind_wrong']} | {r['values_printed']} | {r[CORRECT]} | "
            f"{r[REVIEW_CORRECT]} | {r[REVIEW_WRONG]} | {r[MISSING]} | {r[WRONG]} | {share} | {right} |"
        )
    return "\n".join(lines)


def by_field(values: list[Value]) -> str:
    lines = ["| Kind | Value | Set | Correct | Right, in review | Wrong, in review | Missing | Wrong without flag |",
             "|---|---|---|--:|--:|--:|--:|--:|"]
    for kind, field, group in sorted({(v.kind, v.field, v.set) for v in values}):
        counts = Counter(v.outcome for v in values if (v.kind, v.field, v.set) == (kind, field, group))
        if sum(counts.values()) == counts[ABSENT]:
            continue
        lines.append(f"| {kind} | {field} | {group} | {counts[CORRECT]} | {counts[REVIEW_CORRECT]} | "
                     f"{counts[REVIEW_WRONG]} | {counts[MISSING]} | {counts[WRONG]} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", metavar="DATE", help="Write the raw result as insurance-kinds-DATE.json")
    args = parser.parse_args()
    if not (CORPUS / "truth.json").exists():
        print("The insurance corpus is missing. Run `npm run corpus` first.")
        return 1

    from substrakt.parsers import ocr

    entries = truth()
    if not ocr.available():
        print("Tesseract or its German data is missing: scans are left out.\n")
        entries = [e for e in entries if not e.get("scan")]

    kinds, values = evaluate(entries)
    rows = summary(kinds, values)
    print(table(rows))
    print()
    print(by_field(values))
    print()
    for k in kinds:
        if k.expected is None:
            print(f"{k.file}: expected no kind, recognised {k.recognised}")
    wrong = [v for v in values if v.outcome == WRONG]
    wrong_kinds = [k for k in kinds if k.recognised not in (None, k.expected)]
    for v in wrong:
        print(f"WRONG WITHOUT FLAG: {v.file} {v.field}")
    for k in wrong_kinds:
        print(f"WRONG KIND: {k.file} recognised as {k.recognised}")

    if args.write:
        target = PROTOCOLS / f"insurance-kinds-{args.write}.json"
        target.write_text(json.dumps({
            "corpus": "synthetic, corpus/insurance.py",
            "summary": rows,
            "kinds": [asdict(k) for k in kinds],
            "values": [asdict(v) for v in values],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nRaw result: {target}")
    return 1 if wrong or wrong_kinds else 0


if __name__ == "__main__":
    sys.exit(main())
