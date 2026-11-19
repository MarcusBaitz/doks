/**
 * Types for the sidecar contract.
 *
 * This mirrors `sidecar/substrakt/model.py`, which is authoritative.
 * `scripts/check-api.py` compares both views with `schema/openapi.json`.
 */

export type { ImageRect, Locator, PdfRect, Rotation, SheetRange } from '../viewer/coords'

import type { Locator } from '../viewer/coords'

export type DocumentFormat = 'pdf' | 'sheet' | 'image'

/** Origin of the text, recorded and displayed per document. */
export type TextSource = 'text_layer' | 'ocr' | 'vlm' | 'cells' | 'none'

export interface Page {
  number: number
  /** PDF points or pixels; column count for spreadsheets. */
  width: number
  /** PDF points or pixels; row count for spreadsheets. */
  height: number
  rotation: 0 | 90 | 180 | 270
  sheet_name: string | null
  has_text_layer: boolean
}

export interface Word {
  text: string
  page: number
  locator: Locator
  /** `null` for an exact text layer, set for OCR. */
  confidence: number | null
}

export interface DocumentMeta {
  size_bytes: number
  page_count: number
  word_count: number
  text_source: TextSource
  encoding: string | null
  delimiter: string | null
  producer: string | null
  created: string | null
  warnings: string[]
}

/** Document without its word index — the response from `load_document`. */
export interface DocumentInfo {
  id: string
  filename: string
  sha256: string
  kind: DocumentFormat
  pages: Page[]
  meta: DocumentMeta
}

export interface TextChunk {
  page: number
  text: string
  sheet_name: string | null
}

export interface DocumentText {
  chunks: TextChunk[]
  text_source: TextSource
}

export interface WordList {
  page: number
  words: Word[]
}

export interface SheetInfo {
  index: number
  name: string
  rows: number
  columns: number
}

export interface SheetRaster {
  index: number
  name: string
  rows: string[][]
}

// --- Extraction ------------------------------------------------------------

export type JsonType = 'string' | 'number' | 'integer' | 'date' | 'boolean'
export type Method = 'auto' | 'region' | 'regex' | 'extractor'
export type Source = 'region' | 'regex' | 'extractor' | 'manual' | 'none'

export interface FieldSpec {
  /** Key in ExtractionResult, such as `document_number`; never shown in the UI. */
  name: string
  /** User-facing label, such as “Rechnungsnummer”. */
  label: string
  question: string
  json_type: JsonType
  required: boolean
  method: Method
  regex: string | null
  extractor: string | null
  normalization: string | null
  regions: Locator[]
  /**
   * How a value is found next to its label. This comes from the document-kind
   * YAML file; user-created fields have no rule.
   */
  label_rule?: LabelRule | null
}

/** Rule from `sidecar/substrakt/document_kinds/*.yml`; mirrors Python `LabelRule`. */
export interface LabelRule {
  patterns: string[]
  value: 'identifier' | 'date' | 'amount' | 'code' | 'vat_id' | 'company' | 'title'
  values: string[]
  skip_tax_rate: boolean
  unlabelled: boolean
  letterhead_until: string[]
}

/** An extracted value together with its review evidence. */
export interface ExtractionResult {
  field: string
  value: string | null
  normalized: string | number | boolean | null
  confidence: number
  source: Source
  locator: Locator | null
  matched_text: string
  /** False below the threshold or without evidence, requiring review. */
  grounded: boolean
  note: string
}

export interface ExtractionRun {
  results: ExtractionResult[]
  duration_ms: number
  ungrounded: number
  /** Name of the recognised document kind; `null` means none was clear. */
  kind?: string | null
}

export interface Export {
  document: { file_name: string; sha256: string; pages: number; kind: DocumentFormat }
  data: Record<string, unknown>
  provenance: Record<string, unknown>
  run: { duration_ms: number; ungrounded: number; fields: number; version: string }
}

/**
 * A persisted, named set of values. List responses omit `fields` and include
 * `value_count`, avoiding one request per template just to show a count.
 */
export interface DocumentType {
  id: number | null
  name: string
  description: string
  fields: FieldSpec[]
  updated_at: string
  /** Whether each document becomes a table row or a separate file. */
  output: OutputFormat
  value_count: number
}

export type OutputFormat = 'table' | 'file'

export interface Status {
  connected: boolean
  version: string
  mode: 'airgap' | 'onprem' | 'cloud'
  /** Label shown in the technical status row. */
  backend: string
}

/** Bridge error whose stable key is resolved through the active dictionary. */
export interface BridgeError {
  key: string
  title: string
  detail: string | null
  status: number
  /** Why a correction or approval was refused; absent for other errors. */
  reason?: string | null
  /** What a refused approval names, such as `payment_mode_code`; names only, never values. */
  items?: string[]
}

export function isBridgeError(value: unknown): value is BridgeError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'key' in value &&
    typeof (value as BridgeError).key === 'string'
  )
}

// --- Inbox -------------------------------------------------------------------

/**
 * `new` is found and being read, `waiting` is read and waits for a person,
 * `approved` has a job, `duplicate` has content that was already read,
 * `error` could not be read.
 */
export type InboxState = 'new' | 'waiting' | 'approved' | 'duplicate' | 'error'

/** One file that arrived in the watched folder. Mirrors `sidecar/substrakt/inbox.py`. */
export interface InboxEntry {
  id: number
  import_id: number
  state: InboxState
  file_path: string
  /** The folder the file arrived in. */
  folder: string
  file_name: string
  sha256: string
  /** Null when the file lies outside a customer folder. */
  customer: string | null
  /** The profile the entry was read with. */
  profile: string
  /** Null when no kind was recognised. */
  kind: string | null
  /** Null for an entry that was not read. */
  page_count: number | null
  values: ExtractionResult[]
  /** Milliseconds per step. */
  timings: Record<string, number>
  /** The first entry with the same content, for state `duplicate`. */
  duplicate_of: number | null
  /** Another entry with the same identifying values; a person decides. */
  possible_duplicate_of: number | null
  duplicate_decision: 'same' | 'new' | null
  /** Stable problem key, for state `error`. */
  problem_key: string | null
  /** Values a person changed since the kind was last set; shown bold in Review. */
  changed: string[]
  /** True when the file arrived after the import of the folder had finished. */
  later_arrival: boolean
  arrived_at: string
}

export interface InboxSettings {
  folder: string | null
  /** Where approved jobs are written as files. */
  handover_folder: string | null
  profile: string | null
  profiles: { name: string; title: string }[]
  watching: boolean
  /** Days an entry is kept after its job is done. */
  retention_days: number
}

/** A value of a kind as Review shows it. Mirrors `KindValue` in `sidecar/substrakt/app.py`. */
export interface KindValue {
  name: string
  label: string
  question: string
  /** True when an approval requires it; optional values never block. */
  required: boolean
  /** The type from the kind file (`string`, `date`, `number`, …); Review masks a `date`. */
  json_type: string
}

/** A kind of a pipeline profile with the values its profile expects. */
export interface ProfileKind {
  name: string
  title: string
  values: KindValue[]
}

/** What a person changed on an entry: the kind, values by name, or both. */
export interface InboxCorrection {
  kind?: string
  values?: Record<string, string>
  /** Values a person confirmed as read; they keep text and location. */
  confirmed?: string[]
}

export type JobState = 'pending' | 'handed_over' | 'done' | 'failed'

/** The job file. Mirrors `JobFile` in `sidecar/substrakt/jobs.py`. */
export interface JobFile {
  version: 1
  id: string
  idempotency_key: string
  approved_at: string
  profile: string
  target: string
  kind: string
  customer: string | null
  file: { path: string; sha256: string }
  pages: { first: number; last: number }
  /** Approved values by their name in the target. */
  values: Record<string, { text: string; normalized: string | number | boolean | null }>
}

export interface JobTransition {
  /** Null for the creation of the job. */
  from_state: JobState | null
  to_state: JobState
  /** A stable key such as `approved` or `target-without-writer`. */
  reason: string
  at: string
  /** Who approved or released; null where the application moved the job. */
  account: string | null
}

export interface Job {
  id: string
  entry_id: number
  state: JobState
  file: JobFile
  /** Where the job file was written; null until it was handed over. */
  handover_path: string | null
  transitions: JobTransition[]
}

/** One thing the hand-over format names that keeps a document out of the file. */
export interface HandOverItem {
  /** A stable name such as `insurer_number` or `one_contract_per_policy_number`. */
  item: string
  /** The approved value the mapping table does not know, when there is one. */
  value?: string | number | boolean
  /** The value that does not fit its field, by its name in the kind. */
  field?: string
}

/** What a run would write. Mirrors `Preview` in `sidecar/substrakt/hand_over.py`. */
export interface HandOverPreview {
  customer: string
  /** Job ids the file would hold, one list per contract. */
  contracts: string[][]
  /** Job ids the file would leave out, with what keeps each one out. */
  waiting: Record<string, HandOverItem[]>
  /** A reason key when nothing of the customer can be written. */
  problem: string | null
}

// --- Overview and Settings of the broker pilot ------------------------------

/** One chosen folder. Mirrors `InboxImport` in `sidecar/substrakt/inbox.py`. */
export interface InboxImport {
  id: number
  folder: string
  started_at: string
  /** Set once every file found so far was read; later arrivals come after it. */
  finished_at: string | null
}

/** A profile in words. Mirrors `ProfileDescription` in `pipeline_profiles/__init__.py`. */
export interface ProfileDescription {
  name: string
  title: string
  target: string
  customer_folder_level: number | null
  kinds: {
    name: string
    title: string
    values: { name: string; label: string; target_name: string; required: boolean }[]
  }[]
  /** Value name to column heading, in order. */
  overview_columns: Record<string, string>
}

/** A document kind with the values it reads. Mirrors `KindValues` in `kind_values.py`. */
export interface KindValues {
  name: string
  title: string
  values: { name: string; label: string }[]
}

/** One line of a changed kind; a value without a name is new and named by its label. */
export interface ValueChange {
  name: string | null
  label: string
}
