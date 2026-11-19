/**
 * Renders every user place in both languages and enforces the interface
 * vocabulary. The rendered gate catches a raw internal key even when the
 * dictionaries themselves are complete.
 *
 * The assistant and template detail are excluded: no place reaches them in
 * the pilot (docs/decisions.md, “Interface clarity”), which the
 * import walk from src/main.tsx below proves.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

// PDF.js reads `DOMMatrix` while its module loads, but Node does not provide
// it. These tests cover interface language and structure, not PDF drawing.
vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: () => ({ promise: Promise.resolve(null) }),
}))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '' }))

import type {
  ExtractionResult,
  FieldSpec,
  HandOverPreview,
  InboxEntry,
  KindValues,
  ProfileKind,
  Job,
  JobState,
  ProfileDescription,
  Status,
} from '../../src/api/types'
import {
  applyLanguage,
  LanguageProvider,
  storedLanguage,
  type Language,
} from '../../src/i18n'
import { reviewOf, shownError, sidebarPlace } from '../../src/App'
import { api, SubstraktError } from '../../src/api/client'
import { errorText } from '../../src/i18n'
import { InboxReview, SameContent } from '../../src/places/InboxReview'
import { de } from '../../src/i18n/de'
import { en } from '../../src/i18n/en'
import {
  FeedbackView,
  HandOverView,
  canSave,
  importFailure,
  itemText,
  wordsOf,
  problemText,
} from '../../src/places/HandOver'
import {
  Overview,
  PERIODS,
  filtered,
  folderName,
  handOverSteps,
  headline,
  inPeriod,
  matches,
  opensReview,
  periodStart,
  RowDetails,
  shownDocuments,
  shownValue,
  type InboxView,
  type Stage,
} from '../../src/places/Overview'
import { Review, pick } from '../../src/places/Review'
import { KindScreen, KindView } from '../../src/places/KindView'
import { changeLine, Settings, SettingsView, type Line } from '../../src/places/Settings'
import { ReadFolderView, wayInWords } from '../../src/places/ReadFolder'
import { Templates } from '../../src/places/Templates'
import { Sidebar } from '../../src/shell/Sidebar'
import type { DocumentRecord, Session } from '../../src/state/session'

const noop = () => undefined

const STATUS: Status = {
  connected: true,
  version: '0.1.0',
  mode: 'airgap',
  backend: 'sidecar',
}

function field(name: string, label: string): FieldSpec {
  return {
    name,
    label,
    question: '',
    json_type: 'string',
    required: false,
    method: 'auto',
    regex: null,
    extractor: null,
    normalization: null,
    regions: [],
  }
}

/** A record with one unclear value: the case the review place is built for. */
function record(): DocumentRecord {
  return {
    id: 'b1',
    docId: 'd1',
    document: {
      id: 'd1',
      filename: 'Rechnung 2026-0145.pdf',
      sha256: '',
      kind: 'pdf',
      pages: [
        {
          number: 1,
          width: 595,
          height: 842,
          rotation: 0,
          sheet_name: null,
          has_text_layer: true,
        },
      ],
      meta: {
        size_bytes: 120_000,
        page_count: 1,
        word_count: 300,
        text_source: 'text_layer',
        encoding: null,
        delimiter: null,
        producer: null,
        created: null,
        warnings: [],
      },
    },
    fileName: 'Rechnung 2026-0145.pdf',
    template: 'Rechnung — Nordwind Maschinenbau',
    templateId: 1,
    output: 'table',
    readAt: new Date(Date.now() - 5 * 60_000).toISOString(),
    state: 'waiting',
    fields: [field('zahlungsbedingungen', 'Zahlungsbedingungen'), field('iban', 'IBAN')],
    results: [
      {
        field: 'zahlungsbedingungen',
        value: '14 Tage 2 % Skonto, 30 Tage netto',
        normalized: null,
        confidence: 0.74,
        source: 'region',
        locator: { kind: 'pdf_rect', page: 0, x0: 50, y0: 600, x1: 300, y1: 620 },
        matched_text: '14 Tage',
        grounded: false,
        note: 'Confidence too low — review required',
      },
      {
        field: 'iban',
        value: 'DE21 2105 0170 1002 3456 78',
        normalized: null,
        confidence: 0.99,
        source: 'extractor',
        locator: null,
        matched_text: 'DE21',
        grounded: true,
        note: '',
      },
    ],
    corrections: {},
    missing: [],
    confirmed: [],
  }
}

function session(records: DocumentRecord[]): Session {
  return {
    records,
    reviewCount: records.filter((item) => item.state === 'waiting').length,
    gaps: records.filter((item) => item.missing.length > 0).length,
    add: () => records[0]!,
    change: noop,
    remove: noop,
  }
}

// Review of entries from the watched folder (broker pilot). Labels come from
// the kind file; ASCII labels keep the English render free of German copy.
const KINDS: ProfileKind[] = [
  {
    name: 'policy',
    title: 'Policy',
    values: [
      { name: 'insurer', label: 'Insurer', question: '', required: true, json_type: 'string' },
      { name: 'premium', label: 'Premium', question: '', required: true, json_type: 'string' },
      { name: 'payment_mode', label: 'Payment mode', question: '', required: false, json_type: 'string' },
    ],
  },
]
// --- Broker pilot: inbox fixtures ------------------------------------------
// Names are ASCII and file names avoid underscores, so that the English render
// and the snake_case gate check the interface copy, not the sample data.

const PROFILE: ProfileDescription = {
  name: 'broker',
  title: 'Broker program',
  target: 'gdv',
  customer_folder_level: 1,
  kinds: [
    {
      name: 'policy',
      title: 'Police',
      values: [
        { name: 'insurer', label: 'Versicherer', target_name: 'insurer', required: true },
        { name: 'policy_number', label: 'Nummer', target_name: 'number', required: true },
        { name: 'premium', label: 'Beitrag', target_name: 'premium', required: false },
      ],
    },
  ],
  overview_columns: { insurer: 'Versicherer', policy_number: 'Nummer', premium: 'Beitrag' },
}

/** A profile that reads two kinds; Templates lists exactly these two. */
const TWO_KINDS: ProfileDescription = {
  ...PROFILE,
  kinds: [
    PROFILE.kinds[0]!,
    { name: 'premium_invoice', title: 'Beitragsrechnung', values: [] },
  ],
}

/** The policy as Templates lists it: two values go to the target, one is only shown. */
const KIND: KindValues = {
  name: 'policy',
  title: 'Police',
  values: [
    { name: 'insurer', label: 'Versicherer' },
    { name: 'policy_number', label: 'Nummer' },
    { name: 'line_of_business', label: 'Sparte' },
  ],
}

/** Kinds the sidecar knows; the claim belongs to no profile and is never listed. */
const INVOICE: KindValues = { name: 'premium_invoice', title: 'Beitragsrechnung', values: [{ name: 'premium', label: 'Beitrag' }] }
const CLAIM: KindValues = { name: 'claim', title: 'Schadenmeldung', values: [{ name: 'damage', label: 'Schaden' }] }
/** The policy's lines with its first value renamed and not yet saved. */
const RENAMED = [
  { name: 'insurer', label: 'Gesellschaft', removed: false },
  { name: 'policy_number', label: 'Nummer', removed: false },
  { name: 'line_of_business', label: 'Sparte', removed: false },
]

/** One kind in a state the screen can be in. */
function kindIn(
  language: Language,
  state: { rows?: typeof RENAMED; asking?: boolean; saved?: boolean; refusal?: string },
): string {
  return renderIn(
    language,
    <KindScreen
      kind={KIND}
      profile={PROFILE}
      rows={state.rows ?? KIND.values.map((v) => ({ name: v.name, label: v.label, removed: false }))}
      asking={state.asking ?? false}
      saving={false}
      saved={state.saved ?? false}
      refusal={state.refusal ?? null}
      onChange={noop}
      onSave={noop}
      onBack={noop}
      onDiscard={noop}
      onKeepEditing={noop}
    />,
  )
}

function value(name: string, text: string, grounded = true): ExtractionResult {
  return {
    field: name,
    value: text,
    normalized: null,
    confidence: grounded ? 0.98 : 0.6,
    source: 'extractor',
    locator: { kind: 'pdf_rect', page: 0, x0: 50, y0: 600, x1: 300, y1: 620 },
    matched_text: text,
    grounded,
    note: '',
  }
}

function inboxEntry(overrides: Partial<InboxEntry> = {}): InboxEntry {
  return {
    id: 7,
    import_id: 1,
    state: 'waiting',
    file_path: '/scans/Brandt/policy.pdf',
    folder: '/scans/Brandt',
    file_name: 'policy.pdf',
    sha256: 'ab',
    customer: 'Brandt',
    profile: 'broker',
    kind: 'policy',
    page_count: 1,
    values: [value('insurer', 'Nordlicht AG'), value('premium', '156.64', false)],
    timings: {},
    duplicate_of: null,
    possible_duplicate_of: null,
    duplicate_decision: null,
    problem_key: null,
    changed: [],
    later_arrival: false,
    arrived_at: '2026-11-11T09:00:00Z',
    ...overrides,
  }
}

function inbox(entry: InboxEntry, first: InboxEntry | null = null) {
  const done = () => Promise.resolve()
  return (
    <InboxReview
      entry={entry}
      position={{ n: 1, total: 3 }}
      kinds={KINDS}
      document={null}
      first={first && { entry: first, document: null }}
      onCorrect={done}
      onDecide={done}
      onApprove={done}
      onLater={noop}
      onBack={noop}
      onError={noop}
    />
  )
}

const SETTLED = inboxEntry({
  values: [value('insurer', 'Nordlicht AG'), value('premium', '160.00')],
  changed: ['premium'],
})

/** A file with the bytes of SETTLED: not read, nothing to decide. */
const SAME_BYTES = inboxEntry({ id: 9, state: 'duplicate', duplicate_of: 7, file_name: 'policy copy.pdf', kind: null, values: [] })

function entry(id: number, patch: Partial<InboxEntry> = {}): InboxEntry {
  return {
    id,
    import_id: 1,
    state: 'waiting',
    file_path: `/scans/Meyer/scan-${id}.pdf`,
    folder: '/scans/Meyer',
    file_name: `scan-${id}.pdf`,
    sha256: String(id).padStart(64, '0'),
    customer: 'Meyer',
    profile: 'broker',
    kind: 'policy',
    page_count: 1,
    values: [value('insurer', 'Nordstern'), value('policy_number', 'P-100' + id)],
    timings: {},
    duplicate_of: null,
    possible_duplicate_of: null,
    duplicate_decision: null,
    problem_key: null,
    changed: [],
    later_arrival: false,
    arrived_at: '2026-11-11T09:00:00Z',
    ...patch,
  }
}

/** A job whose last move carries the reason; a failed import names what the person typed. */
function job(entryId: number, state: JobState, customer = 'Meyer', reason = 'approved'): Job {
  return {
    id: `job-${entryId}`,
    entry_id: entryId,
    state,
    file: {
      version: 1,
      id: `job-${entryId}`,
      idempotency_key: 'key',
      approved_at: '2026-11-11T09:10:00Z',
      profile: 'broker',
      target: 'gdv',
      kind: 'policy',
      customer,
      file: { path: `/scans/${customer}/scan-${entryId}.pdf`, sha256: 'ab' },
      pages: { first: 1, last: 1 },
      values: {
        insurer: { text: 'Nordstern', normalized: 'Nordstern' },
        premium: { text: '156,64', normalized: 156.64 },
      },
    },
    handover_path: null,
    transitions: [{ from_state: null, to_state: state, reason, at: '2026-11-11T09:30:00Z', account: null }],
  }
}

function inboxView(entries: InboxEntry[], finished: boolean, jobs: Job[] = []): InboxView {
  return {
    settings: {
      folder: '/scans',
      handover_folder: '/scans/Ausgabe',
      profile: 'broker',
      profiles: [{ name: 'broker', title: 'Broker program' }, { name: 'second', title: 'Second' }],
      watching: true,
      retention_days: 90,
    },
    entries,
    imports: [
      {
        id: 1,
        folder: '/scans',
        started_at: '2026-11-11T09:00:00Z',
        finished_at: finished ? '2026-11-11T09:05:00Z' : null,
      },
    ],
    jobs,
    profile: PROFILE,
  }
}

const EMPTY: InboxView = { settings: null, entries: [], imports: [], jobs: [], profile: null }

/** While reading: two documents read, one still being read. */
const READING = inboxView(
  [entry(1), entry(2, { customer: 'Schulz', folder: '/scans/Schulz' }), entry(3, { state: 'new', kind: null, values: [] })],
  false,
)

/**
 * After the import: approved, unclear, a later arrival, a duplicate and a possible one.
 * Three per customer, so that the word gate sees every row unfolded.
 */
const AFTER = inboxView(
  [
    entry(1, { state: 'approved', customer: 'Schulz', folder: '/scans/Schulz' }),
    entry(2, { values: [value('insurer', 'Nordstern'), value('policy_number', '?', false)] }),
    entry(3, { later_arrival: true, arrived_at: '2026-11-11T10:00:00Z' }),
    entry(4, { state: 'duplicate', duplicate_of: 1, kind: null, values: [], customer: 'Schulz', folder: '/scans/Schulz' }),
    entry(5, { possible_duplicate_of: 1, customer: 'Schulz', folder: '/scans/Schulz' }),
    entry(6, { state: 'error', problem_key: 'document-corrupt', kind: null, values: [] }),
  ],
  true,
  [job(1, 'handed_over', 'Schulz')],
)

/** Everything approved and handed over: nothing waits. */
const QUIET = inboxView([entry(1, { state: 'approved' })], true, [job(1, 'done')])

// --- Hand-over: the simulation before it and the report after it --------------

const SCHULZ = { customer: 'Schulz', folder: '/scans/Schulz' }
const APPROVED = [
  entry(1, { state: 'approved', changed: ['premium'] }),
  entry(5, { state: 'approved', ...SCHULZ }),
]
/** Two customers approved: one contract can go, one waits for an unknown insurer. */
const HANDING = inboxView(APPROVED, true, [job(1, 'pending'), job(5, 'pending', 'Schulz')])
const PREVIEWS: HandOverPreview[] = [
  { customer: 'Meyer', contracts: [['job-1']], waiting: {}, problem: null },
  {
    customer: 'Schulz',
    contracts: [],
    waiting: { 'job-5': [{ item: 'insurer_number', value: 'Nordlicht AG' }] },
    problem: null,
  },
]
/** Both written; the clerk has not reported yet. */
const HANDED = inboxView(APPROVED, true, [job(1, 'handed_over'), job(5, 'handed_over', 'Schulz')])
/** One import confirmed, one reported as failed. */
const REPORTED = inboxView(APPROVED, true, [
  job(1, 'done', 'Meyer', 'import-confirmed'),
  job(5, 'failed', 'Schulz', 'import-failed: Kunde fehlt'),
])

function overviewOf(view: InboxView) {
  return (
    <Overview
      status={STATUS}
      inbox={view}
      onReview={noop}
      onChooseFolder={noop}
      onHandOver={noop}
      onFeedback={noop}
      onError={noop}
    />
  )
}

function storage(value: string | null) {
  return {
    getItem: () => value,
    setItem: vi.fn(),
  }
}

function renderIn(language: Language, node: React.ReactNode): string {
  vi.stubGlobal('localStorage', storage(language))
  return renderToStaticMarkup(<LanguageProvider>{node}</LanguageProvider>)
}

/** Removes presentation attributes, leaving the text and semantic markup. */
function readable(markup: string): string {
  return markup.replace(/\sclass="[^"]*"/g, '').replace(/\sstyle="[^"]*"/g, '')
}

function settingsIn(language: Language, saved: Line | null, refused: SubstraktError | null = null) {
  const change = async () => undefined
  return renderIn(
    language,
    <SettingsView
      status={STATUS}
      theme="light"
      onTheme={noop}
      inbox={READING.settings}
      profile={PROFILE}
      onOverview={noop}
      saved={saved}
      refused={refused}
      change={change}
      pick={change}
    />,
  )
}

function folderScreenIn(language: Language, folder: string | null) {
  return renderIn(
    language,
    <ReadFolderView profile={PROFILE} folder={folder} starting={false} onBack={noop} onPick={noop} onStart={noop} />,
  )
}

function places(language: Language) {
  return {
    'overview with records': renderIn(
      language,
      <Overview
        status={STATUS}
        inbox={AFTER}
        onReview={noop}
        onChooseFolder={noop}
        onHandOver={noop}
        onFeedback={noop}
        onError={noop}
      />,
    ),
    'empty overview': renderIn(
      language,
      <Overview
        status={null}
        inbox={EMPTY}
        onReview={noop}
        onChooseFolder={noop}
        onHandOver={noop}
        onFeedback={noop}
        onError={noop}
      />,
    ),
    'overview while reading': renderIn(
      language,
      <Overview
        status={STATUS}
        inbox={READING}
        onReview={noop}
        onChooseFolder={noop}
        onHandOver={noop}
        onFeedback={noop}
        onError={noop}
      />,
    ),
    'hand-over simulation': renderIn(
      language,
      <HandOverView inbox={HANDING} previews={PREVIEWS} writing={false} onBack={noop} onWrite={noop} />,
    ),
    'hand-over simulation of nothing': renderIn(
      language,
      <HandOverView inbox={QUIET} previews={[]} writing={false} onBack={noop} onWrite={noop} />,
    ),
    'overview after the run': renderIn(language, overviewOf(HANDED)),
    'feedback with a failed import': renderIn(
      language,
      <FeedbackView
        inbox={HANDED}
        answers={{ Meyer: { imported: true, reason: '' }, Schulz: { imported: false, reason: '' } }}
        saving={false}
        onAnswer={noop}
        onBack={noop}
        onSave={noop}
      />,
    ),
    'overview after the report': renderIn(language, overviewOf(REPORTED)),
    'review with a document read by hand': renderIn(
      language,
      <Review session={session([record()])} onError={noop} onFinish={noop} />,
    ),
    'empty review': renderIn(
      language,
      <Review session={session([])} onError={noop} onFinish={noop} />,
    ),
    'inbox review with an unclear value': renderIn(language, inbox(inboxEntry())),
    'inbox review ready for approval': renderIn(language, inbox(SETTLED)),
    'inbox review of a possible duplicate': renderIn(
      language,
      inbox(inboxEntry({ id: 8, possible_duplicate_of: 7, values: SETTLED.values }), SETTLED),
    ),
    'inbox review without a kind': renderIn(language, inbox(inboxEntry({ kind: null, values: [] }))),
    'inbox review of a value not found': renderIn(
      language,
      inbox(inboxEntry({ values: [value('insurer', 'Nordlicht AG')] })),
    ),
    'inbox review of an unclear optional value': renderIn(
      language,
      inbox(inboxEntry({ values: [...SETTLED.values, value('payment_mode', 'annual', false)] })),
    ),
    'duplicate with the same content': renderIn(
      language,
      <SameContent entry={SAME_BYTES} first={SETTLED} document={null} firstDocument={null} onFinish={noop} onError={noop} />,
    ),
    'document kinds': renderIn(
      language,
      <Templates kinds={[KIND, INVOICE, CLAIM]} profile={TWO_KINDS} onOpenKind={noop} onSettings={noop} onOverview={noop} />,
    ),
    'no document kind': renderIn(
      language,
      <Templates kinds={[KIND]} profile={null} onOpenKind={noop} onSettings={noop} onOverview={noop} />,
    ),
    'values of a kind': renderIn(
      language,
      <KindView kind={KIND} profile={PROFILE} onBack={noop} onSaved={noop} onError={noop} />,
    ),
    'kind with an unsaved change on leaving': kindIn(language, { rows: RENAMED, asking: true }),
    'kind with a refused change': kindIn(language, { rows: RENAMED, refusal: 'Zwei Angaben heissen gleich.' }),
    'kind saved': kindIn(language, { saved: true }),
    settings: renderIn(
      language,
      <Settings
        status={STATUS}
        theme="light"
        onTheme={noop}
        inbox={READING.settings}
        profile={PROFILE}
        onInbox={noop}
        onOverview={noop}
        onError={noop}
      />,
    ),
    'settings with a confirmed change': settingsIn(language, 'retention'),
    'settings with a refused folder': settingsIn(
      language,
      null,
      new SubstraktError('output-name-taken', de.errors.messages['output-name-taken']!),
    ),
    'folder screen without a folder': folderScreenIn(language, null),
    'folder screen with a folder': folderScreenIn(language, '/home/sachbearbeitung/Scans/Neukunden'),
    sidebar: renderIn(
      language,
      <Sidebar
        place="overview"
        onPlace={noop}
        waiting={3}
        theme="light"
        onTheme={noop}
        version="0.1.0"
      />,
    ),
  }
}

afterEach(() => vi.unstubAllGlobals())

describe.each<Language>(['de', 'en'])('the four places in %s', (language) => {
  it('render with and without data', () => {
    for (const [place, markup] of Object.entries(places(language))) {
      expect(markup.length, place).toBeGreaterThan(80)
    }
  })

  it('show their core message rather than an empty shell', () => {
    const rendered = places(language)
    if (language === 'de') {
      expect(rendered['overview with records']).toContain('Belege warten auf Ihre Freigabe')
      expect(rendered['overview while reading']).toContain('Es wird gelesen: 2 Belege bisher')
      expect(rendered['empty overview']).toContain('Noch wurde nichts eingelesen')
      // Decision 2: a document read by hand is not reviewed on this place.
      expect(rendered['review with a document read by hand']).toContain('Nichts zu prüfen')
      expect(rendered['empty review']).toContain('Nichts zu prüfen')
      expect(rendered['no document kind']).toContain('Noch keine Belegart')
      expect(rendered.sidebar).toContain('Alle Belege bleiben auf diesem Gerät')
    } else {
      expect(rendered['overview with records']).toContain('documents are waiting for your approval')
      expect(rendered['overview while reading']).toContain('Reading: 2 documents so far')
      expect(rendered['empty overview']).toContain('Nothing has been read yet')
      expect(rendered['review with a document read by hand']).toContain('Nothing to review')
      expect(rendered['empty review']).toContain('Nothing to review')
      expect(rendered['no document kind']).toContain('No document kind yet')
      expect(rendered.sidebar).toContain('All documents stay on this device')
    }
  })

  it('counts later arrivals and duplicates per import and offers to compare a duplicate', () => {
    const t = (language === 'de' ? de : en).pilotOverview
    const markup = places(language)['overview with records']
    expect(markup).toContain(t.laterArrivals(1))
    expect(markup).toContain(t.duplicates(1))
    expect(markup).toContain(t.possibleDuplicates(1))
    expect(markup).toContain(t.compare)
    expect(places(language)['overview while reading']).toContain(t.beingRead(1))
  })

  it('shows the way of working as its folder structure and the one folder in Settings (v002 Z8.2, Z9.7)', () => {
    const markup = places(language).settings
    for (const words of ['/scans', (language === 'de' ? de : en).pilotSettings.folderStructure(1), 'Broker program', 'Second']) {
      expect(markup).toContain(words)
    }
    expect(markup).not.toContain('Versicherer, Nummer')
    expect(markup).not.toContain('/scans/Ausgabe')
  })

  it('names the subfolder Ausgabe of the watched folder on the hand-over screen (v002 Z9.7)', () => {
    expect(places(language)['hand-over simulation']).toMatch(/\/scans\/Ausgabe<\/span>/)
  })

  it('never says „Alles läuft“ or shows the green dot while an entry or a hand-over failed (Z2.1)', () => {
    const texts = language === 'de' ? de : en
    const failing = inboxView(
      [entry(1, { state: 'error', problem_key: 'document-corrupt', kind: null, values: [] }), entry(2, { state: 'approved' })],
      true,
      [job(2, 'failed', 'Meyer', 'import-failed: Kunde fehlt')],
    )
    const markup = renderIn(language, overviewOf(failing))
    expect(markup).not.toContain(texts.state.running)
    expect(markup).not.toContain('bg-good shadow')
    expect(markup).toContain(`text-warn">${texts.pilotOverview.withErrors(2)}<`)
    const quiet = renderIn(language, overviewOf(QUIET))
    expect(quiet).toContain(texts.state.running)
    expect(quiet).toContain('bg-good shadow')
  })

  it('names the count of waiting documents once in the main area (Z2.3)', () => {
    const texts = language === 'de' ? de : en
    const waiting = Array.from({ length: 8 }, (_, i) => entry(11 + i))
    const markup = renderIn(language, overviewOf(inboxView([...waiting, entry(21, { state: 'approved' })], true)))
    const text = markup.replace(/<[^>]*>/g, ' ')
    expect(text.match(/(?<![\w-])8(?![\w])/g), text).toHaveLength(1)
    expect(text).toContain(texts.pilotOverview.waitingTitle(8))
    expect(markup).not.toContain('data-actionable')
  })

  it('shows only the last folder name on an import card, the full path as its tooltip (Z2.4)', () => {
    const view = inboxView([entry(1)], true)
    view.imports = [{ ...view.imports[0]!, folder: '/home/clerk/Kunden/Eingang' }]
    const markup = renderIn(language, overviewOf(view))
    expect(markup.replace(/<[^>]*>/g, ' ')).not.toContain('/home/clerk')
    expect(markup).toContain('title="/home/clerk/Kunden/Eingang">Eingang<')
    expect(folderName('C:\\Scans\\Eingang\\')).toBe('Eingang')
  })

  it('shows no section and no link for documents read by hand (Z2.6)', () => {
    const texts = language === 'de' ? de : en
    for (const view of [AFTER, READING, EMPTY]) {
      const markup = renderIn(language, overviewOf(view))
      expect(markup).not.toContain(texts.pilotOverview.manual)
    }
    // Overview takes no session, so a document read by hand reaches neither it nor the sidebar count.
    for (const file of ['src/places/Overview.tsx', 'src/App.tsx']) {
      expect(readFileSync(file, 'utf-8'), file).not.toMatch(/ManualRecords|session\.(reviewCount|records)/)
    }
  })

  it('has exactly one dark button in every state of Overview (Z2.8)', () => {
    const states = {
      'empty start': EMPTY,
      reading: READING,
      waiting: AFTER,
      'one error entry': inboxView(
        [entry(1, { state: 'approved' }), entry(2, { state: 'error', problem_key: 'document-corrupt', kind: null, values: [] })],
        true,
        [job(1, 'done', 'Meyer', 'import-confirmed')],
      ),
      'ready for hand-over': HANDING,
    }
    for (const [state, view] of Object.entries(states)) {
      const markup = renderIn(language, overviewOf(view))
      const darkButtons = markup.match(/<button[^>]*class="[^"]*\bbg-ink(?![-\w])/g)?.length ?? 0
      expect(darkButtons, state).toBe(1)
    }
  })

  it('lists the kinds in Templates and lets each value of a kind be renamed, removed or added', () => {
    const t = (language === 'de' ? de : en).kinds
    const rendered = places(language)
    expect(rendered['document kinds']).toContain('Police')
    const markup = rendered['values of a kind']
    expect(markup).toContain(t.kindTitle('Police'))
    expect(markup).toMatch(/<input[^>]*value="Versicherer"/)
    expect(markup.split(t.goesTo('Broker program')).length - 1).toBe(2)
    expect(markup).toContain(t.onlyShown)
    expect(markup.split(t.remove).length - 1).toBe(3)
    expect(markup).toContain(t.newPlaceholder)
    expect(markup).toContain(t.save)
    const darkButtons = markup.match(/<button[^>]*class="[^"]*\bbg-ink(?![-\w])/g)?.length ?? 0
    expect(darkButtons).toBe(1)
  })

  it('lists only the kinds of the active profile, without a new template or an empty template card', () => {
    const t = (language === 'de' ? de : en).kinds
    const rendered = places(language)
    const list = rendered['document kinds']
    expect(list).toContain('Police')
    expect(list).toContain('Beitragsrechnung')
    expect(list).not.toContain('Schadenmeldung')
    expect(list.indexOf('Police')).toBeLessThan(list.indexOf('Beitragsrechnung'))
    expect(list).toContain(t.values(3))
    for (const markup of [list, rendered['no document kind']]) {
      for (const text of ['Neue Vorlage', 'Noch keine Vorlage', 'New template', 'No template yet']) {
        expect(markup).not.toContain(text)
      }
    }
    expect(rendered['no document kind']).toContain(t.toSettings)
  })

  it('has exactly one dark button on Templates and one kind in every state', () => {
    for (const place of [
      'document kinds',
      'no document kind',
      'values of a kind',
      'kind with an unsaved change on leaving',
      'kind with a refused change',
      'kind saved',
    ] as const) {
      const darkButtons = places(language)[place].match(/<button[^>]*class="[^"]*\bbg-ink(?![-\w])/g)?.length ?? 0
      expect(darkButtons, place).toBe(1)
    }
  })

  it('has exactly one dark button in every state of Settings, the hand-over and the folder screen (Z5.4, Z6.5, v002 Z10.2)', () => {
    for (const place of [
      'settings',
      'settings with a confirmed change',
      'settings with a refused folder',
      'hand-over simulation',
      'hand-over simulation of nothing',
      'folder screen without a folder',
      'folder screen with a folder',
    ] as const) {
      const darkButtons = places(language)[place].match(/<button[^>]*class="[^"]*\bbg-ink(?![-\w])/g)?.length ?? 0
      expect(darkButtons, place).toBe(1)
    }
  })

  it('has exactly one dark button on every screen of the four places (Z7.9)', () => {
    for (const [place, markup] of Object.entries(places(language))) {
      if (place === 'sidebar') continue
      const darkButtons = markup.match(/<button[^>]*class="[^"]*\bbg-ink(?![-\w])/g)?.length ?? 0
      expect(darkButtons, place).toBe(1)
    }
  })

  it('has exactly one dark button in every state of Review', () => {
    const rendered = places(language)
    const states = Object.keys(rendered).filter((place) => /review|duplicate with/.test(place))
    expect(states.length).toBeGreaterThanOrEqual(8)
    for (const place of states) {
      const darkButtons = rendered[place as keyof typeof rendered].match(/<button[^>]*class="[^"]*\bbg-ink(?![-\w])/g)?.length ?? 0
      expect(darkButtons, place).toBe(1)
    }
  })

  it('never heads the other values with „sicher erkannt“ while one of them is missing', () => {
    const t = (language === 'de' ? de : en).inboxReview
    // Insurer sure, premium unclear and asked about, payment mode not found.
    const markup = places(language)['inbox review with an unclear value']
    expect(markup).toContain(t.missing)
    expect(markup).toContain(`>${t.rest}</h2>`)
    expect(markup).not.toMatch(/sicher erkannt|recognised clearly/)
  })

  it('asks for the kind inside the panel and points to no control above', () => {
    const t = (language === 'de' ? de : en).inboxReview
    const markup = places(language)['inbox review without a kind']
    expect(markup).toContain(t.noKindQuestion)
    expect(markup.match(/type="radio"/g)?.length).toBe(KINDS.length)
    expect(markup).not.toContain('<select')
    expect(markup).toMatch(new RegExp(`<button[^>]*bg-ink[^>]*>${t.readWith}`))
    expect(markup).not.toMatch(/\boben\b|\babove\b/)
  })
})

describe('the review of documents read by hand', () => {
  it('is rendered by no place, while its code stays in src/places/Review.tsx', () => {
    const files = readdirSync('src', { recursive: true, encoding: 'utf8' }).filter((f) => f.endsWith('.tsx'))
    const users = files.filter((f) => readFileSync(join('src', f), 'utf8').includes('<SessionReview'))
    expect(users).toEqual([])
    expect(readFileSync('src/places/Review.tsx', 'utf8')).toContain('export function SessionReview(')
  })
})

describe('the import overview', () => {
  const t = de.pilotOverview
  const overview = (view: InboxView, status: Status = STATUS, language: Language = 'de') =>
    renderIn(
      language,
      <Overview
        status={status}
        inbox={view}
        onReview={noop}
        onChooseFolder={noop}
        onHandOver={noop}
        onFeedback={noop}
        onError={noop}
      />,
    )

  it('names the most urgent state on each customer line', () => {
    const at = (id: number, customer: string, patch: Partial<InboxEntry> = {}) =>
      entry(id, { customer, ...patch })
    const markup = overview(
      inboxView(
        [
          at(1, 'Adler', { state: 'approved' }),
          at(2, 'Berg', { state: 'approved' }),
          at(3, 'Clausen', { state: 'approved' }),
          at(4, 'Dorn'),
          at(5, 'Engel', { state: 'new', kind: null, values: [] }),
          at(6, 'Fuchs', { values: [value('insurer', '?', false)] }),
          at(7, 'Groß', { possible_duplicate_of: 4 }),
        ],
        false,
        [job(1, 'failed'), job(2, 'pending'), job(3, 'done')],
      ),
    )
    for (const word of [
      t.states.error,
      t.states.ready,
      t.done,
      t.certain,
      t.states.reading,
      t.unclearValues(1),
      t.states.possible,
    ]) {
      expect(markup).toContain(word)
    }
  })

  it('names approved jobs in the headline when nothing waits', () => {
    const markup = overview(inboxView([entry(1, { state: 'approved' })], true, [job(1, 'pending')]))
    expect(markup).toContain(t.readyTitle)
    expect(markup).toContain(t.readySubtitle(1))
  })

  it('offers every hand-over step while an entry still waits, beside the one dark button', () => {
    const waiting = entry(9, { customer: 'Wagner', folder: '/scans/Wagner' })
    const combinations: [Job[], ('showHandOver' | 'giveFeedback' | 'releaseFailed')[]][] = [
      [[job(1, 'pending')], ['showHandOver']],
      [[job(1, 'handed_over')], ['giveFeedback']],
      [[job(1, 'failed', 'Meyer', 'import-failed: Kunde fehlt')], ['releaseFailed']],
      [[job(1, 'pending'), job(5, 'handed_over', 'Schulz')], ['showHandOver', 'giveFeedback']],
    ]
    for (const [language, texts] of [['de', de], ['en', en]] as const) {
      for (const [jobs, offered] of combinations) {
        const markup = overview(inboxView([...APPROVED, waiting], true, jobs), STATUS, language)
        for (const step of offered) expect(markup).toContain(`>${texts.pilotOverview[step]}</button>`)
        expect(markup).toContain(texts.overview.reviewNow)
        const darkButtons = markup.match(/<button[^>]*class="[^"]*\bbg-ink(?![-\w])/g) ?? []
        expect(darkButtons, `${language} ${offered.join()}`).toHaveLength(1)
      }
    }
  })

  it('offers a step the headline already offers only once', () => {
    const markup = overview(HANDED)
    expect(markup.split(`>${t.giveFeedback}<`).length - 1).toBe(1)
  })

  it('names a written hand-over and a failed import with its reason on the customer line', () => {
    expect(overview(HANDED)).toContain(t.handedOverGroup)
    const markup = overview(REPORTED)
    expect(markup).toContain(t.failedBecause('Kunde fehlt'))
    expect(markup).toContain(t.done)
  })

  it('shows amounts with their currency', () => {
    const premium = { ...value('premium', '156,64'), normalized: 156.64 }
    expect(shownValue(entry(1, { values: [premium] }), 'premium', 'en')).toBe('€156.64')
    expect(shownValue(entry(1, {}), 'missing', 'de')).toBe('')
    const markup = shownValue(entry(1, { values: [premium] }), 'premium', 'de')
    expect(markup).toContain('156,64 €')
  })

  it('says so when the program cannot be reached', () => {
    const markup = overview(QUIET, { ...STATUS, connected: false })
    expect(markup).toContain(de.state.unavailable)
  })

  it('filters by a group of states and by text in any value', () => {
    const e = entry(1, { values: [value('insurer', 'Nordstern')] })
    const none = { period: 'latest', filter: '', search: '' } as const
    expect(matches(e, { ...none, filter: 'waiting' }, 'later')).toBe(true)
    expect(matches(e, { ...none, filter: 'error' }, 'later')).toBe(false)
    expect(matches(e, { ...none, search: ' NORD ' }, 'waiting')).toBe(true)
    expect(matches(e, { ...none, search: 'Süd' }, 'waiting')).toBe(false)
  })

  it('offers no filter by customer name in either language', () => {
    for (const [language, texts] of [['de', de], ['en', en]] as const) {
      const markup = overview(AFTER, STATUS, language)
      expect(markup).not.toContain(`aria-label="${language === 'de' ? 'Kunde' : 'Customer'}"`)
      expect(markup).toContain(`aria-label="${texts.pilotOverview.period}"`)
      expect(markup).toContain(`aria-label="${texts.pilotOverview.state}"`)
    }
    expect(Object.keys(de.pilotOverview)).not.toContain('allCustomers')
    expect(Object.keys(en.pilotOverview)).not.toContain('allCustomers')
  })
})

describe('the read documents on Overview (UI7)', () => {
  const t = de.pilotOverview
  const NOW = new Date(2026, 10, 11, 12)
  const DAY = 86_400_000
  const at = (ms: number) => new Date(ms).toISOString()
  const ui7 = (id: number, patch: Partial<InboxEntry> = {}) => entry(id, patch)
  const overview = (view: InboxView) =>
    renderIn(
      'de',
      <Overview
        status={STATUS}
        inbox={view}
        onReview={noop}
        onChooseFolder={noop}
        onHandOver={noop}
        onFeedback={noop}
        onError={noop}
      />,
    )

  it('narrows by state and period together', () => {
    const old = at(NOW.getTime() - 5 * DAY)
    const view = {
      entries: [
        ui7(1, { state: 'error', problem_key: 'document-corrupt', arrived_at: old }),
        ui7(2, { state: 'error', problem_key: 'document-corrupt', arrived_at: at(NOW.getTime()) }),
        ui7(3, { arrived_at: at(NOW.getTime()) }),
      ],
      imports: [],
    }
    const stateOf = (e: InboxEntry) => (e.state === 'error' ? 'error' : 'waiting')
    const errors = { period: 'days3', filter: 'error', search: '' } as const
    expect(filtered(view, errors, stateOf, NOW).map((e) => e.id)).toEqual([2])
    expect(filtered(view, { ...errors, period: 'week' }, stateOf, NOW).map((e) => e.id)).toEqual([1, 2])
    expect(filtered(view, { ...errors, filter: '' }, stateOf, NOW).map((e) => e.id)).toEqual([2, 3])
  })

  it('offers exactly five periods, the most recent import first and by default', () => {
    expect(PERIODS).toEqual(['latest', 'days3', 'week', 'month', 'months3'])
    const markup = overview(AFTER)
    const options = [...markup.matchAll(/<option[^>]*value="(latest|days3|week|month|months3)"[^>]*>/g)]
    expect(options.map((o) => o[1])).toEqual([...PERIODS])
    expect(options[0]?.[0]).toContain('selected')
    for (const p of PERIODS) expect(markup).toContain(t.periods[p])
  })

  it('holds an entry exactly at the start of each period and drops one a millisecond older', () => {
    // Calendar days and months on the local clock, so a change of summer time keeps the hour.
    const local = (month: number, day: number) => new Date(2026, month, day, 12).getTime()
    const starts = {
      days3: local(10, 8),
      week: local(10, 4),
      month: local(9, 11),
      months3: local(7, 11),
    } as const
    for (const [period, start] of Object.entries(starts) as [keyof typeof starts, number][]) {
      expect(periodStart(period, NOW).getTime()).toBe(start)
      expect(inPeriod(ui7(1, { arrived_at: at(start) }), period, 1, NOW)).toBe(true)
      expect(inPeriod(ui7(1, { arrived_at: at(start - 1) }), period, 1, NOW)).toBe(false)
    }
  })

  it('holds only the most recent import under „zuletzt eingelesen“, however recent the other is', () => {
    const fresh = at(NOW.getTime())
    expect(inPeriod(ui7(1, { import_id: 2, arrived_at: at(0) }), 'latest', 2, NOW)).toBe(true)
    expect(inPeriod(ui7(1, { import_id: 1, arrived_at: fresh }), 'latest', 2, NOW)).toBe(false)
  })

  it('shows only the most recent import by default', () => {
    const view = {
      ...inboxView([ui7(1, { customer: 'Altkunde' }), ui7(2, { import_id: 2, customer: 'Neukunde' })], true),
      imports: [
        { id: 1, folder: '/old', started_at: '2026-11-01T09:00:00Z', finished_at: '2026-11-01T09:05:00Z' },
        { id: 2, folder: '/new', started_at: '2026-11-11T09:00:00Z', finished_at: '2026-11-11T09:05:00Z' },
      ],
    }
    const markup = overview(view)
    expect(markup).toContain('Neukunde')
    expect(markup).not.toContain('Altkunde')
  })

  it('orders documents by time of reading, the latest first', () => {
    const docs = [10, 30, 20].map((h) => ui7(h, { arrived_at: at(NOW.getTime() - h * 3_600_000) }))
    const ids = shownDocuments(docs, () => 'waiting', true).map((e) => e.id)
    expect(ids).toEqual([10, 20, 30])
  })

  it('shows three documents and a link to all, and never hides one waiting for a person behind a settled one', () => {
    const hour = (h: number) => at(NOW.getTime() - h * 3_600_000)
    const docs = [
      ui7(1, { state: 'approved', arrived_at: hour(1) }),
      ui7(2, { state: 'approved', arrived_at: hour(2) }),
      ui7(3, { state: 'approved', arrived_at: hour(3) }),
      ui7(4, { values: [value('insurer', '?', false)], arrived_at: hour(4) }),
    ]
    const stateOf = (e: InboxEntry) => (e.state === 'approved' ? 'ready' : 'unclear')
    expect(shownDocuments(docs, stateOf, false).map((e) => e.id)).toEqual([1, 2, 4])
    expect(shownDocuments(docs, stateOf, true)).toHaveLength(4)

    const markup = overview(inboxView(docs, true))
    expect(markup).toContain(t.showAll(4))
    expect(markup).toContain('scan-4.pdf')
    expect(markup).not.toContain('scan-3.pdf')
    expect(overview(inboxView(docs.slice(0, 3), true))).not.toContain(t.showAll(3))
  })

  it('renders the customer name bold', () => {
    expect(overview(AFTER)).toMatch(/font-semibold"><svg[^]*?<span class="truncate">Meyer<\/span>/)
  })
})

describe('the headline of Overview', () => {
  const t = de.pilotOverview
  const quiet: Stage = {
    starts: false, reading: false, read: 2, waiting: 0, pending: 0, errors: 0,
    handedOver: 0, failed: 0, done: 0, target: 'Broker program',
  }

  it('offers one next step, a report before a release before a hand-over', () => {
    expect(headline(t, { ...quiet, pending: 1, failed: 1, handedOver: 1 })[2]).toBe('feedback')
    expect(headline(t, { ...quiet, pending: 1, failed: 1, done: 2 })).toEqual([
      t.resultTitle(2, 1), t.resultSubtitle, 'release',
    ])
    expect(headline(t, { ...quiet, pending: 1 })[2]).toBe('handOver')
    expect(headline(t, quiet)[2]).toBeNull()
  })

  it('offers review before any hand-over step, also while reading, and nothing else while reading', () => {
    expect(headline(t, { ...quiet, waiting: 1, handedOver: 1 })[2]).toBe('review')
    expect(headline(t, { ...quiet, reading: true, waiting: 1 })[2]).toBe('review')
    expect(headline(t, { ...quiet, reading: true, pending: 1 })[2]).toBeNull()
  })

  it('leads to the errors only when nothing else is to do', () => {
    expect(headline(t, { ...quiet, errors: 1 })).toEqual([t.errorsTitle, t.errorsSubtitle, 'errors'])
    expect(headline(t, { ...quiet, errors: 1, pending: 1 })[2]).toBe('handOver')
  })

  it('allows each hand-over step by its own count, whatever else waits', () => {
    expect(handOverSteps({ pending: 0, handedOver: 0, failed: 0 })).toEqual([])
    expect(handOverSteps({ pending: 2, handedOver: 0, failed: 0 })).toEqual(['handOver'])
    expect(handOverSteps({ pending: 1, handedOver: 1, failed: 1 })).toEqual(['feedback', 'release', 'handOver'])
  })

  it('names the target of the profile when a report is open', () => {
    expect(headline(t, { ...quiet, handedOver: 2 })[0]).toBe(t.handedOverTitle(2, 'Broker program'))
  })
})

describe('the hand-over', () => {
  const t = de.handOver
  const file = job(1, 'pending').file

  it('names every value the format refuses in words, never by its key', () => {
    const items = [
      { item: 'insurer' },
      { item: 'policy_number' },
      { item: 'insurer_number', value: 'Nordlicht AG' },
      { item: 'line_of_business_code', value: 'Hausrat' },
      { item: 'payment_mode_code', value: 'quartalsweise' },
      { item: 'premium_per_payment_period' },
      { item: 'value_fits_field', field: 'policy_number' },
      { item: 'value_fits_field', field: 'unknown' },
      { item: 'one_contract_per_policy_number' },
      { item: 'same_policyholder' },
      { item: 'kind_not_handed_over', value: 'policy' },
      { item: 'something_new' },
    ]
    const texts = items.map((item) => itemText(item, file.kind, wordsOf(HANDING), t))
    expect(texts).toEqual([
      t.missing('Versicherer'),
      t.missing('Nummer'),
      t.unknownInsurer('Nordlicht AG', 'Broker program'),
      t.unknownLine('Hausrat', 'Broker program'),
      t.unknownPaymentMode('quartalsweise', 'Broker program'),
      t.annualOnly,
      t.doesNotFit('Nummer'),
      t.doesNotFit(t.aValue),
      t.twoPolicies,
      t.twoHolders,
      t.kindNotHandedOver('Police', 'Broker program'),
      t.cannotWrite,
    ])
    for (const text of texts) expect(text).not.toMatch(/\b[a-z]+_[a-z_]+\b/)
  })

  it('names why nothing of a customer can be written, also for an unknown reason', () => {
    expect(problemText('hand-over-settings-invalid: hand_over.broker_number', t)).toBe(
      t.problems['hand-over-settings-invalid'],
    )
    expect(problemText('hand-over-folder-missing', t)).toBe(t.problems['hand-over-folder-missing'])
    expect(problemText('handover-write-failed', t)).toBe(t.cannotWrite)
  })

  it('shows a refused value before the run and keeps the run possible for the others', () => {
    const markup = renderIn('de', <HandOverView inbox={HANDING} previews={PREVIEWS} writing={false} onBack={noop} onWrite={noop} />)
    expect(markup).toContain(t.unknownInsurer('Nordlicht AG', 'Broker program'))
    expect(markup).toContain(t.contractsFrom(1, 1))
    expect(markup).toContain(t.notYet)
    expect(markup).toContain('156,64 €')
    expect(markup).toContain(`Police, Seite 1 · ${t.changed}`)
    expect(markup).not.toMatch(/<button[^>]*disabled=""[^>]*>Übergabe schreiben/)
  })

  it('writes nothing when no customer has a contract that can go', () => {
    const refused = [PREVIEWS[1]!, { ...PREVIEWS[0]!, problem: 'hand-over-table-invalid' }]
    const markup = renderIn('de', <HandOverView inbox={HANDING} previews={refused} writing={false} onBack={noop} onWrite={noop} />)
    expect(markup).toContain(t.problems['hand-over-table-invalid'])
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>Übergabe schreiben/)
  })

  it('reads the reason of a failed import and of nothing else', () => {
    expect(importFailure(job(1, 'failed', 'Meyer', 'import-failed: Kunde fehlt'))).toBe('Kunde fehlt')
    expect(importFailure(job(1, 'failed', 'Meyer', 'target-without-writer'))).toBeNull()
    expect(importFailure(job(1, 'pending', 'Meyer', 'import-failed: alt'))).toBeNull()
    expect(importFailure(undefined)).toBeNull()
  })

  it('saves a report only when something is answered and every failure has a reason', () => {
    expect(canSave({})).toBe(false)
    expect(canSave({ Meyer: { imported: true, reason: '' } })).toBe(true)
    expect(canSave({ Meyer: { imported: false, reason: '  ' } })).toBe(false)
    expect(canSave({ Meyer: { imported: false, reason: 'Kunde fehlt' } })).toBe(true)
  })

  it('asks per customer and opens the reason for a failed import', () => {
    const markup = places('de')['feedback with a failed import']
    expect(markup).toContain(t.feedbackTitle('Broker program'))
    expect(markup).toContain(t.reasonPlaceholder)
    expect(markup).toContain('Schulz')
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>Rückmeldung speichern/)
  })
})

const FORBIDDEN_DE: Array<[string, RegExp]> = [
  ['Konfidenz', /Konfidenz/i],
  ['Locator', /Locator/i],
  ['Provenance', /Provenance/i],
  ['Bounding-Box', /Bounding/i],
  ['OCR', /\bOCR\b/],
  ['Dokumenttyp', /Dokumenttyp/i],
  ['Vorlage statt Belegart', /Vorlage/i],
  ['Profil', /Profil/i],
  ['Template', /Template/i],
  ['Feld statt Angabe', /\bFeld(er)?\b/],
  ['Dokument statt Beleg', /\bDokument(e|s)?\b/],
  ['Extraktion', /Extrakt/i],
  ['Regex', /Regex/i],
  ['Modellname', /GLiNER|Granite|Tesseract|Q4_K_M|rapidfuzz/i],
  ['Schlüssel in snake_case', /\b[a-zäöü]+_[a-zäöü]+\b/],
]

const FORBIDDEN_EN: Array<[string, RegExp]> = [
  ['confidence', /\bconfidence\b/i],
  ['locator', /\blocator\b/i],
  ['provenance', /\bprovenance\b/i],
  ['bounding box', /\bbounding[ -]box\b/i],
  ['OCR', /\bOCR\b/],
  ['document type', /\bdocument type\b/i],
  ['template instead of document kind', /\btemplates?\b/i],
  ['profile', /\bprofiles?\b/i],
  ['extraction', /\bextraction\b/i],
  ['regex', /\bregex\b/i],
  ['field', /\bfields?\b/i],
  ['threshold', /\bthreshold\b/i],
  ['model name', /GLiNER|Granite|Tesseract|Q4_K_M|rapidfuzz/i],
  ['snake_case key', /\b[a-z]+_[a-z]+\b/],
]

describe.each<Language>(['de', 'en'])('review of an entry from the watched folder in %s', (language) => {
  const rendered = places(language)
  const de = language === 'de'

  it('asks about the value an approval waits for and shows the kind it was read as', () => {
    const markup = rendered['inbox review with an unclear value']
    expect(markup).toContain(de ? 'Eine Angabe ist nicht eindeutig' : 'One detail is unclear')
    expect(markup).toContain(de ? 'Stimmt die Angabe „Premium“?' : 'Is “Premium” right?')
    expect(markup).toContain('156.64')
    expect(markup).toMatch(/<option value="policy"[^>]*selected="">Policy<\/option>/)
    expect(markup).toContain(de ? 'Kunde Brandt' : 'Customer Brandt')
  })

  it('offers the approval once every value is settled and marks what a person changed in bold', () => {
    const markup = rendered['inbox review ready for approval']
    expect(markup).toContain(de ? 'Beleg freigeben' : 'Approve document')
    expect(markup).toMatch(/font-bold[^"]*">160\.00</)
    expect(markup).not.toMatch(/font-bold[^"]*">Nordlicht AG</)
    expect(markup).toContain(de ? 'Fett: von Ihnen geändert.' : 'Bold: changed by you.')
  })

  it('lets a possible duplicate be approved only after the same-or-new decision', () => {
    const markup = rendered['inbox review of a possible duplicate']
    expect(markup).toContain(de ? 'Ist das derselbe Beleg?' : 'Is this the same document?')
    expect(markup).toContain(de ? 'Derselbe Beleg' : 'The same document')
    expect(markup).toContain(de ? 'Ein neuer Beleg' : 'A new document')
    expect(markup).not.toContain(de ? 'Beleg freigeben' : 'Approve document')
  })

  it('shows a duplicate with the same content beside the first document with nothing to decide', () => {
    const markup = rendered['duplicate with the same content']
    expect(markup).toContain(de ? 'Derselbe Inhalt' : 'The same content')
    expect(markup).toContain('policy.pdf')
    expect(markup).toContain('policy copy.pdf')
    expect(markup).not.toContain(de ? 'Ein neuer Beleg' : 'A new document')
  })

  it('asks for a value that was not found as an input, and lets an optional one be marked as missing', () => {
    const missing = rendered['inbox review of a value not found']
    expect(missing).toMatch(/<input[^>]*aria-label="Premium"/)
    expect(missing).not.toContain(de ? 'Diese Angabe fehlt im Beleg' : 'This detail is missing from the document')
    const optional = rendered['inbox review of an unclear optional value']
    expect(optional).toContain(de ? 'Stimmt die Angabe „Payment mode“?' : 'Is “Payment mode” right?')
    expect(optional).not.toMatch(/<input[^>]*aria-label="Payment mode"/)
    expect(optional).toContain(de ? 'Diese Angabe fehlt im Beleg' : 'This detail is missing from the document')
  })

  it('asks for the kind when none was recognised', () => {
    const markup = rendered['inbox review without a kind']
    expect(markup).toContain(de ? 'Als was soll dieser Beleg gelesen werden?' : 'What should this document be read as?')
    expect(markup).not.toContain(de ? 'Beleg freigeben' : 'Approve document')
  })

  it('has exactly one dark button where a step is obvious', () => {
    for (const place of [
      'inbox review with an unclear value',
      'inbox review ready for approval',
      'inbox review of a possible duplicate',
      'empty review',
    ] as const) {
      const darkButtons = rendered[place].match(/<button[^>]*class="[^"]*\bbg-ink(?![-\w])/g)?.length ?? 0
      expect(darkButtons, place).toBe(1)
    }
  })
})

/** The paragraph right under each heading, without markup; text inside a card below a section heading is no subtitle. */
function subtitles(markup: string): string[] {
  return [...markup.matchAll(/<\/h[12]><p[^>]*>(.*?)<\/p>/g)].map((m) => m[1]!.replace(/<[^>]+>/g, ''))
}

/** Sentence ends: a full stop, question or exclamation mark before a space or the end. */
const sentences = (text: string) => text.match(/[.!?](?=\s|$)/g)?.length ?? 0

describe.each<Language>(['de', 'en'])('subtitles in %s (Z7.4)', (language) => {
  // The duplicate decision, the report and the retention period need their explanation.
  const LONGER = ['inbox review of a possible duplicate', 'feedback with a failed import']

  it('are at most one sentence under every heading of the four places', () => {
    const longer = Object.entries(places(language))
      .filter(([place]) => !LONGER.includes(place))
      .flatMap(([place, markup]) => subtitles(markup).filter((text) => sentences(text) > 1).map((text) => `${place}: ${text}`))
    expect(longer).toEqual([])
  })

  it('finds a subtitle of two sentences', () => {
    expect(sentences(subtitles('<h1>A</h1><p>One. Two.</p>')[0]!)).toBe(2)
  })
})

describe('the interface vocabulary', () => {
  it('rejects the words the owner replaced: „Vorlage“, „Profil“, template and profile', () => {
    const de = new Map(FORBIDDEN_DE)
    const en = new Map(FORBIDDEN_EN)
    expect(de.get('Vorlage statt Belegart')!.test('Neue Vorlage')).toBe(true)
    expect(de.get('Profil')!.test('Profil-Datei')).toBe(true)
    expect(en.get('template instead of document kind')!.test('New template')).toBe(true)
    expect(en.get('profile')!.test('Profile file')).toBe(true)
  })

  it('fails a rendered place that calls a kind „Vorlage“ or names a „Profil“', () => {
    const markup = renderIn(
      'de',
      <Templates kinds={[{ ...KIND, title: 'Vorlage Police' }]} profile={{ ...TWO_KINDS, title: 'Profil Makler' }}
        onOpenKind={noop} onSettings={noop} onOverview={noop} />,
    )
    const found = FORBIDDEN_DE.filter(([, pattern]) => pattern.test(readable(markup))).map(([term]) => term)
    expect(found).toEqual(expect.arrayContaining(['Vorlage statt Belegart']))
  })

  it('keeps engine-room terms off German user screens', () => {
    for (const [place, markup] of Object.entries(places('de'))) {
      const text = readable(markup)
      for (const [term, pattern] of FORBIDDEN_DE) {
        expect(pattern.test(text), `“${term}” appears on “${place}”`).toBe(false)
      }
    }
  })

  it('keeps engine-room terms and German copy off English user screens', () => {
    for (const [place, markup] of Object.entries(places('en'))) {
      const text = readable(markup)
      for (const [term, pattern] of FORBIDDEN_EN) {
        expect(pattern.test(text), `“${term}” appears on “${place}”`).toBe(false)
      }
      expect(/[äöüß]/i.test(text), `German copy appears on “${place}”`).toBe(false)
    }
  })
})

describe('language persistence', () => {
  it('falls back to German for an unknown stored value', () => {
    vi.stubGlobal('localStorage', storage('fr'))
    expect(storedLanguage()).toBe('de')
  })

  it('falls back to German when storage is unavailable', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('blocked') } })
    expect(storedLanguage()).toBe('de')
  })

  it('stores the language and updates the document language', () => {
    const localStorage = storage(null)
    const documentElement = { lang: 'de' }
    vi.stubGlobal('localStorage', localStorage)
    vi.stubGlobal('document', { documentElement })

    applyLanguage('en')

    expect(documentElement.lang).toBe('en')
    expect(localStorage.setItem).toHaveBeenCalledWith('substrakt.language', 'en')
  })
})

describe('comparing a duplicate from Overview', () => {
  const later = inboxEntry({ id: 3 })
  const possible = inboxEntry({ id: 8, possible_duplicate_of: 7, duplicate_decision: null })
  const entries = [SETTLED, later, possible, SAME_BYTES]
  const opened = (entryId?: number) => {
    const view = reviewOf(entryId)
    return pick(entries, 'entryId' in view ? view.entryId : null, [])
  }

  it('opens the possible duplicate the link names, with the first document beside it', () => {
    expect(opened(8).entry).toBe(possible)
    expect(opened(8).first).toBe(SETTLED)
  })

  it('opens a duplicate with the same bytes beside the first document', () => {
    expect(opened(9).entry).toBe(SAME_BYTES)
    expect(opened(9).first).toBe(SETTLED)
  })

  it('opens the first waiting entry without a link or when the named one no longer waits', () => {
    expect(opened().entry).toBe(SETTLED)
    expect(opened(8).waiting).toEqual([SETTLED, later, possible])
    expect(pick(entries, 8, [8]).entry).toBe(SETTLED)
    expect(pick([inboxEntry({ id: 8, state: 'approved' }), later], 8, []).entry).toBe(later)
  })
})

describe('the error banner of the four places', () => {
  const CLASS_NAME = /^[A-Z]\w*(Error|Exception)\b/

  it('never starts a text with the name of an error class', () => {
    const errors = [
      new SubstraktError('unknown-document', 'Der Beleg ist nicht mehr geöffnet.'),
      new TypeError('Failed to fetch'),
      new Error('Broken'),
      'plain text',
    ]
    for (const texts of [de, en]) {
      for (const error of errors) {
        const shown = shownError(error, texts.errors.title)
        expect(errorText(texts, shown.key, shown.fallback)).not.toMatch(CLASS_NAME)
        expect(shown.detail ?? '').not.toMatch(CLASS_NAME)
      }
    }
  })

  it('gets errors as they are, not turned into text that starts with their class', () => {
    // String(error) of a SubstraktError is „SubstraktError: …“, the text the owner saw in the viewer.
    const files = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
        e.isDirectory() ? files(join(dir, e.name)) : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : [])
    const offenders = files('src').filter((f) => /onError\(\s*String\(/.test(readFileSync(f, 'utf8')))
    expect(offenders).toEqual([])
  })
})

/** Every module src/main.tsx reaches through its static imports. */
function reachable(): Set<string> {
  const seen = new Set<string>()
  const walk = (file: string) => {
    if (seen.has(file)) return
    seen.add(file)
    const source = readFileSync(file, 'utf-8')
    for (const [, spec] of source.matchAll(/(?:import|export)[^'"]*?from\s+'(\.[^']+)'/g)) {
      const base = join(file, '..', spec!)
      const found = ['', '.tsx', '.ts', '/index.ts', '/index.tsx'].map((end) => base + end)
        .find((candidate) => { try { return readFileSync(candidate) && true } catch { return false } })
      if (found) walk(found)
    }
  }
  walk('src/main.tsx')
  return seen
}

describe('a document row on Overview (Z2.2)', () => {
  const rowsOf = (markup: string) => markup.match(/<button[^>]*class="grid w-full[^"]*border-t[^>]*>[^]*?<\/button>/g) ?? []

  it('opens a waiting entry in Review and every other entry read-only below its row', () => {
    expect(opensReview(entry(1))).toBe(true)
    expect(opensReview(entry(2, { values: [value('insurer', '?', false)] }))).toBe(true)
    expect(opensReview(entry(3, { state: 'error' }))).toBe(false)
    expect(opensReview(entry(4, { state: 'approved' }))).toBe(false)
  })

  it('makes the whole row one button, with the file name inside it', () => {
    const rows = rowsOf(renderIn('de', overviewOf(AFTER)))
    expect(rows.length).toBeGreaterThanOrEqual(6)
    for (const name of ['scan-1.pdf', 'scan-2.pdf', 'scan-6.pdf']) {
      expect(rows.some((r) => r.includes(`>${name}<`)), name).toBe(true)
    }
    // A row closed below itself says so; one that opens Review has nothing to expand.
    expect(rows.find((r) => r.includes('>scan-6.pdf<'))).toContain('aria-expanded="false"')
    expect(rows.find((r) => r.includes('>scan-2.pdf<'))).not.toContain('aria-expanded')
  })

  it('shows the labelled values of an approved entry and the reason of an error, and nothing to change', () => {
    const labelOf = (_: string | null, name: string) => (name === 'insurer' ? 'Versicherer' : null)
    const approved = renderIn('de', <RowDetails entry={entry(1, { state: 'approved' })} job={job(1, 'failed', 'Meyer', 'import-failed: Kunde fehlt')} labelOf={labelOf} />)
    expect(approved).toContain('Versicherer')
    expect(approved).toContain('Nordstern')
    expect(approved).toContain('Kunde fehlt')
    expect(approved).not.toContain('P-1001')
    const error = renderIn('en', <RowDetails entry={entry(2, { state: 'error', problem_key: 'document-corrupt', values: [] })} job={undefined} labelOf={labelOf} />)
    expect(error).toContain(errorText(en, 'document-corrupt', ''))
    const notWritten = renderIn('de', <RowDetails entry={entry(3, { state: 'approved' })} job={job(3, 'failed', 'Meyer', 'nobody-knows')} labelOf={labelOf} />)
    expect(notWritten).toContain(problemText('nobody-knows', de.handOver))
    for (const markup of [approved, error]) expect(markup).not.toMatch(/<(button|input|select)/)
  })
})

describe('the hidden path for documents read by hand', () => {
  it('is reached by no place, while its code stays in the repository', () => {
    const modules = reachable()
    expect(modules.has('src/places/Templates.tsx')).toBe(true)
    const hidden = ['src/places/Assistant.tsx', 'src/places/TemplateView.tsx', 'src/results/save.ts',
      ...readdirSync('src/places/assistant').map((f) => `src/places/assistant/${f}`)]
    for (const file of hidden) {
      expect(readFileSync(file, 'utf-8').length, file).toBeGreaterThan(0)
      expect(modules.has(file), file).toBe(false)
    }
    // Without a caller of session.add no document read by hand exists, so its review screen stays empty.
    for (const file of modules) {
      expect(readFileSync(file, 'utf-8'), file).not.toMatch(/session\.add\(/)
    }
  })
})

const DARK_BUTTON = /<button[^>]*class="[^"]*\bbg-ink(?![-\w])[^"]*"[^>]*>/

describe('starting to read a folder (M6)', () => {
  const t = de.readFolder

  afterEach(() => vi.restoreAllMocks())

  it('opens from „Ordner einlesen“ as a path while the sidebar keeps Overview (Z6.1)', () => {
    expect(sidebarPlace({ place: 'readFolder' })).toBe('overview')
    expect(renderIn('de', overviewOf(EMPTY))).toContain(`>${de.pilotOverview.chooseFolder}</button>`)
    expect(folderScreenIn('de', null)).toContain(`>${t.title}</h1>`)
  })

  it('names the chosen folder, describes the way of working and enables the start only after a choice (Z6.2)', () => {
    const before = folderScreenIn('de', null)
    expect(before.match(DARK_BUTTON)?.[0]).toContain('disabled=""')
    expect(before).toContain(t.noFolder)
    expect(before).toContain(
      'Liest Police. Der Name des Unterordners ist der Kunde. Freigegebenes geht an Broker program.',
    )
    const after = folderScreenIn('de', '/home/sachbearbeitung/Scans/Neukunden')
    expect(after.match(DARK_BUTTON)?.[0]).not.toContain('disabled=""')
    expect(after).toContain('>Neukunden</p>')
    expect(after).toContain(t.chooseOther)
    expect(folderName('C:\\Scans\\Neukunden\\')).toBe('Neukunden')
  })

  it('says how the customer is found for every folder level of the way of working', () => {
    const at = (level: number | null) => wayInWords(t, { ...PROFILE, customer_folder_level: level })[1]
    expect(at(null)).toBe(t.customerNone)
    expect(at(1)).toBe(t.customerFirst)
    expect(at(2)).toBe(t.customerLevel(2))
  })
})

describe('Settings takes effect in one way (M5)', () => {
  afterEach(() => vi.restoreAllMocks())

  it('stores folders, way of working and retention at once through the same call, and has no save button (Z5.1)', async () => {
    const choose = vi.spyOn(api, 'chooseInboxSettings').mockResolvedValue(READING.settings!)
    const stored = vi.fn()
    expect(await changeLine('folder', '/scans/Neu', stored, noop)).toBe(true)
    expect(await changeLine('profile', 'second', stored, noop)).toBe(true)
    expect(await changeLine('retention', 30, stored, noop)).toBe(true)
    expect(choose.mock.calls).toEqual([
      [{ folder: '/scans/Neu' }],
      [{ profile: 'second' }],
      [{ retentionDays: 30 }],
    ])
    expect(stored).toHaveBeenCalledTimes(3)
    for (const language of ['de', 'en'] as const) {
      expect(places(language).settings).not.toMatch(/speichern|>Save/i)
    }
  })

  it('confirms a change beside its line as a status message under a title without subtitle (Z5.2, v002 Z8.1)', () => {
    for (const line of ['profile', 'folder', 'retention'] as const) {
      const markup = settingsIn('de', line)
      const confirmations = markup.match(/<span role="status"[^>]*>Gespeichert\.<\/span>/g) ?? []
      expect(confirmations, line).toHaveLength(1)
    }
    for (const language of ['de', 'en'] as const) {
      expect(settingsIn(language, null)).toMatch(/<\/h1><\/div>/)
    }
    expect(settingsIn('de', 'retention')).toMatch(
      /role="status"[^>]*>Gespeichert\.<\/span><select aria-label="Erledigte Einträge löschen nach"/,
    )
    expect(settingsIn('de', 'profile')).toMatch(/<\/select><span role="status"[^>]*>Gespeichert\.<\/span>/)
  })
})
