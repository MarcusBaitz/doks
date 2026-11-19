/**
 * The frontend's only route to the backend.
 *
 * The browser knows neither the sidecar port nor its session token. Every call
 * goes through a Tauri command in `src-tauri/src/bridge.rs`; ESLint and the
 * repository egress gate reject a direct browser network path.
 */

import { invoke } from '@tauri-apps/api/core'

import type {
  DocumentInfo,
  DocumentText,
  DocumentType,
  Export,
  FieldSpec,
  ExtractionRun,
  InboxCorrection,
  InboxEntry,
  InboxImport,
  InboxSettings,
  HandOverPreview,
  Job,
  KindValues,
  ProfileDescription,
  ProfileKind,
  SheetInfo,
  SheetRaster,
  Status,
  ValueChange,
  WordList,
} from './types'
import { isBridgeError } from './types'
import { errorText } from '../i18n'
import { de } from '../i18n/de'

/** Error with an already translated display message and a stable key. */
export class SubstraktError extends Error {
  readonly key: string
  readonly detail: string | null
  /** Why a correction or approval was refused, such as `entry-changed`. */
  readonly reason: string | null
  /** What a refused approval names, such as `kind_not_handed_over` or `value_fits_field:policy_number`. */
  readonly items: string[]

  constructor(
    key: string,
    message: string,
    detail: string | null = null,
    reason: string | null = null,
    items: string[] = [],
  ) {
    super(message)
    this.name = 'SubstraktError'
    this.key = key
    this.detail = detail
    this.reason = reason
    this.items = items
  }
}

async function call<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  try {
    return await invoke<T>(command, args)
  } catch (error) {
    if (isBridgeError(error)) {
      throw new SubstraktError(
        error.key,
        errorText(de, error.key, error.title),
        error.detail,
        error.reason ?? null,
        error.items ?? [],
      )
    }
    // A non-bridge error is a frontend defect and receives its own stable key.
    throw new SubstraktError(
      'internal-error',
      errorText(de, 'internal-error', de.errors.title),
      error instanceof Error ? error.message : String(error),
    )
  }
}

export const api = {
  status: () => call<Status>('sidecar_status'),

  loadDocument: (path: string) => call<DocumentInfo>('load_document', { path }),

  documentInfo: (docId: string) => call<DocumentInfo>('document_info', { docId }),

  closeDocument: (docId: string) =>
    call<{ removed: boolean }>('close_document', { docId }),

  /** Raw file bytes for PDF.js. */
  documentBytes: async (docId: string): Promise<Uint8Array> => {
    const data = await call<ArrayBuffer | number[]>('document_bytes', { docId })
    return data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(data)
  },

  documentText: (docId: string) => call<DocumentText>('document_text', { docId }),

  pageWords: (docId: string, page: number) =>
    call<WordList>('page_words', { docId, page }),

  /** Rendered PNG page for images; PDF.js renders PDF pages itself. */
  renderPage: async (docId: string, page: number, scale = 1): Promise<Blob> => {
    const data = await call<ArrayBuffer | number[]>('render_page', { docId, page, scale })
    const bytes = data instanceof ArrayBuffer ? new Uint8Array(data) : new Uint8Array(data)
    return new Blob([bytes], { type: 'image/png' })
  },

  sheets: (docId: string) => call<SheetInfo[]>('sheets', { docId }),

  sheetRaster: (docId: string, index: number) =>
    call<SheetRaster>('sheet_raster', { docId, index }),

  /**
   * Extraction path A: region, regular expression and built-in extractors.
   * Manual values take precedence, which is the only path for handwriting.
   */
  extract: (docId: string, fields: FieldSpec[], manual?: Record<string, string>) =>
    call<ExtractionRun>('extract', { docId, fields, manual }),

  /**
   * Like `extract`, but with values and provenance separated for export.
   * `confirmed` names values a person accepted without a location.
   */
  export: (
    docId: string,
    fields: FieldSpec[],
    manual?: Record<string, string>,
    confirmed?: string[],
  ) => call<Export>('export', { docId, fields, manual, confirmed }),

  sampleFields: () => call<FieldSpec[]>('sample_fields'),

  /** Persisted value sets without their values, used by the template list. */
  documentTypes: () => call<DocumentType[]>('document_types'),

  documentType: (typeId: number) => call<DocumentType>('document_type', { typeId }),

  saveDocumentType: (
    type: Omit<DocumentType, 'id' | 'updated_at' | 'value_count'>,
  ) => call<DocumentType>('save_document_type', { documentType: type }),

  deleteDocumentType: (typeId: number) =>
    call<{ deleted: boolean }>('delete_document_type', { typeId }),

  /** Everything that arrived in the watched folder, oldest first. */
  inboxEntries: () => call<InboxEntry[]>('inbox_entries'),

  inboxSettings: () => call<InboxSettings>('inbox_settings'),

  /** Chooses a folder to watch, a profile, a hand-over folder, or several. */
  chooseInboxSettings: (choice: {
    folder?: string
    profile?: string
    retentionDays?: number
  }) => call<InboxSettings>('choose_inbox_settings', choice),

  /** The kinds of a profile with their values, labels and which ones an approval requires. */
  profileKinds: (profile: string) => call<ProfileKind[]>('profile_kinds', { profile }),

  /** Stores a corrected kind or corrected values with the entry. */
  correctInboxEntry: (entryId: number, correction: InboxCorrection) =>
    call<InboxEntry>('correct_inbox_entry', { entryId, correction }),

  /** Decides a possible duplicate: the same document as the other entry, or a new one. */
  decideDuplicate: (entryId: number, same: boolean) =>
    call<InboxEntry>('decide_duplicate', { entryId, same }),

  /** Deletes an entry with its job and job file; the scan only when asked. */
  deleteInboxEntry: (entryId: number, deleteFile = false) =>
    call<{ deleted: boolean }>('delete_inbox_entry', { entryId, deleteFile }),

  /** Approves an entry; refused while a required value is open or unclear. */
  approveInboxEntry: (entryId: number) => call<Job>('approve_inbox_entry', { entryId }),

  jobs: () => call<Job[]>('jobs'),

  /** Writes the pending jobs of one customer as one hand-over file. */
  runHandOver: (customer: string) => call<Job[]>('run_hand_over', { customer }),

  /** What a run for one customer would write now; nothing is written. */
  previewHandOver: (customer: string) =>
    call<HandOverPreview>('preview_hand_over', { customer }),

  /** Reports the import of a customer's hand-over: imported, or failed with a reason. */
  reportImport: (customer: string, imported: boolean, reason = '') =>
    call<Job[]>('report_import', { customer, imported, reason }),

  /** Releases a failed job again. */
  releaseJob: (jobId: string) => call<Job>('release_job', { jobId }),

  /** Every chosen folder, oldest first; an entry names its import by id. */
  inboxImports: () => call<InboxImport[]>('inbox_imports'),

  /** Every document kind with the values it reads, for Templates. */
  documentKinds: () => call<KindValues[]>('document_kinds'),

  /** Stores the complete new list of values of a kind; a value left out is removed. */
  changeKindValues: (kind: string, values: ValueChange[]) =>
    call<KindValues>('change_kind_values', { kind, values }),

  /** A profile with the titles and labels of its kinds. */
  pipelineProfile: (name: string) => call<ProfileDescription>('pipeline_profile', { name }),
}
