# Document types

Everything Substrakt knows about a kind of document lives in one YAML file,
not in code: which values it has, how they are labelled, which titles mark it
as an invoice or a credit note, which legal forms reveal a company name. The
core (parser, word index, label search, normalisation, grounding) reads this
description and is the same for every type. **A new document type is a new
file.**

Substrakt ships four kinds under
[`sidecar/substrakt/document_kinds/`](../sidecar/substrakt/document_kinds/):

| File | Kind |
|---|---|
| `invoice.yml` | invoices and credit notes, labelled in German or English |
| `policy.yml` | insurance policies (Versicherungsscheine) |
| `contract_change.yml` | contract changes (Nachträge) to a policy |
| `premium_invoice.yml` | premium invoices (Beitragsrechnungen) of an insurer |

The three insurance kinds belong to the broker pilot. They share the value
names `insurer`, `policy_number`, `policyholder`, `line_of_business`,
`payment_mode`, `premium` and `net_premium`, so a profile can name a value
once for all of them. `premium` is the amount per payment period including
tax; a policy and a contract change read the amount for a year as
`annual_premium`, because a hand-over must not take one for the other.

## Where files are loaded from

| Location | Purpose |
|---|---|
| `sidecar/substrakt/document_kinds/*.yml` | shipped with the application |
| `<data dir>/document_kinds/*.yml` | your own kinds, see [Configuration](configuration.md#directories) |

A file of your own with the same name **replaces** the shipped one
completely; nothing is merged, so every type has exactly one version.
When a clerk renames, removes or adds a value in „Vorlagen“, the application
writes such a file itself; deleting it goes back to the shipped kind.

Files are read with `yaml.safe_load` and validated with Pydantic when loaded.
Unknown keys, invalid regular expressions and a `name` that differs from the
file name are rejected. The sidecar then answers with the error key
`document-kind-invalid`, the file name and the location of the error, never with
document text.

## Structure

```yaml
# yaml-language-server: $schema=document_kind.schema.json
name: invoice                  # equals the file name, [a-z][a-z0-9_]*
title: Rechnung                # name shown in the interface
description: Eingangs- und Ausgangsrechnungen sowie Gutschriften.

recognition:
  titles:                      # canonical value → printed titles
    Rechnung: [Rechnung, Invoice]
    Gutschrift: [Gutschrift, Credit note]
  title_patterns: ['Rechnung', 'Invoice']   # the heading that names the kind
  minimum: 4                   # score a document must reach

legal_forms: ['GmbH(?:\s*&\s*Co\.?\s*KG)?', 'AG', 'Ltd\.?']
boundaries: ['Lieferdatum', 'Due\s+date']

fields:
  - name: document_date        # becomes the JSON key
    label: Belegdatum          # shown to the user
    question: Wann wurde das Dokument ausgestellt?
    json_type: date
    label_rule:
      patterns: ['Belegdatum', 'Rechnungsdatum', 'Invoice\s+date']
      value: date
```

`document_kind.schema.json` next to the shipped file is generated from the model
and gives editors completion and validation. After a change to the model,
regenerate it with `document_kinds.write_schema()`;
`tests/sidecar/test_document_kinds.py` rejects an outdated schema.

### Recognising the kind (`recognition`)

`document_kinds.recognise(doc)` returns the one kind a document clearly is,
or nothing. Nothing means review; the application never guesses a kind.

A kind scores 3 when the first page carries its heading and 1 for every field
whose label stands on that page. A heading is a line that matches one of
`title_patterns` and is printed larger than the body text or stands alone on
its line. When one heading matches two kinds, the kind named first in it
wins: a change “to the policy” is a contract change.

A document gets the best kind only if that kind reaches its `minimum` and
leads the second-best by 2. A page with the headings of two kinds gets none.
The weights and the lead are constants in
`sidecar/substrakt/document_kinds/__init__.py`; headings, labels and the
minimum are data in the kind file.

`POST /documents/{id}/extract` uses the recognised kind and names it in
`kind`. A request without `fields` reads the fields of that kind.

### Fields (`fields`)

| Key | Meaning |
|---|---|
| `name` | JSON key of the value; a valid identifier |
| `label` | name in the interface |
| `question` | the question the value answers |
| `json_type` | `string`, `number`, `integer`, `date` or `boolean` |
| `required` | value is required |
| `extractor` | a built-in extractor such as `iban`, `bic`, `vat_id`, `date` |
| `normalization` | a built-in normaliser; by default chosen from `json_type` |
| `label_rule` | how the value is found next to its printed label (below) |

### Label rules (`label_rule`)

| Key | Meaning |
|---|---|
| `patterns` | labels as regular expressions, case-insensitive; a trailing colon is always allowed |
| `value` | `identifier`, `date`, `amount`, `code`, `vat_id`, `company`, `title`, `text` or `term` |
| `values` | allowed codes for `value: code`, e.g. `[EUR, USD, CHF, GBP]` |
| `terms` | for `value: term`: canonical value → printed spellings, e.g. `halbjährlich: [halbjährliche, 1/2]`; the result carries the printed text and the canonical value |
| `position` | for `date` and `amount`: which value after the label counts; `2` reads the end of “01.01.2026 bis 31.12.2026” |
| `unlabelled` | a code or term may also be found without a label, if the document names only one |
| `skip_tax_rate` | skip a percentage printed before the amount |
| `letterhead_until` | look for an unlabelled company name above these labels |

`value: text` reads free text such as a name. Free text has no shape that
could be checked, so the rule is strict: the label must open a row or a cell
or end in a colon, the value must start with a capital letter or a digit, and
it ends at the gap to the next cell. A label inside a sentence yields
nothing.

An `identifier` printed in digit groups (“47 110 815”) yields no value,
because only its first group could be read.

## Custom parsers

When the core is not enough, a type may name at most one parser:
`parser: <name>` refers to a module shipped under
`sidecar/substrakt/document_kinds/parser/` with a function
`read(doc, field, kind)` that returns an assignment or `None`; `None`
hands the field back to the core.

A file in the user directory can **choose** a shipped parser but cannot bring
its own code. That keeps every type file reviewable as data.

## Values that identify a document

`same_document` lists the values that identify one document of the kind, for
a policy its number and its date of issue. Two files with different content
whose values all agree are a possible duplicate: the same paper scanned
twice. The second one is read as usual and marked; a person decides whether
it is the same document. Nothing is compared when one of the values is
missing or was not read unambiguously, and a kind that leaves the key out is
never compared by values. Text is compared by its letters and digits without
case, dates and amounts in their normalised form.

## What does not belong in a type file

A document type names neither a model nor a quantisation method. Both belong
in the model registry planned for stage 3, and the schema rejects them like
any other unknown key.

## Measuring a change to an insurance kind

`npm run corpus` writes synthetic policies, contract changes and premium
invoices with ground truth into `corpus/out/insurance/`. Then

```bash
cd sidecar && uv run python ../bench/insurance_kinds.py
```

prints, per kind, how many values are delivered correctly, sent to review or
missing, and fails if a wrong value is delivered without a review flag.
Layouts `d` and `e` are held out: do not adjust a pattern to them, or the
second figure stops meaning anything. The protocol of 10 November 2026 is
[`measurements/insurance-kinds-2026-11-10.md`](measurements/insurance-kinds-2026-11-10.md).

## Measuring a change

Label patterns came from the 84-document evaluation run of 14 October 2026.
After changing them, run the 84-document evaluation again as described in
[`corpus/evaluation/README.md`](../corpus/evaluation/README.md) and compare
with the previous result. The corpus is no blind test any more: the patterns
were tuned on it.
