# Development

## Commands

| Command | What it does |
|---|---|
| `npm start` | set up, fetch models and start (see [Getting started](getting-started.md)) |
| `npm run app` | start the app in development mode |
| `npm run app:wsl` | the same under WSL2 |
| `npm run check` | typecheck, lint, frontend and sidecar tests, licence and egress gates |
| `npm run test` | frontend tests (Vitest) |
| `npm run test:sidecar` | sidecar tests (pytest) |
| `npm run lint` | ESLint, including the colour and egress rules |
| `npm run typecheck` | TypeScript contract |
| `npm run licenses` | licence gate for Python and npm |
| `npm run egress` | grep-based egress gate |
| `npm run corpus` | generate the synthetic test corpus into `corpus/out/` |
| `npm run bench` | measure performance budgets |

Rust checks run in `src-tauri/`:

```bash
export PATH="$HOME/.cargo/bin:$PATH"   # cargo is not on every shell's PATH
cd src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
```

## Project layout

```text
src/                    React frontend
  App.tsx               entry point, switches between the four places
  places/               the four places and the template assistant
  viewer/               document viewer, overlays, coords.ts
  api/                  Tauri client and hand-written types
  i18n/                 German and English texts, context and language storage
  design/tokens.css     the only place with colour values
  state/session.ts      session state
  results/save.ts       saving results
  shell/Sidebar.tsx     navigation between places
  ui/components.tsx     shared interface components
src-tauri/src/          Rust shell: lib, sidecar, bridge, egress, policy
sidecar/substrakt/      Python sidecar
  app.py                FastAPI endpoints
  parsers/              PDF, images, spreadsheets, OCR
  extraction/           fields, extractors, normalisation, grounding
  document_kinds/       YAML document kinds, schema and custom parsers
  db/                   SQLite migrations and persisted types
  store.py              loaded documents, in memory only
tests/frontend/         Vitest
tests/sidecar/          pytest and the shared coordinate fixture
corpus/                 synthetic test corpus generators; evaluation corpus v1
bench/                  benchmarks, not shipped
licenses/policy.toml    licence rules, single source of truth
scripts/                setup, model download and gate scripts
docs/                   documentation, decisions, measurements
```

## Adding an endpoint

A new endpoint passes through five places, none of them generated:

1. Pydantic model in `sidecar/substrakt/model.py` or `db/models.py`.
2. FastAPI route in `sidecar/substrakt/app.py` with a `response_model`.
3. The matching TypeScript type in `src/api/types.ts`, by hand.
4. A Tauri command in `src-tauri/src/bridge.rs`, registered in `lib.rs`.
5. A wrapper in `src/api/client.ts`.

A new domain error needs a stable key in `sidecar/substrakt/errors.py` and
matching texts in `src/i18n/de.ts` and `src/i18n/en.ts`.

## Tests

- **Frontend** (`tests/frontend/`): coordinates, image rotation, and the four
  places. Interface tests mock `pdfjs-dist`, because PDF.js needs `DOMMatrix`,
  which Node does not provide.
- **Sidecar** (`tests/sidecar/`): parsers, API, migrations, extractors,
  normalisation, grounding, OCR, manual values. `conftest.py` sets the
  environment at module level, before `app.py` reads its configuration.
  Property-style tests use `random.Random(seed)` so failures are reproducible.
- **Rust**: unit tests next to the modules in `src-tauri/src/`.

A test should run the production path and the relevant failure cases. The
stage 1 report (`docs/status.md`) records why: a green path-check test set its
own read roots while the real process received none.

## Evaluation corpus

`corpus/evaluation/v1` holds 84 synthetic PDFs with ground truth, stored in
Git LFS. It is frozen: no document or expected value is changed after a model
result. See [`corpus/evaluation/README.md`](../corpus/evaluation/README.md).

## Walk-through

`npm run walk-through` lets a person walk once from the watched folder to the
report of an import, in the real application window and with synthetic
documents only. It runs on Linux and under WSL2, after `npm ci` and
`uv sync --all-groups` in `sidecar/`.

The script `scripts/walk-through.sh` builds `~/substrakt-walk-through`
(another folder with `WALK_THROUGH_DIR=<dir>`), wipes and rebuilds it at
every start, and starts the application against it:

| Path | What it is |
|---|---|
| `scans/` | the watched folder, one subfolder per customer |
| `scans/Ausgabe/` | where the hand-over goes; created when `scans/` is chosen and never read as a customer |
| `share/` | the data directory of this run (`XDG_DATA_HOME`) |

The run has its own database. Its profile is a copy of the shipped example
`insurance_folder.yml` with a `hand_over` block whose settings are invented
and marked as synthetic, so a GDV file can be written;
`WALK_THROUGH_PROFILE=<file>` copies another profile instead, for example
the one of a customer setup ([`configuration.md`](configuration.md),
section “Customer setup”). Its insurer table leaves out Wattenmeer
Assekuranz SE on purpose. `WALK_THROUGH_PREPARE_ONLY=1` builds the folder
and the data directory and starts nothing.

What lies in `scans/`, from the synthetic corpus:

- **Tischlerei Okafor**: two policies as text PDFs and a premium invoice as a
  scan; the Wattenmeer policy cannot be approved, because its insurer has no
  entry in the table.
- **Jonas Brandt**: a policy, and 90 seconds after the start a premium
  invoice as a later arrival.
- **Mira Lindqvist**: a policy, the same policy again with other bytes (a
  possible duplicate), and a contract change as a scan.

The path:

1. **Choose the folder.** On Overview, „Ordner einlesen“ asks for the
   watched folder; choose `~/substrakt-walk-through/scans`. The application
   creates `scans/Ausgabe`; the way of working is chosen already, since
   there is only one.
2. **Watch Overview fill.** One entry per import with its three customers.
   Choose the folder within 90 seconds, or the later invoice counts as part
   of the first import.
3. **Review.** „Jetzt prüfen“ opens Prüfen with one document at a time:
   confirm a value with „Stimmt so“, correct it with „Ändern“, or type a
   value the document lacks. A click on a document's state on Overview opens
   that document, for example one of the scans.
4. **Decide the possible duplicate.** `policy_c_1_again.pdf` shows both
   documents side by side; answer „Derselbe Beleg“.
5. **Approve.** „Beleg freigeben“ on each document to hand over. A document
   the hand-over could not write is refused at once with the reason: the
   Wattenmeer policy for its insurer, the contract change because the format
   does not hand it over, some policies for a payment mode the invented
   tables lack.
6. **Look at the simulation.** „Übergabe ansehen“ shows per customer and
   contract every value that would be written, with its source.
7. **Write and report.** „Übergabe schreiben“ writes one GDV file per
   customer into `scans/Ausgabe/`. Then record per customer „Erledigt“ or
   „Fehlgeschlagen“ with a reason; a failed hand-over can be released again.

The GDV file is written with invented settings, and nobody has imported such
a file into any program; „Erledigt“ only records what the person says.
Close the window to end the run.
