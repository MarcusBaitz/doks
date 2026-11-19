"""Synthetic German insurance documents with ground truth.

Three kinds a broker receives for a contract: policy, contract change and
premium invoice. Every insurer, person, number and amount is invented.

Each kind is printed in five layouts. Layouts ``a`` to ``c`` are the tuning
set: the label patterns in ``sidecar/substrakt/document_kinds/`` may be
adjusted until these read well. Layouts ``d`` and ``e`` are held out: they use
other words, other number and amount formats and other arrangements, and no
pattern was changed after looking at their result. Reporting both figures
keeps the measurement from being a test on its own training data.

The truth holds what is printed, in canonical form: ISO dates, numbers, and
the canonical term for line of business and payment mode. A value a layout
does not print is ``None``; reading one anyway is an error.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

WIDTH, HEIGHT = A4
FOLDER = "insurance"
TRUTH = "truth.json"
HELD_OUT = ("d", "e")

INSURERS = [
    ("Nordlicht Versicherung AG", "Hafenkai 12", "24999 Beispielstadt"),
    ("Hansekontor Sachversicherung AG", "Speicherweg 3", "20999 Musterhafen"),
    ("Alpenrand Versicherung a. G.", "Gipfelstraße 40", "80999 Musterberg"),
    ("Wattenmeer Assekuranz SE", "Deichstraße 7", "26999 Beispielsiel"),
]

HOLDERS = [
    ("Herrn", "Jonas Brandt", "Musterweg 4", "24999 Beispielstadt"),
    ("Frau", "Mira Lindqvist", "Am Probenhang 18", "80999 Musterberg"),
    ("Firma", "Tischlerei Okafor", "Werkhof 2", "20999 Musterhafen"),
    ("Frau", "Dr. Selma Achterberg", "Beispielallee 61", "26999 Beispielsiel"),
]

# Canonical line of business → spelling printed on the document.
LINES = [
    ("Hausrat", "Hausratversicherung"),
    ("Privathaftpflicht", "Privathaftpflichtversicherung"),
    ("Kraftfahrt", "Kraftfahrtversicherung"),
    ("Wohngebäude", "Wohngebäudeversicherung"),
    ("Betriebshaftpflicht", "Betriebshaftpflichtversicherung"),
    ("Rechtsschutz", "Rechtsschutzversicherung"),
]

MODES = ["jährlich", "halbjährlich", "vierteljährlich", "monatlich"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]

NUMERIC = "numeric"
SPELLED = "spelled"


def euro(amount: float) -> str:
    return f"{amount:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def printed_date(value: dt.date, style: str) -> str:
    if style == SPELLED:
        return f"{value.day}. {MONTHS[value.month - 1]} {value.year}"
    return value.strftime("%d.%m.%Y")


# --- Layouts ---------------------------------------------------------------
#
# A layout names where each value stands and under which label. ``info`` is
# the block right of the address, ``rows`` the body, ``amounts`` the block of
# sums. A field that appears in none of them is not printed, except the
# insurer (letterhead) and the policyholder (address), which always are.
# The pseudo-field ``period`` prints both period dates behind one label.

POLICY = {
    "a": dict(
        title="Versicherungsschein", size=14, style="rows", colon=True, dates=NUMERIC, money="{} EUR",
        info=[("Versicherungsschein-Nr.", "policy_number"), ("Ausfertigungsdatum", "issue_date")],
        rows=[("Versicherungsnehmer", "policyholder"), ("Sparte", "line_of_business"),
              ("Versicherungsbeginn", "start_date"), ("Ablauf", "end_date"), ("Zahlweise", "payment_mode")],
        amounts=[("Nettobeitrag", "net_premium"), ("Jahresbeitrag", "annual_premium")],
    ),
    "b": dict(
        title="Versicherungsschein zur {line}", size=13, beside=True, style="grid", colon=False,
        dates=NUMERIC, money="{} €",
        info=[],
        rows=[("Versicherungsnummer", "policy_number"), ("Beginn", "start_date"),
              ("Vertragsablauf", "end_date"), ("Zahlungsweise", "payment_mode")],
        amounts=[("Beitrag inkl. Versicherungsteuer", "premium")],
    ),
    "c": dict(
        title="Police", size=16, style="above", colon=False, dates=SPELLED, money="{} EUR",
        info=[("Datum", "issue_date")],
        rows=[("Versicherer", "insurer"), ("Police Nr.", "policy_number"), ("Versicherungsnehmer", "policyholder"),
              ("Versicherungsart", "line_of_business"), ("Vertragsbeginn", "start_date"),
              ("Versicherungsablauf", "end_date")],
        amounts=[("Gesamtbeitrag", "premium")],
    ),
    "d": dict(
        title="Ihr Versicherungsschein", size=14, style="rows", colon=True, dates=NUMERIC, money="EUR {}",
        info=[("VS-Nr.", "policy_number"), ("Ausgestellt am", "issue_date")],
        rows=[("Versicherungsnehmerin", "policyholder"), ("Versichertes Risiko", "line_of_business"),
              ("Vertragsdauer", "period"), ("Zahlungsperiode", "payment_mode")],
        amounts=[("Beitrag ohne Versicherungsteuer", "net_premium"), ("Beitrag je Zahlungsabschnitt", "premium")],
        digit_groups=True,
    ),
    "e": dict(
        title="VERSICHERUNGSSCHEIN", size=10, style="above", colon=False, dates=NUMERIC, money="{} EUR",
        info=[("Unser Zeichen", "policy_number")],
        rows=[("Vertragsnummer", "policy_number"), ("Produkt", "line_of_business"), ("Beginn der Versicherung", "start_date"),
              ("Ablauf der Versicherung", "end_date"), ("Zahlungsart", "payment_mode"), ("Bruttobeitrag", "premium")],
        amounts=[],
    ),
}

CHANGE = {
    "a": dict(
        title="Nachtrag Nr. {change} zum Versicherungsschein Nr. {number}", size=13, style="rows", colon=True,
        dates=NUMERIC, money="{} EUR",
        info=[("Ausfertigungsdatum", "issue_date")],
        rows=[("Versicherungsnehmer", "policyholder"), ("Sparte", "line_of_business"),
              ("Änderung zum", "change_date"), ("Versicherungsbeginn", "start_date"), ("Ablauf", "end_date"),
              ("Zahlweise", "payment_mode")],
        amounts=[("Nettobeitrag", "net_premium"), ("Neuer Beitrag", "premium")],
    ),
    "b": dict(
        title="Nachtrag zur {line}", size=14, beside=True, style="grid", colon=False, dates=NUMERIC, money="{} €",
        info=[],
        rows=[("Versicherungsschein-Nr.", "policy_number"), ("Nachtragsnummer", "change_number"),
              ("Wirksam ab", "change_date"), ("Zahlungsweise", "payment_mode")],
        amounts=[("Beitrag inkl. Versicherungsteuer", "premium")],
    ),
    "c": dict(
        title="Änderungsmitteilung", size=15, style="above", colon=False, dates=SPELLED, money="{} EUR",
        info=[("Datum", "issue_date")],
        rows=[("Versicherer", "insurer"), ("Vertragsnummer", "policy_number"), ("Versicherungsnehmer", "policyholder"),
              ("Versicherungsart", "line_of_business"), ("Gültig ab", "change_date"), ("Vertragsablauf", "end_date")],
        amounts=[("Gesamtbeitrag", "premium")],
    ),
    "d": dict(
        title="Nachtrag zu Ihrem Vertrag", size=14, style="rows", colon=True, dates=NUMERIC, money="EUR {}",
        info=[("VS-Nr.", "policy_number"), ("Nachtrag Nr.", "change_number"), ("Ausgestellt am", "issue_date")],
        rows=[("Versicherungsnehmerin", "policyholder"), ("Versichertes Risiko", "line_of_business"),
              ("Die Änderung gilt ab dem", "change_date"), ("Zahlungsperiode", "payment_mode")],
        amounts=[("Bisheriger Beitrag", "old_premium"), ("Beitrag je Zahlungsabschnitt", "premium")],
        digit_groups=True,
    ),
    "e": dict(
        title="NACHTRAG", size=10, style="above", colon=False, dates=NUMERIC, money="{} EUR",
        info=[],
        rows=[("Vertragsnummer", "policy_number"), ("Produkt", "line_of_business"), ("Änderungsdatum", "change_date"),
              ("Ablauf der Versicherung", "end_date"), ("Zahlungsart", "payment_mode"), ("Bruttobeitrag", "premium")],
        amounts=[],
    ),
}

INVOICE = {
    "a": dict(
        title="Beitragsrechnung", size=14, style="rows", colon=True, dates=NUMERIC, money="{} EUR",
        info=[("Versicherungsschein-Nr.", "policy_number"), ("Rechnungsdatum", "invoice_date")],
        rows=[("Versicherungsnehmer", "policyholder"), ("Sparte", "line_of_business"),
              ("Versicherungszeitraum", "period"), ("Zahlweise", "payment_mode"), ("Fällig am", "due_date")],
        amounts=[("Nettobeitrag", "net_premium"), ("Versicherungsteuer 19 %", "insurance_tax"),
                 ("Gesamtbeitrag", "premium")],
    ),
    "b": dict(
        title="Beitragsrechnung zur {line}", size=13, beside=True, style="grid", colon=False, dates=NUMERIC,
        money="{} €", period="vom {} bis {}",
        info=[],
        rows=[("Versicherungsnummer", "policy_number"), ("Datum", "invoice_date"),
              ("Zeitraum", "period"), ("Fälligkeit", "due_date")],
        amounts=[("Nettobeitrag", "net_premium"), ("Versicherungsteuer", "insurance_tax"),
                 ("Zu zahlender Betrag", "premium")],
    ),
    "c": dict(
        title="Beitragsmitteilung", size=15, style="above", colon=False, dates=SPELLED, money="{} EUR",
        period="{} bis {}",
        info=[("Rechnungsdatum", "invoice_date")],
        rows=[("Versicherer", "insurer"), ("Vertragsnummer", "policy_number"), ("Versicherungsnehmer", "policyholder"),
              ("Versicherungsart", "line_of_business"), ("Beitragszeitraum", "period"), ("Zahlbar bis", "due_date")],
        amounts=[("Beitrag ohne Versicherungsteuer", "net_premium"), ("Versicherungsteuer 19 %", "insurance_tax"),
                 ("Beitrag inkl. Versicherungsteuer", "premium")],
    ),
    "d": dict(
        title="Rechnung über den Versicherungsbeitrag", size=14, style="rows", colon=True, dates=NUMERIC,
        money="EUR {}",
        info=[("VS-Nr.", "policy_number"), ("Rechnung vom", "invoice_date")],
        rows=[("Versicherungsnehmerin", "policyholder"), ("Versichertes Risiko", "line_of_business"),
              ("Abrechnungszeitraum von", "period_start"), ("Abrechnungszeitraum bis", "period_end"),
              ("Zahlungsperiode", "payment_mode"), ("Bitte zahlen Sie bis zum", "due_date")],
        amounts=[("Beitrag", "net_premium"), ("zzgl. Versicherungsteuer", "insurance_tax"),
                 ("Rechnungsbetrag", "premium")],
        digit_groups=True,
    ),
    "e": dict(
        title="BEITRAGSRECHNUNG", size=10, style="above", colon=False, dates=NUMERIC, money="{} EUR",
        period="{} – {}",
        info=[],
        rows=[("Vertragsnummer", "policy_number"), ("Produkt", "line_of_business"), ("Belegdatum", "invoice_date"),
              ("Zeitraum", "period"), ("Fälligkeitsdatum", "due_date"), ("Zahlbetrag", "premium")],
        amounts=[],
    ),
}

KINDS = {"policy": POLICY, "contract_change": CHANGE, "premium_invoice": INVOICE}
DATES = {"issue_date", "start_date", "end_date", "change_date", "invoice_date", "period_start", "period_end", "due_date"}
MONEY = {"premium", "annual_premium", "net_premium", "insurance_tax", "old_premium"}


def record(rng: random.Random, index: int, digit_groups: bool) -> dict:
    """One contract with every value any layout may print, in canonical form."""
    insurer = INSURERS[index % len(INSURERS)]
    holder = HOLDERS[(index + rng.randrange(len(HOLDERS))) % len(HOLDERS)]
    canonical, printed = rng.choice(LINES)
    start = dt.date(rng.choice([2024, 2025, 2026]), rng.choice([1, 4, 7, 10]), 1)
    mode = rng.choice(MODES)
    net = round(rng.uniform(40, 1900), 2)
    tax = round(net * 0.19, 2)
    initials = "".join(word[0] for word in insurer[0].split()[:2]).upper()
    number = (
        f"{rng.randrange(10, 99)} {rng.randrange(100, 999)} {rng.randrange(100, 999)}"
        if digit_groups
        else rng.choice([
            f"{initials}-{canonical[:2].upper()}-{rng.randrange(1000, 9999)}-{rng.randrange(1000, 9999)}",
            f"{rng.randrange(1000000, 9999999)}/{rng.randrange(1000, 9999)}",
            f"{initials}{rng.randrange(100000, 999999)}",
        ])
    )
    return {
        "insurer": insurer[0], "insurer_street": insurer[1], "insurer_city": insurer[2],
        "salutation": holder[0], "policyholder": holder[1], "street": holder[2], "city": holder[3],
        "line_of_business": canonical, "line_printed": printed,
        "policy_number": number,
        "change_number": str(rng.randrange(1, 9)),
        "start_date": start,
        "end_date": start.replace(year=start.year + rng.choice([1, 3])),
        "issue_date": start - dt.timedelta(days=rng.randrange(10, 40)),
        "change_date": start.replace(year=start.year + 1, month=rng.choice([2, 5, 8, 11])),
        "invoice_date": start - dt.timedelta(days=rng.randrange(20, 35)),
        "period_start": start,
        "period_end": start.replace(year=start.year + 1) - dt.timedelta(days=1),
        "due_date": start,
        "payment_mode": mode,
        "net_premium": net, "insurance_tax": tax, "premium": round(net + tax, 2),
        "annual_premium": round(net + tax, 2),
        "old_premium": round(net * 0.9, 2),
    }


def printed(layout: dict, rec: dict, field: str) -> str:
    """The text a layout prints for a field."""
    if field == "period":
        pattern = layout.get("period", "{} - {}")
        return pattern.format(printed_date(rec["period_start"], layout["dates"]),
                              printed_date(rec["period_end"], layout["dates"]))
    if field in DATES:
        return printed_date(rec[field], layout["dates"])
    if field in MONEY:
        return layout["money"].format(euro(rec[field]))
    if field == "line_of_business":
        return rec["line_printed"]
    return str(rec[field])


def truth(kind: str, layout: dict, rec: dict) -> dict:
    """Canonical values of what this layout prints; ``None`` if it prints none."""
    on_paper = {"insurer", "policyholder"}
    for _, field in [*layout["info"], *layout["rows"], *layout["amounts"]]:
        on_paper.update({"period_start", "period_end"} if field == "period" else {field})
    if "{line}" in layout["title"]:
        on_paper.add("line_of_business")
    if "{change}" in layout["title"]:
        on_paper.update({"change_number", "policy_number"})
    # A policy printed with “Vertragsdauer” still states start and end.
    if kind != "premium_invoice" and "period_start" in on_paper:
        on_paper.update({"start_date", "end_date"})

    values = {}
    for field in sorted(on_paper - {"old_premium"}):
        value = rec[field]
        values[field] = value.isoformat() if isinstance(value, dt.date) else value
    return values


def draw(path: Path, kind: str, layout: dict, rec: dict) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Synthetisches Muster")
    title = layout["title"].format(line=rec["line_printed"], number=rec["policy_number"],
                                   change=rec["change_number"])
    bold = "Helvetica-Bold"

    # Letterhead, with the heading beside it in some layouts.
    c.setFont(bold, 12)
    c.drawString(25 * mm, HEIGHT - 22 * mm, rec["insurer"])
    c.setFont("Helvetica", 7)
    c.drawString(25 * mm, HEIGHT - 44 * mm,
                 f"{rec['insurer']} · {rec['insurer_street']} · {rec['insurer_city']}")

    # Address block of the letter.
    c.setFont("Helvetica", 10)
    for i, line in enumerate([rec["salutation"], rec["policyholder"], rec["street"], rec["city"]]):
        c.drawString(25 * mm, HEIGHT - 50 * mm - i * 5 * mm, line)

    colon = ":" if layout["colon"] else ""
    c.setFont("Helvetica", 9)
    for i, (label, field) in enumerate(layout["info"]):
        y = HEIGHT - 50 * mm - i * 5 * mm
        c.drawString(120 * mm, y, label + colon)
        c.drawString(160 * mm, y, printed(layout, rec, field))

    y = HEIGHT - 88 * mm
    c.setFont(bold, layout["size"])
    if layout.get("beside"):
        c.drawRightString(190 * mm, HEIGHT - 32 * mm, title)
    else:
        c.drawString(25 * mm, y, title)
        y -= 12 * mm

    rows = layout["rows"]
    if layout["style"] == "rows":
        for label, field in rows:
            c.setFont("Helvetica", 9)
            c.drawString(25 * mm, y, label + colon)
            c.drawString(85 * mm, y, printed(layout, rec, field))
            y -= 6 * mm
    elif layout["style"] == "grid":
        for i in range(0, len(rows), 2):
            for (label, field), (x_label, x_value) in zip(rows[i:i + 2], [(25, 62), (112, 150)], strict=False):
                c.setFont("Helvetica", 9)
                c.drawString(x_label * mm, y, label + colon)
                c.drawString(x_value * mm, y, printed(layout, rec, field))
            y -= 7 * mm
    else:  # label above its value, three cells in a row
        for i in range(0, len(rows), 3):
            for (label, field), x in zip(rows[i:i + 3], [25, 85, 140], strict=False):
                c.setFont("Helvetica", 7.5)
                c.drawString(x * mm, y, label.upper() if layout["size"] <= 10 else label)
                c.setFont("Helvetica", 9.5)
                c.drawString(x * mm, y - 4.5 * mm, printed(layout, rec, field))
            y -= 13 * mm

    y -= 6 * mm
    for label, field in layout["amounts"]:
        c.setFont(bold if field == "premium" else "Helvetica", 9)
        c.drawString(110 * mm, y, label + ("" if label.endswith("%") else colon))
        c.drawRightString(190 * mm, y, printed(layout, rec, field))
        y -= 5.5 * mm

    # Running text with the words that also serve as labels elsewhere.
    y -= 8 * mm
    c.setFont("Helvetica", 8.5)
    prose = [
        f"Es gelten die Allgemeinen Bedingungen für die {rec['line_printed']} in der jeweils gültigen Fassung.",
        f"Der Beitrag ist {rec['payment_mode']} im Voraus zu zahlen. Bitte prüfen Sie alle Angaben; der",
        "Versicherungsnehmer hat Änderungen des Risikos unverzüglich in Textform anzuzeigen.",
    ]
    if kind == "premium_invoice":
        prose.append("Diese Rechnung gehört zu Ihrem Versicherungsschein. Ein Nachtrag wird nicht erstellt.")
    else:
        prose.append("Dieser Versicherungsschein und seine Nachträge ersetzen alle früheren Fassungen.")
    for line in prose:
        c.drawString(25 * mm, y, line)
        y -= 4.5 * mm

    c.setFont("Helvetica", 7)
    c.drawString(25 * mm, 16 * mm, f"{rec['insurer']} · Sitz der Gesellschaft: {rec['insurer_city'][6:]} · "
                                   "Muster mit erfundenen Daten")
    c.showPage()
    c.save()


def other_documents(folder: Path) -> list[dict]:
    """Documents that are none of the kinds, or two of them at once."""
    entries = []

    neither = folder / "neither_claim_report.pdf"
    c = canvas.Canvas(str(neither), pagesize=A4)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(25 * mm, HEIGHT - 22 * mm, INSURERS[0][0])
    c.setFont("Helvetica-Bold", 14)
    c.drawString(25 * mm, HEIGHT - 88 * mm, "Schadenmeldung")
    c.setFont("Helvetica", 9)
    for i, (label, value) in enumerate([
        ("Versicherungsschein-Nr.:", "NV-HA-2210-4471"), ("Versicherungsnehmer:", "Jonas Brandt"),
        ("Schadentag:", "14.03.2026"), ("Schadenort:", "Musterweg 4, 24999 Beispielstadt"),
        ("Schadenhöhe:", "ca. 1.200,00 EUR"),
    ]):
        c.drawString(25 * mm, HEIGHT - 100 * mm - i * 6 * mm, label)
        c.drawString(85 * mm, HEIGHT - 100 * mm - i * 6 * mm, value)
    c.save()
    entries.append({"file": neither.name, "kind": None, "case": "fits no kind"})

    both = folder / "both_policy_and_invoice.pdf"
    c = canvas.Canvas(str(both), pagesize=A4)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(25 * mm, HEIGHT - 22 * mm, INSURERS[1][0])
    y = HEIGHT - 70 * mm
    for heading, rows in [
        ("Versicherungsschein", [("Versicherungsschein-Nr.:", "HS-PR-1180-7745"), ("Versicherungsbeginn:", "01.01.2026"),
                                 ("Ablauf:", "01.01.2027"), ("Zahlweise:", "jährlich")]),
        ("Beitragsrechnung", [("Rechnungsdatum:", "02.12.2025"), ("Fällig am:", "01.01.2026"),
                              ("Nettobeitrag:", "100,00 EUR"), ("Gesamtbeitrag:", "119,00 EUR")]),
    ]:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(25 * mm, y, heading)
        c.setFont("Helvetica", 9)
        for label, value in rows:
            y -= 6 * mm
            c.drawString(25 * mm, y, label)
            c.drawString(85 * mm, y, value)
        y -= 16 * mm
    c.save()
    entries.append({"file": both.name, "kind": None, "case": "fits two kinds"})
    return entries


def generate(output: Path, seed: int, as_scan) -> list[tuple[Path, str]]:
    """Write all documents and the truth file; return what was written."""
    rng = random.Random(seed)
    folder = output / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    written: list[tuple[Path, str]] = []

    for kind, layouts in KINDS.items():
        for letter, layout in layouts.items():
            for index in range(4):
                rec = record(rng, index, layout.get("digit_groups", False) and index == 3)
                pdf = folder / f"{kind}_{letter}_{index + 1}.pdf"
                draw(pdf, kind, layout, rec)
                entry = {
                    "file": pdf.name, "kind": kind, "layout": letter,
                    "set": "held_out" if letter in HELD_OUT else "tuning",
                    "scan": False, "values": truth(kind, layout, rec),
                }
                entries.append(entry)
                written.append((pdf, f"{kind}, layout {letter}, text layer"))
                # Two of four become scans: one sharp, one coarse.
                if dpi := {0: 300, 1: 150}.get(index):
                    scan = folder / f"{kind}_{letter}_{index + 1}_scan{dpi}.png"
                    as_scan(pdf, scan, dpi, rng)
                    entries.append({**entry, "file": scan.name, "scan": True, "dpi": dpi})
                    written.append((scan, f"{kind}, layout {letter}, scan at {dpi} dpi"))

    for entry in other_documents(folder):
        entries.append(entry)
        written.append((folder / entry["file"], f"not a kind: {entry['case']}"))

    (folder / TRUTH).write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return written
