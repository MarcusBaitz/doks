# GDV hand-over

Status: 19 November 2026

This file says which approved value goes into which record and field of the
GDV file, which fields carry a constant or stay empty and why, and what
nobody knows until a file has been imported into a test database of the
target program. The code is `sidecar/substrakt/gdv/`; the job queue reaches
it through `sidecar/substrakt/hand_over.py`, see “From approval to file”.

## Sources

Everything below was read on 10 November 2026 from the GDV's free
publication of the data set “VU-Vermittler”, release 01.12.2023, at
<https://www.gdv-online.de/vuvm/>. No position or code was taken from any
other source.

| Short name | Document |
|---|---|
| T0001 | record table “Vorsatz”, record 0001, version 2.5: `bestand/rel2023/ds0001.htm` |
| T0100 | record table “Adressteil”, record 0100, version 2.3: `bestand/rel2023/ds0100.htm` |
| T0200 | record table “Allgemeiner Vertragsteil”, record 0200, version 2.5: `bestand/rel2023/ds0200.htm` |
| T0400 | record table “Inkasso”, record 0400, version 1.7: `bestand/rel2023/ds0400.htm` |
| T9999 | record table “Nachsatz”, record 9999, version 1.1: `bestand/rel2023/ds9999.htm` |
| A1, A2, A7, A14, A24, A60 | annexes 1 (lines of business), 2 (sequence number), 7 (partner role), 14 (payment mode), 24 (contract status), 60 (kind of debit): `bestand/rel2023/anl<n>.htm` |
| B | brochure “Der GDV-Datensatz VU-Vermittler”, 4th edition: `bestand/Broschuere_gdv-datensatz_vu-vermittler.pdf`, cited by section and page |
| FAQ | `bestand/faq.html` |
| S | sample file of the GDV, `musterdatei_bestand/musterdatei_041222.txt` (release 2001; used only for conventions the tables leave open) |

## What a file is

One file per customer and hand-over, named
`<customer>_<date>-<time>.gdv`. It holds one package per insurer: header 0001
in three partial records, the records of that insurer's contracts, trailer
9999 (B 3.1.2, p. 15: a header and a trailer for every change of insurer
number or broker number). Per contract:

| Record | Partial records | Written for |
|---|---|---|
| 0100 | 1 | every contract |
| 0200 | 1 and 2 | every contract |
| 0400 | 1 | every approved premium invoice |

Partial records 2 to 5 of 0100 and 2 of 0400 would hold only initial values
and are left out, which B 3.1.3 (p. 16) allows. No line-specific record
(0210, 0220) is written, and a contract change is not handed over: its job
waits with the item `kind_not_handed_over`.

Every partial record is 256 bytes (B 3.1.3). Records are ordered by policy
number, sequence number, line of business, record type and partial record
(B 3.1.7, p. 20). The first invoice of a contract shares sequence number 01
with the contract, every further invoice for the same policy number counts on
(A2; B 3.1.7; FAQ on the sequence number).

Formats (B 3.1.5, table 2, p. 18): a numeric field is right-aligned with
leading zeros and is zeros when not delivered; an alphanumeric field is
left-aligned and spaces when not delivered; a date is DDMMYYYY; an amount has
two decimals and no separator, its sign stands in a field of its own.

## Approved values

The value names are those of the document kinds; a job carries them under the
names the pipeline profile gives them.

| Approved value | Kind | Record · partial record · field (byte address, length) | How |
|---|---|---|---|
| `insurer` | both | key field 2 of 0100, 0200, 0400 (5, 5); header 0001 field 2 | the insurer number from `tables/insurers.yml`, never the name |
| `line_of_business` | both | key field 4 (11, 3) | the code from `tables/lines_of_business.yml` (A1) |
| `policy_number` | both | key field 5 (14, 17), right-aligned; 0200 · 2 · field 13 (84, 30) | as approved, see “Policy number” |
| `policyholder` | both | 0100 · 1 · fields 9 to 11, name 1 to 3 (44, 74, 104; 30 each) | as approved, continued in the next field at a word boundary |
| `start_date` | policy | 0200 · 1 · field 9 (44, 8) | |
| `end_date` | policy | 0200 · 1 · field 10 (52, 8) | |
| `payment_mode` | policy | 0200 · 1 · field 12 (68, 1) | the code from `tables/payment_modes.yml` (A14) |
| `issue_date` | policy | 0200 · 2 · field 17, “Policierungsdatum” (147, 8) | if the profile hands it over |
| `premium` | policy | 0200 · 2 · field 12 (72, 12) | see “Premium” |
| `net_premium` | policy | 0200 · 1 · field 22 (116, 12) | only as the amount per payment period, see “Premium” |
| `annual_premium` | policy | 0200 · 2 · field 12 (72, 12) | only with annual or one-off payment, see “Premium” |
| `premium` | premium invoice | 0400 · 1 · field 26 (139, 11) with sign “+” in field 27 | the amount of the invoice including tax |
| `net_premium` | premium invoice | 0400 · 1 · field 20 (110, 11) with sign “+” | if the profile hands it over |
| `insurance_tax` | premium invoice | 0400 · 1 · field 22 (122, 11) with sign “+” | if the profile hands it over |
| `period_start` | premium invoice | 0400 · 1 · field 11, “Abrechnungszeitraum von” (54, 8) | |
| `due_date` | premium invoice | 0400 · 1 · field 11 (54, 8) | only where no `period_start` is approved, see “Dates of an invoice” |
| `period_end` | premium invoice | 0400 · 1 · field 12, “Abrechnungszeitraum bis” (62, 8) | |
| `invoice_date` | premium invoice | 0400 · 1 · field 14, “Erstellungsdatum” (71, 8) | “Datum der Erstellung der Sollstellung” |
| `payment_mode` | premium invoice | 0400 · 1 · field 13 (70, 1) | if the profile hands it over |

A contract that has only an invoice still gets 0100 and 0200; its 0200 then
carries the key, the currency and the policy number and no dates or premium.

A profile may list fewer values than this table: a value reaches the
file only if the profile names it for the kind.

### Dates of an invoice

T0400 defines field 11 as “Beginn des Abrechnungszeitraumes einer
Sollstellung (Fälligkeit)”: the table treats the start of the billing period
and the due date as the same day, and 0400 has no other field for a due date
(field 10 is the booking date, field 14 the date the debit was created,
field 15 the date a contract state takes effect). So field 11 gets
`period_start`; where an invoice has no approved period, it gets `due_date`.
Where both are approved and differ, as with an invoice payable two weeks
after the period begins, the payment date is not in the file: the
specification has no field for it.

## Not on the paper

| Item | Goes into | Comes from |
|---|---|---|
| Insurer number (VU-Nummer) | key field 2, header field 2 | `sidecar/substrakt/gdv/tables/insurers.yml`, replaceable by `<data dir>/gdv/insurers.yml` |
| Line of business code | key field 4 | `tables/lines_of_business.yml`, annex 1 |
| Payment mode code | 0200 field 12, 0400 field 13 | `tables/payment_modes.yml`, annex 14 |
| Broker number | key field 7 (33, 10), header field 6, trailer field 3 | profile, `hand_over.broker_number` |
| Sender, addressee | header fields 3 and 4 | profile, `hand_over.sender`, `hand_over.addressee` |
| Currency | 0200 · 1 · field 21, 0400 · 1 · field 19 | profile, `hand_over.currency` |
| Encoding, record separator | the whole file | profile, `hand_over.encoding`, `hand_over.record_separator` |

A table is one YAML file with `name`, `source` and `entries`; an unknown key,
a code that is no text or a code of the wrong length is rejected
(`hand-over-table-invalid`). The shipped insurer table holds the four
invented insurers of the synthetic corpus with invented numbers. Real numbers
are those of the BaFin register, which the GDV publishes at
<https://www.gdv-online.de/vuvm/vunummern.htm>; which spelling of an insurer
on a document maps to which number is the broker's data and has to be filled
in with the broker.

A missing entry is never guessed. The contract is not written, and the result
names the item: `insurer_number`, `line_of_business_code` or
`payment_mode_code` with the approved value that has no entry. Other items
are `insurer`, `policy_number`, `policyholder` and `line_of_business` (the
approved value itself is missing), `value_fits_field` (a value is longer than
its field or has a character the encoding lacks; nothing is cut or replaced),
`premium_per_payment_period`, `one_contract_per_policy_number` (two approved
policies with the same number), `same_policyholder` (policy and invoice of
one contract name different policyholders) and `kind_not_handed_over`.

### The block `hand_over` of a profile

```yaml
hand_over:
  format: gdv                  # chooses the writer
  encoding: cp850              # any codec with one byte per character
  record_separator: crlf       # crlf or none
  broker_number: "4711"        # up to 10 letters and digits
  sender: Maklerbüro Beispiel  # up to 30 characters
  addressee: Bestandsprogramm  # up to 30 characters
  currency: EUR
  contract_kinds: [policy]
  collection_kinds: [premium_invoice]
  # Codes of facts that stand on no paper; each may be left out:
  sender_kind: "2"             # header field 54: 1 insurer, 2 broker, 3 insurer without GDV key, 9 other
  addressee_kind: "2"          # header field 55, same codes
  contract_status: "1"         # 0200 field 13, annex 24: 1 in force
  collection_kind: "2"         # field 8 of 0200 and 0400: 1 by the broker, 2 by the insurer
  debit_kind: "30"             # 0400 field 9, annex 60: 10 first premium, 30 renewal
```

The five codes at the end are facts of this hand-over that no document
prints. The code never chooses one: a code the profile names is written and
checked against its annex, one it does not name leaves the field empty.
Whoever writes the profile decides, and the decision is visible there. The
values above are examples, not proposals for any target program.

No other key has a default, and the shipped profile does not have the block yet:
its values are facts of the broker and the vendor (see the questions below).
A hand-over with a profile that lacks the block fails with
`pipeline-profile-invalid` and names every missing key.

## From approval to file

A profile whose block `hand_over` names `format: gdv` is handed over in runs
(`sidecar/substrakt/hand_over.py`):

1. **Approval asks the writer first.** If the document could not be written
   (an insurer without a number, a line of business or payment mode without a
   code, a value that fits no field, a contract change), the approval is
   refused with `approval-refused`, reason `hand-over-not-possible`, and the
   item names. No job exists, and the entry waits in review. The message
   carries names of items, never the values.
2. **Approving writes nothing.** The job stays pending. A person starts a run
   for one customer (`POST /jobs/hand-over`); the screen that shows the
   content first does not exist yet.
3. **A run writes one file** per customer and profile, and beside it the job
   file of every job in it. These jobs become handed over. A later run for
   the same customer writes a further file; no file is ever replaced.
4. **What the writer holds back in a run fails.** A job has four states and
   none of them means “back to review”, so a job the writer cannot place
   (two approved policies with one number, policy and invoice naming
   different policyholders) fails with the reason
   `hand-over-held-back: <items>`. A mismatch on read-back fails every job of
   the file with `hand-over-read-back-failed: …` and leaves no file. Missing
   or invalid settings fail with `hand-over-settings-invalid: <keys>`.
5. **Nothing is written again by itself.** A failed job stays failed until a
   person releases it; it is then pending for the next run.

A profile without the block keeps the behaviour of the job queue: the job
fails at once with `target-without-writer`. The shipped profile is in that
state until the broker and the vendor have answered what the block needs.

## Premium

The specification asks for the amount **per payment period**:

- 0200 · 1 · field 22: total premium net, “ohne Gebühren und Vers.-Steuer
  gem. Zahlungsweise” (T0200).
- 0200 · 2 · field 12: total premium gross, “inkl. Vers.-Steuer gem.
  Zahlungsweise” (T0200).
- B 3.1.7 (p. 20): “Beiträge gemäß Zahlungsweise beinhalten bei
  unterjähriger Zahlung grundsätzlich die entsprechenden Zuschläge.” An
  annual figure divided by the number of instalments is therefore not the
  amount per period, and the specification defines no conversion.

What follows from it:

1. The document kinds read two values. `premium` is the amount per payment
   period including tax; `annual_premium` is the amount for a year and has
   its own labels (“Jahresbeitrag”). A label that does not say which stays
   `premium`, and the clerk approves it as such.
2. 0200 field 12 gets `premium`. Where only `annual_premium` is approved, it
   is written if the payment mode is annual or one-off (A14: codes 1 and 6),
   because a year or the whole contract is then one payment period.
3. Where only `annual_premium` is approved and the payment mode is another
   one or unknown, nothing is computed. The contract waits with the item
   `premium_per_payment_period`.
4. 0200 field 22 gets `net_premium` when it is the net amount per payment
   period, and the trailer's first sum adds it up. With annual or one-off
   payment it is. With instalments the kinds cannot say whether a printed
   net amount is for the year or the period, but the amounts can: a net
   amount for a year is at least twice the net amount per period and so
   above the gross amount per period, while the net amount per period is
   below it. A net amount not above the approved `premium` is written. One
   above it, or one without a `premium` to compare with, is the amount of
   another period: it is not converted and not written, because the record
   has no field for it, just as it has none for the annual premium of a
   contract paid in instalments. It does not hold the contract back; the net
   premium is an optional value of the profile. The limit of the rule: it
   assumes at least two instalments a year and a tax below 100 percent.
5. An invoice goes into 0400 as it stands: field 26 is the “Abrechnungsbeitrag
   einschl. Steuer und Gebühren” (T0400), which is what an invoice totals.

The shipped profile does not list `annual_premium`. Every value a profile
lists is required for approval, and most policies print only one of the two
amounts; listing both would make them impossible to approve. A policy that
prints only the annual amount therefore waits until the clerk has entered the
premium per payment period, which is the question the document left open. The
writer's rule for `annual_premium` takes effect once a profile can name a
value as optional.

## Policy number

Key field 5 is 17 characters, right-aligned, and the record tables allow only
digits and letters: “ohne Sonderzeichen. Zu den … nicht zulässigen
Sonderzeichen zählen auch "Leerzeichen". Zulässig sind Ziffern und Buchstaben
(ohne Umlaute und ß)” (T0100, T0200, T0400, field 5). Insurers print the
number with separators, and the field for the printed form is 0200 · 2 ·
field 13: “wie auf dem Dokument angegeben, inklusive aller Alpha und
Sonderzeichen”.

The rule is therefore the specification's, not the application's:

- The key field gets the approved number without every character that is not
  a digit or a letter: `KF-88/2026-15` becomes `KF88202615`.
- The printed field gets the number as approved.
- The 17 characters apply to the key form. A number whose key form is longer,
  is empty, or holds a letter outside A to Z is not written
  (`value_fits_field`, field `policy_number`).
- Two approved numbers with the same key form, insurer and line of business
  are one contract.

The first independent review of a written file found the earlier behaviour,
the approved number in both fields, as its one contradiction to the
specification (finding E1 below).

Leading zeros and upper or lower case are kept as approved. Whether the
target program matches on the key field as written, on a form without
leading zeros, or on the printed field stays a question to the vendor.

## Constants and empty fields

| Field | Content | Why |
|---|---|---|
| 0001 · fields 7, 8, 9, 46, 50 (versions of 0001, 0100, 0200, 0400, 9999) | `2.5`, `2.3`, `2.5`, `1.7`, `1.1` | T0001: the version of every record type the package can contain; the one of 0400 only in a package that holds a 0400; all other version fields stay empty |
| 0001 · field 5 (creation date, period from and to) | the day of the hand-over, twice | T0001 |
| 0001 · 1 · field 56 (billing office) | `00` | T0001: “Sollte keine Abrechnungstelle vorhanden sein, muss "00" geschlüsselt werden” |
| 0001 · fields 54, 55 (kind of sender and addressee) | `hand_over.sender_kind`, `hand_over.addressee_kind`, else empty | a fact of the hand-over, decided in the profile |
| key field 3 (bundle flag) | empty | no contract is bundled |
| key field 6 (sequence number) | `01`, counted on per further invoice | A2, B 3.1.7 |
| 0100 · 1 · field 20 (partner role) | `01` | A7: 01 is the policyholder, which is what the approved value names |
| 0100 · 1 · salutation, title, address, date of birth, sex | empty or zeros | not values the kinds read; the address block of a document is not read |
| 0200 · 1 · field 8 and 0400 · 1 · field 8 (collection kind) | `hand_over.collection_kind`, else empty | not on the paper; a fact of the broker's agreement with the insurers |
| 0200 · 1 · field 13 (contract status, A24) | `hand_over.contract_status`, else empty | not on the paper; that a contract entered from a current policy is in force is a decision of whoever writes the profile |
| 0400 · 1 · field 9 (kind of debit, A60) | `hand_over.debit_kind`, else empty | first premium (10) or renewal (30) is not on the paper; one code for all invoices of a profile is a simplification the profile's author accepts or leaves out |
| 0200 · 1 · field 11 (main due date) | zeros | FAQ “Wie ist das Feld Hauptfälligkeit zu verstehen?”: the day the contract next renews unless cancelled. Neither start date nor payment mode define it (a contract over three years renews on a day no approved value names), so it is not derived |
| 0200 · 1 · field 26, customer number of the broker | empty | the application knows no customer number of the target program; matching against its master data is not built |
| 0400 · 1 · sign fields of amounts | `+` | B 3.1.5: amounts are signed from the insurer's view, a charge is positive; S writes `+` also beside a sum of zero |
| 9999 · field 2 (count) | partial records between header and trailer | T9999 says “ohne Vor-/Nachsatz”; S counts partial records (162 of 162) |
| 9999 · field 4 | sum of 0200 field 22 | T9999 |
| 9999 · field 5 with sign | sum of 0400 field 26 | T9999 |
| 9999 · fields 7, 9, 11 with signs | zero, `+` | no commission and no claims are written |

## Read-back

Every file is written under a temporary name, read back by
`sidecar/substrakt/gdv/reader.py` and gets its name only if every value read
equals the approved value, the count and sums of each trailer equal the
records, and the file holds no record without an approved job. Otherwise the
file is removed and every job in it is reported as failed.

The reader imports nothing from the package: it has its own positions, its
own conversion of dates and amounts and its own sums, and a test rejects an
import. The tests hold a third table of positions, written as the byte
addresses the record tables print.

**The limit of this check.** `gdv.xport` (Java, Apache-2.0) was meant as an
independent validator for development; the development machine has no JVM,
so it was not used. Writer, reader and test table are three transcriptions of
the same tables by the same hand. They catch a slip in one of them. They do
not catch a misreading of the specification that all three share, and they
say nothing about what the target program accepts.

## Independent review

On 10 November 2026 a reviewer who saw only a written file, its input values
and the specification, not the code or this document, compared the file with
the record tables; the review and its inputs are kept outside this
repository. Positions, lengths, order, sums
and encoding agreed (30 points); one contradiction to the specification (the
policy number in the key field) and fifteen risks were found. What became of
each:

| Finding | Result |
|---|---|
| E1 special characters in the key field | fixed, see “Policy number” |
| R1 contract status, R6 collection kind and kind of debit, R7 collection kind, R10 kind of sender and addressee | settings of the profile, see “The block `hand_over`” |
| R2 net premium zero | fixed, see “Premium”, point 4 |
| R6 invoice date and end of period, R7 issue date not written | fixed, see “Approved values” |
| R14 due date and period start in one field | decided from T0400, see “Dates of an invoice” |
| R13 header announces 0400 in a package without one | fixed |
| R7 main due date | open with reason, see “Constants and empty fields” |
| R4 address record without address and with the whole name in name 1 | open: the document kinds do not read the address block, see below |
| R5 same person under two insurers with nothing to merge on | open: follows from R4; first vendor question |
| R3 no line-specific records | out of scope by decision; question to the vendor and step of a test import |
| R8 encoding, R9 separator | stay required settings without a default; the GDV sample file uses ISO 8859-1 and CR LF |
| R11 blank in a coded field | the specification does not decide it; the settings above close it where a profile names the code |
| R12 invented insurer numbers | by design of the shipped table; real numbers come with the broker's data |
| R15 annual premium of a contract paid in instalments | no field in the record; not a defect, as the review says |

**Address and name (R4).** The kinds read the policyholder behind a label as
one text. Street, postcode, town, first name and surname stand in the address
block of a letter, which has no labels; the label search of the core cannot
read it, and splitting a name at a space would be a guess. Reading the block
needs a rule of its own in the core (the lines between the letterhead and the
date, by position), values `street`, `postcode`, `city` in the three kind
files, a corpus with other address layouts and a new evaluation. That is a
piece of work of the size of a kind, not an addition to the kind files, and
was not done here.

A fresh file for the next review comes from
`cd sidecar && uv run python ../bench/gdv_sample.py <folder>`, which writes
the file and its inputs outside the repository.

## Open until a test import

Questions to the vendor of the target program and to the broker; none of them
can be answered from the specification:

1. **Encoding.** The standard fixes none; B (p. 43) lists it as a point the
   two parties agree on. Code page 850, ISO 8859-1 and ISO 8859-15 are in
   use.
2. **Record separator.** The tables speak of 256 bytes per partial record
   and of no separator; the GDV's sample file has CR LF after each.
3. **Broker number, sender and addressee** the import expects, and whether
   it checks them.
4. **Policy number**: whether the import matches on the key field as the
   specification defines it (digits and letters only), on a form without
   leading zeros, or on the printed field.
5. **Due date of an invoice.** Field 11 of 0400 gets the start of the
   period, or the due date where no period is approved. Whether the import
   shows field 11 as the due date the clerk types today has to be seen.
6. **Code fields**: which contract status, collection kind, kind of debit
   and kinds of sender and addressee the import expects, or whether it
   accepts them empty. They are settings of the profile.
7. **Name of the policyholder**: T0100 wants the first name of a natural
   person in name 3 and the surname in name 1. The approved value is one
   text and is written from name 1 on; splitting it would be a guess.
8. **Header as written by a broker**: the data set describes deliveries from
   an insurer to a broker. Whether the import minds a file whose sender is
   the broker is not known.
9. **A contract change**: which records the import needs to change an
   existing contract instead of creating a second one.
10. **Three header records**: release 2023 has three partial records for
    0001; an import written for an older release may expect two.
