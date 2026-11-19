# Insurance document kinds on the synthetic corpus

Date: 10 November 2026 · measured for the broker pilot

**The corpus is synthetic.** Every document was drawn by
`corpus/insurance.py` from layouts somebody invented. The figures say how the
rules in the kind files behave on those layouts. They say nothing about the
documents of a real insurer; that needs a measurement on real, anonymised
documents, which the contract lists as outside the pilot's scope.

## Environment

- Development machine: Linux 6.6 under WSL2, x86_64, 16 cores, 15.6 GB RAM, Python 3.12;
  the full description is in `measurement-2026-11-10.json`.
- Tesseract 5 with `deu.traineddata` from `tessdata_best` 4.1.0, SHA-256
  `8407331d…0d06e`, as pinned in `scripts/fetch-models.sh`.
- Code: branch `worker-1-m2-kinds`; kinds `policy`, `contract_change` and
  `premium_invoice` under `sidecar/substrakt/document_kinds/`.

## Input

`npm run corpus` writes 92 documents into `corpus/out/insurance/` together
with `truth.json`:

- three kinds, each in five layouts with four contracts: 20 text-layer PDFs
  per kind;
- two of the four contracts per layout also as a scan, one at 300 dpi and one
  at 150 dpi, with skew, sensor noise and uneven lighting: 10 scans per kind;
- two documents that are no kind: a claim report (fits no kind) and a page
  that carries a policy and a premium invoice (fits two kinds).

Layouts `a` to `c` are the **tuning set**; the label patterns were written
against them. Layouts `d` and `e` are **held out**: they use other label
words, amounts with the currency in front, policy numbers in digit groups,
two labels for one period, a sentence instead of a label, and a heading in
body size. No pattern in a kind file was changed after their result was
seen.

Three changes to the core were made after a first run showed wrong values
without a review flag, in both sets. They are rules of the label search, not
patterns: a free-text value needs a label that opens a row or a cell and must
not continue a sentence; a free-text or company value ends at the gap to the
next cell; a page with the headings of two kinds gets no kind. The held-out
figures are therefore untouched by pattern tuning, but not blind with respect
to these three rules.

## Procedure

`cd sidecar && uv run python ../bench/insurance_kinds.py --write 2026-11-10`

Every document runs through the production path: `DocumentStore.load`,
`document_kinds.recognise`, `extract` with the fields of the recognised kind.
Each value is compared with the truth in canonical form (ISO date, number,
canonical term, otherwise the printed text without regard to case).

| Outcome | Meaning |
|---|---|
| Correct | delivered without a review flag, and right |
| Right, in review | right, but flagged for review |
| Wrong, in review | wrong, and flagged for review |
| Missing | printed on the document, not found; the clerk is asked |
| Wrong without flag | delivered without a flag and wrong, or delivered although nothing is printed |

A value counts as flagged when `grounded` is false. A document whose kind is
not recognised delivers no value at all; it goes to review as a whole.

## Result

| Kind | Set | Source | Documents | Kind recognised | Kind to review | Kind wrong | Values printed | Correct | Right, in review | Wrong, in review | Missing | Wrong without flag | Share correct | Share right value |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| contract_change | held_out | text layer | 8 | 8 | 0 | 0 | 68 | 43 | 8 | 0 | 17 | 0 | 63.2% | 75.0% |
| contract_change | held_out | scan | 4 | 3 | 1 | 0 | 26 | 16 | 3 | 0 | 7 | 0 | 61.5% | 73.1% |
| contract_change | tuning | text layer | 12 | 12 | 0 | 0 | 112 | 100 | 8 | 0 | 4 | 0 | 89.3% | 96.4% |
| contract_change | tuning | scan | 6 | 6 | 0 | 0 | 56 | 50 | 4 | 0 | 2 | 0 | 89.3% | 96.4% |
| policy | held_out | text layer | 8 | 8 | 0 | 0 | 72 | 39 | 8 | 0 | 25 | 0 | 54.2% | 65.3% |
| policy | held_out | scan | 4 | 4 | 0 | 0 | 36 | 20 | 4 | 0 | 12 | 0 | 55.6% | 66.7% |
| policy | tuning | text layer | 12 | 12 | 0 | 0 | 104 | 92 | 8 | 0 | 4 | 0 | 88.5% | 96.2% |
| policy | tuning | scan | 6 | 6 | 0 | 0 | 52 | 44 | 5 | 0 | 3 | 0 | 84.6% | 94.2% |
| premium_invoice | held_out | text layer | 8 | 8 | 0 | 0 | 84 | 39 | 8 | 0 | 37 | 0 | 46.4% | 56.0% |
| premium_invoice | held_out | scan | 4 | 4 | 0 | 0 | 42 | 20 | 4 | 0 | 18 | 0 | 47.6% | 57.1% |
| premium_invoice | tuning | text layer | 12 | 12 | 0 | 0 | 136 | 120 | 8 | 0 | 8 | 0 | 88.2% | 94.1% |
| premium_invoice | tuning | scan | 6 | 6 | 0 | 0 | 68 | 62 | 4 | 0 | 2 | 0 | 91.2% | 97.1% |

“Share correct” is correct values over printed values; “share right value”
adds the right values that were sent to review.

- **No wrong value was delivered without a review flag**, and no document got
  a wrong kind: 0 of 856 printed values and 0 of 90 documents.
- The claim report and the page with two headings got no kind, as required.
- One held-out scan of a contract change (heading in body size, 150 dpi) got
  no kind and went to review.
- On the tuning layouts between 84.6% and 91.2% of the printed values are
  delivered correctly, and between 94.1% and 97.1% carry the right value.
- On the held-out layouts between 46.4% and 63.2% are delivered correctly.
  The rest is missing, not wrong: the clerk is asked for it.
- Scans read about as well as text-layer PDFs on this corpus. The scans are
  rasterised PDFs with synthetic defects, not paper from a scanner.

### Per value

| Kind | Value | Set | Correct | Right, in review | Wrong, in review | Missing | Wrong without flag |
|---|---|---|--:|--:|--:|--:|--:|
| contract_change | change_date | held_out | 5 | 0 | 0 | 6 | 0 |
| contract_change | change_date | tuning | 18 | 0 | 0 | 0 | 0 |
| contract_change | change_number | held_out | 6 | 0 | 0 | 0 | 0 |
| contract_change | change_number | tuning | 12 | 0 | 0 | 0 | 0 |
| contract_change | end_date | held_out | 5 | 0 | 0 | 0 | 0 |
| contract_change | end_date | tuning | 12 | 0 | 0 | 0 | 0 |
| contract_change | insurer | held_out | 0 | 11 | 0 | 0 | 0 |
| contract_change | insurer | tuning | 6 | 12 | 0 | 0 | 0 |
| contract_change | issue_date | held_out | 6 | 0 | 0 | 0 | 0 |
| contract_change | issue_date | tuning | 12 | 0 | 0 | 0 | 0 |
| contract_change | line_of_business | held_out | 11 | 0 | 0 | 0 | 0 |
| contract_change | line_of_business | tuning | 18 | 0 | 0 | 0 | 0 |
| contract_change | net_premium | tuning | 6 | 0 | 0 | 0 | 0 |
| contract_change | payment_mode | held_out | 10 | 0 | 0 | 1 | 0 |
| contract_change | payment_mode | tuning | 12 | 0 | 0 | 0 | 0 |
| contract_change | policy_number | held_out | 5 | 0 | 0 | 6 | 0 |
| contract_change | policy_number | tuning | 18 | 0 | 0 | 0 | 0 |
| contract_change | policyholder | held_out | 6 | 0 | 0 | 5 | 0 |
| contract_change | policyholder | tuning | 12 | 0 | 0 | 6 | 0 |
| contract_change | premium | held_out | 5 | 0 | 0 | 6 | 0 |
| contract_change | premium | tuning | 18 | 0 | 0 | 0 | 0 |
| contract_change | start_date | tuning | 6 | 0 | 0 | 0 | 0 |
| policy | annual_premium | tuning | 6 | 0 | 0 | 0 | 0 |
| policy | end_date | held_out | 6 | 0 | 0 | 6 | 0 |
| policy | end_date | tuning | 18 | 0 | 0 | 0 | 0 |
| policy | insurer | held_out | 0 | 12 | 0 | 0 | 0 |
| policy | insurer | tuning | 6 | 12 | 0 | 0 | 0 |
| policy | issue_date | held_out | 6 | 0 | 0 | 0 | 0 |
| policy | issue_date | tuning | 12 | 0 | 0 | 0 | 0 |
| policy | line_of_business | held_out | 12 | 0 | 0 | 0 | 0 |
| policy | line_of_business | tuning | 18 | 0 | 0 | 0 | 0 |
| policy | net_premium | held_out | 0 | 0 | 0 | 6 | 0 |
| policy | net_premium | tuning | 6 | 0 | 0 | 0 | 0 |
| policy | payment_mode | held_out | 12 | 0 | 0 | 0 | 0 |
| policy | payment_mode | tuning | 11 | 0 | 0 | 1 | 0 |
| policy | policy_number | held_out | 5 | 0 | 0 | 7 | 0 |
| policy | policy_number | tuning | 17 | 1 | 0 | 0 | 0 |
| policy | policyholder | held_out | 6 | 0 | 0 | 6 | 0 |
| policy | policyholder | tuning | 12 | 0 | 0 | 6 | 0 |
| policy | premium | held_out | 6 | 0 | 0 | 6 | 0 |
| policy | premium | tuning | 12 | 0 | 0 | 0 | 0 |
| policy | start_date | held_out | 6 | 0 | 0 | 6 | 0 |
| policy | start_date | tuning | 18 | 0 | 0 | 0 | 0 |
| premium_invoice | due_date | held_out | 6 | 0 | 0 | 6 | 0 |
| premium_invoice | due_date | tuning | 16 | 0 | 0 | 2 | 0 |
| premium_invoice | insurance_tax | held_out | 0 | 0 | 0 | 6 | 0 |
| premium_invoice | insurance_tax | tuning | 18 | 0 | 0 | 0 | 0 |
| premium_invoice | insurer | held_out | 0 | 12 | 0 | 0 | 0 |
| premium_invoice | insurer | tuning | 6 | 12 | 0 | 0 | 0 |
| premium_invoice | invoice_date | held_out | 6 | 0 | 0 | 6 | 0 |
| premium_invoice | invoice_date | tuning | 18 | 0 | 0 | 0 | 0 |
| premium_invoice | line_of_business | held_out | 12 | 0 | 0 | 0 | 0 |
| premium_invoice | line_of_business | tuning | 18 | 0 | 0 | 0 | 0 |
| premium_invoice | net_premium | held_out | 0 | 0 | 0 | 6 | 0 |
| premium_invoice | net_premium | tuning | 18 | 0 | 0 | 0 | 0 |
| premium_invoice | payment_mode | held_out | 6 | 0 | 0 | 0 | 0 |
| premium_invoice | payment_mode | tuning | 6 | 0 | 0 | 0 | 0 |
| premium_invoice | period_end | held_out | 6 | 0 | 0 | 6 | 0 |
| premium_invoice | period_end | tuning | 16 | 0 | 0 | 2 | 0 |
| premium_invoice | period_start | held_out | 6 | 0 | 0 | 6 | 0 |
| premium_invoice | period_start | tuning | 18 | 0 | 0 | 0 | 0 |
| premium_invoice | policy_number | held_out | 5 | 0 | 0 | 7 | 0 |
| premium_invoice | policy_number | tuning | 18 | 0 | 0 | 0 | 0 |
| premium_invoice | policyholder | held_out | 6 | 0 | 0 | 6 | 0 |
| premium_invoice | policyholder | tuning | 12 | 0 | 0 | 6 | 0 |
| premium_invoice | premium | held_out | 6 | 0 | 0 | 6 | 0 |
| premium_invoice | premium | tuning | 18 | 0 | 0 | 0 | 0 |

## What the figures show

1. **The insurer is always sent to review unless it is labelled.** It is
   taken from the letterhead, and the core marks a letterhead value as a
   guess. Twelve of eighteen tuning documents per kind carry no label
   “Versicherer”. On real documents this would ask the clerk for the insurer
   on most documents.
2. **The policyholder is read only behind a label.** Where it stands only in
   the address block, it is missing. The address block is not parsed.
3. **Held-out layouts lose values to wording the patterns do not know**:
   “Vertragsdauer” for start and end, “Beitrag je Zahlungsabschnitt”,
   “Rechnung vom”, a period under two labels, an amount written as
   “EUR 186,40”. These are pattern gaps and would be closed per insurer.
4. **A policy number printed in digit groups is not read.** Reading only the
   first group would deliver a truncated number, so the core now delivers
   none. Whether the groups belong together is a rule per insurer.
5. **The annual premium and the premium per payment period are two values.**
   A first version read both as `premium`. Since the hand-over was built
   they are separate: “Jahresbeitrag” is read as `annual_premium`, because a
   GDV record asks for the amount per payment period and the two differ by
   more than a division (`docs/gdv-hand-over.md`, section “Premium”).
   The totals above did not change; in the table per value six tuning
   policies moved from `premium` to `annual_premium`. A label that does not
   say which, such as “Gesamtbeitrag”, stays `premium`.

## Limits

- Synthetic layouts, five per kind, by one author who also wrote the rules.
- One page per document; multi-page policies and several documents in one
  scan are not covered.
- OCR errors on real paper, stamps, handwriting and fax quality are not
  covered.
- The raw result with every value is in `insurance-kinds-2026-11-10.json`.
