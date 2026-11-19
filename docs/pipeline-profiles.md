# Writing a pipeline profile

Status: 2026-11-19

A pipeline profile is one YAML file that says what a watched folder means and
where its approved values go: which folder names the customer, which kinds of
documents are read, which values a clerk must have settled before an
approval, under which names the target application knows them, and the
target. Another broker, another folder structure or another target
application is a new file, not a change to the code;
`tests/sidecar/test_second_profile.py` holds that with a profile for an
invented target.

This guide derives the shipped profile,
[`insurance_folder.yml`](../sidecar/substrakt/pipeline_profiles/insurance_folder.yml),
step by step. The same test reads the result of the last step from this page
and compares it with the shipped file, so the two cannot drift apart.

## Where a profile lives and how it becomes active

| Place | Purpose |
|---|---|
| `sidecar/substrakt/pipeline_profiles/<name>.yml` | shipped with the application |
| `<data dir>/pipeline_profiles/<name>.yml` | your own profile; a file of the same name replaces the shipped one completely, nothing is merged |

`<data dir>` is the data directory of the application, the variable
`SUBSTRAKT_DATA_DIR`. A file is read again whenever it changed; no restart
is needed.

While exactly one profile exists, it is active. As soon as a second file
exists, none is active until one is chosen: no profile name is a default in
code. The choice is the setting `profile` of `POST /inbox/settings`
(`chooseInboxSettings` in `src/api/client.ts`), offered in Settings. A
document keeps the profile it was read under, so a new choice applies to
documents that arrive afterwards.

A file that breaks the schema, names a kind without a kind file, or lists a
value its kind does not read ends as `pipeline-profile-invalid` with file
name and position when the profile is loaded, not when a document arrives.
An editor that reads `pipeline_profile.schema.json` shows most of it while
typing.

## The keys

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | Lower-case letters, digits and `_`, starting with a letter; must equal the file name without `.yml`. Stored on every entry and written into the job file as `profile`. |
| `title` | yes | Name of the profile in the interface. |
| `target` | yes | Name of the target the values are handed over to, written into the job file as `target`. It is a free name: nothing in the code knows a target application. |
| `customer_folder_level` | yes | The folder level below the watched folder that names the customer: `1` is the first subfolder, `2` the one below it. `null` means no folder names a customer. A file that lies above that level has no customer. |
| `kinds` | yes, at least one | The kinds of documents this pipeline reads, each the name of a kind file (see [Document types](document-types.md)). Only these kinds are recognised in the folder. |
| `kinds.<kind>.values` | yes, at least one | Values an approval requires, as `name in the kind file: name in the target`. An approval is refused while one of them is open or was not read unambiguously. |
| `kinds.<kind>.optional` | no | Values in the same form that go along when they were read unambiguously and never block an approval. A value stands in `values` or in `optional`, not in both. |
| `overview_columns` | no | Values shown as columns in the list of an import on the overview, in order, as `name in the kind file: heading of the column`. A kind of the profile must read each of them; a document whose kind does not read one leaves its cell empty. Without the key the list shows file, kind and state only. |
| `hand_over` | no | Settings of a hand-over format, see below. Without the block the profile has no writer. |

No other key is accepted; a typing error is reported and not ignored.

The name on the right of a value is the key under which it appears in the
job file ([`job-format.md`](job-format.md)). A writer of a format finds the
values under the names on the left, so the right-hand side is free and is
best the word the clerk knows from the target application.

## Step by step, with the shipped profile as the example

The example is an insurance broker who scans policies, contract changes and
premium invoices and enters them in a broker management program. The core
names no such program, so the shipped profile stands for one.

### 1. Name the pipeline and its target

The file is `insurance_folder.yml`, so `name` is `insurance_folder`. The
title is the word the clerk knows the receiving program by; the example says
„Beispielziel“. The target is one word for the receiving application, and
`example_target` has no writer.

```yaml
name: insurance_folder
title: Beispielziel
target: example_target
```

### 2. Find the customer in the folder structure

The scanner of the broker files every document as
`<watched folder>/<customer>/<document>`. The customer is the first
subfolder:

```yaml
customer_folder_level: 1
```

A broker who files by year first, `<watched folder>/<year>/<customer>/…`,
writes `2`. One who puts every document into a single folder writes `null`;
the customer is then empty on every entry, and a hand-over run per customer
has nothing to go by.

### 3. List the kinds of documents

One entry under `kinds` per kind of document the folder may hold. The name
is that of a kind file: `policy`, `contract_change` and `premium_invoice` are
shipped for insurance documents, and `invoice` for ordinary invoices. A kind that does
not exist yet is written first, as [Document types](document-types.md)
describes. A document of a kind the profile does not list is not recognised
and waits for a person to name its kind.

### 4. Per kind, name the required and the optional values

Open the kind file and read the names under `fields`. For every value the
target needs, decide:

- **Required** (`values`): the target cannot take the document without it,
  and every document of this kind prints it. A clerk has to settle it before
  the approval.
- **Optional** (`optional`): useful where it was read, but not on every
  document. It never holds an approval up.
- **Left out**: the target has no use for it. It is still read and shown, and
  is not handed over.

For a policy the broker enters insurer, policy number, policyholder, line of
business, start, end and payment mode for every contract; these are required.
A policy prints either the premium per payment period or the annual premium,
so neither can be required, and issue date and net premium are not on every
policy; these four are optional.

```yaml
  policy:
    values:
      insurer: Versicherer
      policy_number: Versicherungsscheinnummer
      policyholder: Versicherungsnehmer
      line_of_business: Sparte
      start_date: Beginn
      end_date: Ablauf
      payment_mode: Zahlungsweise
    optional:
      premium: Beitrag
      annual_premium: Jahresbeitrag
      net_premium: Nettobeitrag
      issue_date: Ausstellungsdatum
```

A contract change names the contract, the date from which it applies and the
new premium; all six values are on every such letter, and nothing is
optional. A premium invoice names the contract, the due date and the amount
to pay; what it prints beyond that (its date, the period, net premium and
insurance tax) is optional.

### 5. Choose the columns of the overview

The overview lists every document of an import with its file, kind and
state, and with the values named under `overview_columns`. A clerk at a
broker recognises a contract by insurer, number and premium:

```yaml
overview_columns:
  insurer: Versicherer
  policy_number: Nummer
  premium: Beitrag
```

### 6. Decide about the hand-over

Without a block `hand_over`, an approval writes the job file as JSON into
the folder `Ausgabe` inside the watched folder if a writer is registered
for the target. None is
registered in the shipped application, so the job ends as failed with the
reason `target-without-writer` and nothing is written. The approval itself,
its record and the corrections are stored all the same.

With the block, the approved jobs of one customer leave as one file of the
named format when a person starts a run for that customer. One format
exists, `gdv`; its settings are:

| Key | Required | Meaning |
|---|---|---|
| `format` | yes | `gdv`; it chooses the writer. |
| `encoding` | yes | A codec with one byte per character, for example `cp850`. |
| `record_separator` | yes | `crlf` or `none`. |
| `broker_number` | yes | Up to 10 letters and digits. |
| `sender`, `addressee` | yes | Up to 30 characters each. |
| `currency` | yes | Three capital letters, for example `EUR`. |
| `contract_kinds` | yes | The kinds written as address and contract part. |
| `collection_kinds` | yes | The kinds written as address, contract part and collection record. A kind in neither list is held back as `kind_not_handed_over`. |
| `sender_kind`, `addressee_kind`, `contract_status`, `collection_kind`, `debit_kind` | no | Codes of facts that stand on no paper; one that is left out leaves its field empty. |

None of the required settings has a default. A block that lacks one fails
the jobs of a run with `hand-over-settings-invalid` and the names of the
keys. The meaning of every setting, the codes, and what the writer needs
from the values are in [`gdv-hand-over.md`](gdv-hand-over.md), section “The
block `hand_over` of a profile”. With this format the names on the left of
`values` and `optional` must be the ones that document lists, and the
insurers, lines of business and payment modes of the broker must stand in
the tables under `<data dir>/gdv/`.

Encoding, record separator and broker number are facts only the broker and
the vendor of the target program have. The shipped profile therefore has no
block, and this step adds nothing to the example; `scripts/walk-through.sh`
appends an invented block to a copy of it.

### The result

<!-- worked-example: tests/sidecar/test_second_profile.py compares this block with insurance_folder.yml -->
```yaml
name: insurance_folder
title: Beispielziel
target: example_target

customer_folder_level: 1

overview_columns:
  insurer: Versicherer
  policy_number: Nummer
  premium: Beitrag

kinds:
  policy:
    values:
      insurer: Versicherer
      policy_number: Versicherungsscheinnummer
      policyholder: Versicherungsnehmer
      line_of_business: Sparte
      start_date: Beginn
      end_date: Ablauf
      payment_mode: Zahlungsweise
    optional:
      premium: Beitrag
      annual_premium: Jahresbeitrag
      net_premium: Nettobeitrag
      issue_date: Ausstellungsdatum
  contract_change:
    values:
      insurer: Versicherer
      policy_number: Versicherungsscheinnummer
      policyholder: Versicherungsnehmer
      line_of_business: Sparte
      change_date: Änderungsdatum
      premium: Beitrag
  premium_invoice:
    values:
      insurer: Versicherer
      policy_number: Versicherungsscheinnummer
      policyholder: Versicherungsnehmer
      line_of_business: Sparte
      due_date: Fälligkeit
      premium: Beitrag
    optional:
      invoice_date: Rechnungsdatum
      period_start: Zeitraum von
      period_end: Zeitraum bis
      net_premium: Nettobeitrag
      insurance_tax: Versicherungsteuer
```

This is the content of the shipped file; the shipped file adds comments.

## Checking a new profile

1. Put the file into `<data dir>/pipeline_profiles/` and ask for the
   settings of the inbox: the profile is listed with its title, or the
   answer is `pipeline-profile-invalid` with the position of the error.
2. Choose it, put one document of every kind into a customer folder, and
   look at the entries: kind, customer and the values with their state.
3. Approve one entry and read the job: `profile`, `target`, `customer` and
   the values under the names of the target.

`tests/sidecar/fixtures/second_profile.yml` is a second complete example:
an invented archive as the target, the customer on the second folder level,
two kinds and other values.

## What a profile cannot do

- It reads no new kind of document; that is a kind file.
- It writes no new format. A format is a module with `check`, `hand_over`
  and `PART` and one entry in `FORMATS` of `sidecar/substrakt/hand_over.py`.
- It cannot name a customer from anything but a folder name: not from the
  file name and not from a value on the document.
- It applies to one watched folder at a time, because one profile is active.
