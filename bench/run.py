#!/usr/bin/env python3
"""Measure reading and rendering times and the steps from file to review.

Timings are a measurement, never a build gate: shared runners vary too much.
The step table follows one document from the folder to a reviewable result:
file stable, parse, OCR, recognition, extraction.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

os.environ.setdefault("SUBSTRAKT_DEV", "1")

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus" / "out"
PROTOCOLS = ROOT / "docs" / "measurements"


OPEN_BUDGET_PER_PAGE_MS = 100.0

# The folder watcher of the pilot (criterion Z3.1) reads a file only after its
# size has stopped changing. No watcher exists yet, so this wait is an assumed
# constant, not a measurement: one second between two looks at the file.
FILE_STABLE_MS = 1000.0
# Target of the pilot: a one-page text-layer PDF is reviewable within 3 s.
REVIEWABLE_TARGET_MS = 3000.0
INSURANCE = CORPUS / "insurance"


@dataclass
class Measurement:
    file: str
    kind: str
    pages: int
    words: int
    median_ms: float
    min_ms: float
    max_ms: float
    per_page_ms: float
    over_budget: bool


@dataclass
class Environment:
    system: str
    release: str
    machine: str
    processor: str
    cores: int
    python: str
    ram_gb: float | None


def environment() -> Environment:
    ram = None
    try:
        
        
        with open("/proc/meminfo") as f:
            for row in f:
                if row.startswith("MemTotal:"):
                    ram = round(int(row.split()[1]) / 1024 / 1024, 1)
                    break
    except OSError:
        pass

    return Environment(
        system=platform.system(),
        release=platform.release(),
        machine=platform.machine(),
        processor=platform.processor() or "unbekannt",
        cores=os.cpu_count() or 0,
        python=platform.python_version(),
        ram_gb=ram,
    )


def measure(fn, repetitions: int) -> tuple[float, float, float]:
    
    
    with contextlib.suppress(Exception):
        fn()

    times = []
    for _ in range(repetitions):
        start_time = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start_time) * 1000)
    return statistics.median(times), min(times), max(times)


def parse_measurements(repetitions: int) -> list[Measurement]:
    from substrakt.config import load
    from substrakt.store import DocumentStore

    files = sorted(
        p
        for p in CORPUS.glob("*")
        if p.suffix.lower() in {".pdf", ".xlsx", ".csv", ".png", ".tiff"}
        and not p.name.startswith(("defekt", "leer", "getarnt"))
    )

    results: list[Measurement] = []
    for path in files:
        
        # Use a fresh store so the measurement exercises the parser, not its cache.
        def run(p: Path = path) -> None:
            DocumentStore(load()).load(str(p))

        try:
            median, minimum, maximum = measure(run, repetitions)
            doc = DocumentStore(load()).load(str(path))
        except Exception as exc:
            print(f"  {path.name}: skipped ({exc})")
            continue

        per_page = median / max(doc.meta.page_count, 1)
        results.append(
            Measurement(
                file=path.name,
                kind=doc.kind,
                pages=doc.meta.page_count,
                words=doc.meta.word_count,
                median_ms=round(median, 1),
                min_ms=round(minimum, 1),
                max_ms=round(maximum, 1),
                per_page_ms=round(per_page, 1),
                over_budget=per_page > OPEN_BUDGET_PER_PAGE_MS,
            )
        )

    return results


def render_measurements(repetitions: int) -> list[Measurement]:
    from substrakt.config import load
    from substrakt.parsers.pdf import render_page
    from substrakt.store import DocumentStore

    store = DocumentStore(load())
    results: list[Measurement] = []

    for path in sorted(CORPUS.glob("*.pdf")):
        if path.name.startswith(("defekt", "getarnt")):
            continue
        try:
            doc = store.load(str(path))
            median, minimum, maximum = measure(
                lambda p=path: render_page(p, 0, scale=2.0), repetitions
            )
        except Exception as exc:
            print(f"  {path.name}: skipped ({exc})")
            continue

        results.append(
            Measurement(
                file=f"{path.name} (Rendern, 2×)",
                kind="render",
                pages=1,
                words=doc.meta.word_count,
                median_ms=round(median, 1),
                min_ms=round(minimum, 1),
                max_ms=round(maximum, 1),
                per_page_ms=round(median, 1),
                over_budget=median > 500,
            )
        )

    return results


@dataclass
class Steps:
    file: str
    source: str
    pages: int
    kind: str | None
    file_stable_ms: float
    parse_ms: float
    ocr_ms: float
    recognition_ms: float
    extraction_ms: float
    total_ms: float


def step_measurements(repetitions: int) -> list[Steps]:
    """Time each step per insurance document; the median of the runs counts."""
    from substrakt import document_kinds
    from substrakt.config import load
    from substrakt.extraction.fields import extract
    from substrakt.parsers import ocr
    from substrakt.store import DocumentStore

    # The parsers call OCR through the module, so a wrapper sees every call.
    spent = [0.0]

    def timed(fn):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                spent[0] += (time.perf_counter() - start) * 1000
        return wrapper

    original = ocr.read_image, ocr.read_pdf_page
    ocr.read_image, ocr.read_pdf_page = timed(ocr.read_image), timed(ocr.read_pdf_page)
    document_kinds.load_all()  # reading the kind files is start-up, not a step

    results: list[Steps] = []
    try:
        for path in sorted(p for p in INSURANCE.glob("*") if p.suffix in {".pdf", ".png"}):
            runs = []
            for _ in range(repetitions + 1):
                spent[0] = 0.0
                start = time.perf_counter()
                # A fresh store, so the parser runs instead of its cache.
                doc = DocumentStore(load()).load(str(path))
                loaded = time.perf_counter()
                kind = document_kinds.recognise(doc)
                recognised = time.perf_counter()
                if kind:
                    extract(doc, kind.fields, kind=kind)
                done = time.perf_counter()
                runs.append((
                    (loaded - start) * 1000 - spent[0], spent[0],
                    (recognised - loaded) * 1000, (done - recognised) * 1000,
                ))
            # The first run warms caches and is dropped, as in `measure`.
            parse, ocr_ms, recognition, extraction = (statistics.median(step) for step in zip(*runs[1:], strict=True))
            results.append(Steps(
                file=path.name,
                source=doc.meta.text_source,
                pages=doc.meta.page_count,
                kind=kind.name if kind else None,
                file_stable_ms=FILE_STABLE_MS,
                parse_ms=round(parse, 1),
                ocr_ms=round(ocr_ms, 1),
                recognition_ms=round(recognition, 1),
                extraction_ms=round(extraction, 1),
                total_ms=round(FILE_STABLE_MS + parse + ocr_ms + recognition + extraction, 1),
            ))
    finally:
        ocr.read_image, ocr.read_pdf_page = original
    return results


def step_table(steps: list[Steps]) -> str:
    rows = [
        "### Steps from file to reviewable result",
        "",
        "| File | Text from | Kind | File stable (assumed) | Parse | OCR | Recognition | Extraction | Total |",
        "|---|---|---|--:|--:|--:|--:|--:|--:|",
    ]
    for m in steps:
        rows.append(
            f"| `{m.file}` | {m.source} | {m.kind or 'none'} | {m.file_stable_ms:.0f} ms | {m.parse_ms:.1f} ms | "
            f"{m.ocr_ms:.1f} ms | {m.recognition_ms:.1f} ms | {m.extraction_ms:.1f} ms | {m.total_ms:.1f} ms |"
        )
    return "\n".join(rows)


def step_summary(steps: list[Steps]) -> str:
    """Say where the 3 s target stands, per source of the text."""
    rows = []
    for source, label in (("text_layer", "one-page text-layer PDFs"), ("ocr", "one-page scans read by OCR")):
        totals = [m.total_ms for m in steps if m.source == source and m.pages == 1]
        if totals:
            within = sum(t <= REVIEWABLE_TARGET_MS for t in totals)
            rows.append(
                f"- {len(totals)} {label}: median {statistics.median(totals):.0f} ms, slowest {max(totals):.0f} ms, "
                f"{within} of {len(totals)} within {REVIEWABLE_TARGET_MS:.0f} ms."
            )
    rows.append(
        f"- Each total contains {FILE_STABLE_MS:.0f} ms for “file stable”. That wait is an assumption until "
        "the folder watcher exists; the other steps are measured."
    )
    return "\n".join(rows)


def table(title: str, measurements: list[Measurement]) -> str:
    rows = [
        f"### {title}",
        "",
        "| File | Kind | Pages | Words | Median | per page | Budget |",
        "|---|---|--:|--:|--:|--:|:--:|",
    ]
    for m in measurements:
        mark = "❌" if m.over_budget else "✓"
        rows.append(
            f"| `{m.file}` | {m.kind} | {m.pages} | {m.words} | "
            f"{m.median_ms:.1f} ms | {m.per_page_ms:.1f} ms | {mark} |"
        )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--repetitions", type=int, default=5)
    parser.add_argument("--timestamp", default="", help="ISO timestamp for the report")
    parser.add_argument("--write", action="store_true", help="Write a report")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when the target-hardware budget is exceeded",
    )
    args = parser.parse_args()

    if not CORPUS.exists() or not any(CORPUS.iterdir()):
        print("The test corpus is missing. Run `python corpus/generate.py` first.")
        return 1

    env = environment()
    print(f"Environment: {env.system} {env.machine}, {env.cores} cores, "
          f"{env.ram_gb or '?'} GB RAM, Python {env.python}")
    print(f"Repetitions per measurement: {args.repetitions}\n")

    print("Reading documents …")
    parsing = parse_measurements(args.repetitions)
    print("Rendering pages …")
    rendering = render_measurements(args.repetitions)

    steps: list[Steps] = []
    if INSURANCE.is_dir():
        print("Following insurance documents from file to review …")
        steps = step_measurements(args.repetitions)

    print()
    print(table("Reading", parsing))
    print()
    print(table("Rendering", rendering))
    if steps:
        print()
        print(step_table(steps))
        print()
        print(step_summary(steps))

    exceeded = [m for m in parsing + rendering if m.over_budget]
    print()
    if exceeded:
        print(f"{len(exceeded)} measurement(s) over budget:")
        for m in exceeded:
            print(f"  - {m.file}: {m.per_page_ms:.1f} ms per page")
        if not args.strict:
            print(
                "\nWithout --strict this is only a report. Timings on shared CI "
                "runners are too noisy to enforce target-hardware budgets."
            )
    else:
        print("All measurements are within budget.")

    if args.write:
        PROTOCOLS.mkdir(parents=True, exist_ok=True)
        mark = args.timestamp or "current"
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in mark)

        json_path = PROTOCOLS / f"measurement-{safe}.json"
        json_path.write_text(
            json.dumps(
                {
                    "environment": asdict(env),
                    "repetitions": args.repetitions,
                    "reading": [asdict(m) for m in parsing],
                    "rendering": [asdict(m) for m in rendering],
                    "steps": [asdict(m) for m in steps],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        md_path = PROTOCOLS / f"measurement-{safe}.md"
        md_path.write_text(
            "\n\n".join(
                [
                    f"# Measurement report {mark}",
                    f"**Environment:** {env.system} {env.release} · {env.machine} · "
                    f"{env.cores} cores · {env.ram_gb or '?'} GB RAM · Python {env.python}",
                    f"**Repetitions per measurement:** {args.repetitions} (median shown)",
                    table("Reading", parsing),
                    table("Rendering", rendering),
                    *([step_table(steps), step_summary(steps)] if steps else []),
                    "> Measured on the development machine. The target is a 16 GB "
                    "laptop without a GPU and may be slower.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nReport: {md_path}")

    return 1 if (exceeded and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
