// @vitest-environment happy-dom
/**
 * The same two keys on every place: Enter
 * takes the screen's one dark step, Escape goes back to Overview or, from a
 * kind, to the list of kinds. Enter takes no final step: it never approves and
 * never decides that a document is the same as one read before (R12).
 */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The screens import the viewer, and PDF.js reads `DOMMatrix` while it loads.
vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: { workerSrc: '' } }))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '' }))
// The folder dialog answers with a chosen folder.
vi.mock('@tauri-apps/plugin-dialog', () => ({ open: async () => '/scans/Neukunden' }))
// Review asks for its entries and a kind is saved through the client; nothing waits here.
vi.mock('../../src/api/client', async (original) => ({
  ...(await original<typeof import('../../src/api/client')>()),
  api: {
    inboxEntries: async () => [],
    inboxSettings: async () => null,
    chooseInboxSettings: async (choice: { folder?: string }) => ({ folder: choice.folder ?? null }),
    changeKindValues: async (name: string, values: { label: string }[]) => ({ name, title: 'Police', values }),
  },
}))

import type { ExtractionResult, HandOverPreview, InboxEntry, Job, KindValues, ProfileKind } from '../../src/api/types'
import { LanguageProvider } from '../../src/i18n'
import { de } from '../../src/i18n/de'
import { FeedbackView, HandOverView } from '../../src/places/HandOver'
import { InboxReview } from '../../src/places/InboxReview'
import { KindView } from '../../src/places/KindView'
import { Overview, type InboxView } from '../../src/places/Overview'
import { ReadFolder } from '../../src/places/ReadFolder'
import { Review } from '../../src/places/Review'
import { Settings } from '../../src/places/Settings'
import { Templates } from '../../src/places/Templates'
import type { Session } from '../../src/state/session'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const KINDS: ProfileKind[] = [
  {
    name: 'policy',
    title: 'Police',
    values: [
      { name: 'insurer', label: 'Versicherer', question: '', required: true, json_type: 'string' },
      { name: 'premium', label: 'Beitrag', question: '', required: true, json_type: 'string' },
    ],
  },
]

function value(field: string, text: string, grounded: boolean): ExtractionResult {
  return {
    field,
    value: text,
    normalized: null,
    confidence: grounded ? 0.98 : 0.6,
    source: 'extractor',
    locator: { kind: 'pdf_rect', page: 0, x0: 50, y0: 600, x1: 170, y1: 614 },
    matched_text: text,
    grounded,
    note: '',
  }
}

function entry(id: number, patch: Partial<InboxEntry> = {}): InboxEntry {
  return {
    id,
    import_id: 1,
    state: 'waiting',
    file_path: `/scans/Brandt/scan-${id}.pdf`,
    folder: '/scans/Brandt',
    file_name: `scan-${id}.pdf`,
    sha256: String(id).padStart(64, '0'),
    customer: 'Brandt',
    profile: 'broker',
    kind: 'policy',
    page_count: 1,
    values: [value('insurer', 'Nordlicht AG', true), value('premium', '156.64', false)],
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

function job(entryId: number, state: Job['state'], customer = 'Brandt'): Job {
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
      values: { insurer: { text: 'Nordlicht AG', normalized: 'Nordlicht AG' } },
    },
    handover_path: null,
    transitions: [{ from_state: null, to_state: state, reason: 'approved', at: '2026-11-11T09:30:00Z', account: null }],
  }
}

function view(entries: InboxEntry[], jobs: Job[] = []): InboxView {
  return {
    settings: {
      folder: '/scans',
      handover_folder: '/scans/Ausgabe',
      profile: 'broker',
      profiles: [{ name: 'broker', title: 'Maklerprogramm' }],
      watching: true,
      retention_days: 90,
    },
    entries,
    imports: [{ id: 1, folder: '/scans', started_at: '2026-11-11T09:00:00Z', finished_at: '2026-11-11T09:05:00Z' }],
    jobs,
    profile: null,
  }
}

const KIND: KindValues = { name: 'policy', title: 'Police', values: [{ name: 'insurer', label: 'Versicherer' }] }
const PREVIEWS: HandOverPreview[] = [{ customer: 'Brandt', contracts: [['job-1']], waiting: {}, problem: null }]

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

async function show(node: ReactNode) {
  await act(async () => {
    root.render(<LanguageProvider>{node}</LanguageProvider>)
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

/** Presses a key on the focused element, or on the page when nothing has focus. */
async function press(key: 'Enter' | 'Escape', on: Element = document.activeElement ?? document.body) {
  await act(async () => {
    on.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

/** A focused button acts on Enter by itself; the browser turns the key into a click. */
async function enterOn(button: HTMLButtonElement) {
  button.focus()
  await press('Enter', button)
  await act(async () => button.click())
}

const button = (text: string) =>
  [...host.querySelectorAll('button')].find((b) => b.textContent?.trim().startsWith(text)) ?? null

function review(patch: Partial<Parameters<typeof InboxReview>[0]> = {}) {
  const props = {
    onCorrect: vi.fn(async () => undefined),
    onDecide: vi.fn(async () => undefined),
    onApprove: vi.fn(async () => undefined),
    onBack: vi.fn(),
  }
  const node = (
    <InboxReview entry={entry(7)} position={{ n: 1, total: 1 }} kinds={KINDS} document={null} first={null}
      onLater={() => undefined} onError={(error) => { throw error }} {...props} {...patch} />
  )
  return { node, ...props }
}

describe('Escape goes back (Z7.1)', () => {
  it('leaves the question in Review for Overview', async () => {
    const { node, onBack } = review()
    await show(node)
    await press('Escape')
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('first leaves a change in Review, then the screen', async () => {
    const { node, onBack } = review()
    await show(node)
    await act(async () => button(de.review.change)!.click())
    expect(host.querySelector('input[type=text]')).not.toBeNull()
    // The change screen is rendered only here, so the owner's words are checked on it here (Z7.5).
    expect(host.textContent).toContain(de.review.appliesHere)
    expect(host.textContent).not.toMatch(/Vorlage|Profil/)
    await press('Escape')
    expect(host.querySelector('input[type=text]')).toBeNull()
    expect(onBack).not.toHaveBeenCalled()
    await press('Escape')
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('leaves the decision on a duplicate for Overview', async () => {
    const { node, onBack } = review({ entry: entry(8, { possible_duplicate_of: 7 }), first: { entry: entry(7), document: null } })
    await show(node)
    await press('Escape')
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('leaves an empty Review for Overview', async () => {
    const onFinish = vi.fn()
    await show(<Review session={{} as Session} onError={(error) => { throw error }} onFinish={onFinish} />)
    expect(host.textContent).toContain(de.review.empty)
    await press('Escape')
    expect(onFinish).toHaveBeenCalledOnce()
  })

  it('leaves the simulation and the report for Overview', async () => {
    const onBack = vi.fn()
    const inbox = view([entry(1, { state: 'approved' })], [job(1, 'pending')])
    await show(<HandOverView inbox={inbox} previews={PREVIEWS} writing={false} onBack={onBack} onWrite={() => undefined} />)
    await press('Escape')
    await show(<FeedbackView inbox={inbox} answers={{}} saving={false} onAnswer={() => undefined} onBack={onBack} onSave={() => undefined} />)
    await press('Escape')
    expect(onBack).toHaveBeenCalledTimes(2)
  })

  it('leaves the folder screen for Overview without storing anything', async () => {
    const onBack = vi.fn()
    const onStarted = vi.fn()
    await show(<ReadFolder profile={null} onBack={onBack} onStarted={onStarted} onError={(error) => { throw error }} />)
    await press('Escape')
    expect(onBack).toHaveBeenCalledOnce()
    expect(onStarted).not.toHaveBeenCalled()
  })

  it('leaves an unchanged kind for the list of kinds', async () => {
    const onBack = vi.fn()
    await show(<KindView kind={KIND} profile={null} onBack={onBack} onSaved={() => undefined} onError={(error) => { throw error }} />)
    await press('Escape')
    expect(onBack).toHaveBeenCalledOnce()
  })
})

describe('Enter takes the one dark step', () => {
  it('opens Review from Overview while a document waits', async () => {
    const onReview = vi.fn()
    await show(
      <Overview status={null} inbox={view([entry(1)])} onReview={onReview} onChooseFolder={() => undefined}
        onHandOver={() => undefined} onFeedback={() => undefined} onError={() => undefined} />,
    )
    await press('Enter')
    expect(onReview).toHaveBeenCalledOnce()
  })

  it('opens the folder screen from the start of Overview', async () => {
    const onChooseFolder = vi.fn()
    await show(
      <Overview status={null} inbox={{ settings: null, entries: [], imports: [], jobs: [], profile: null }} onReview={() => undefined}
        onChooseFolder={onChooseFolder} onHandOver={() => undefined} onFeedback={() => undefined} onError={() => undefined} />,
    )
    await press('Enter')
    expect(onChooseFolder).toHaveBeenCalledOnce()
  })

  it('starts reading on the folder screen only once a folder is chosen', async () => {
    const onStarted = vi.fn()
    await show(<ReadFolder profile={null} onBack={() => undefined} onStarted={onStarted} onError={(error) => { throw error }} />)
    await press('Enter', document.body)
    expect(onStarted).not.toHaveBeenCalled()
    await enterOn(button(de.readFolder.choose)!)
    ;(document.activeElement as HTMLElement | null)?.blur()
    await press('Enter', document.body)
    expect(onStarted).toHaveBeenCalledExactlyOnceWith({ folder: '/scans/Neukunden' })
  })

  it('goes from Settings to Overview, and leaves Enter in a choice to the choice', async () => {
    const onOverview = vi.fn()
    await show(
      <Settings status={null} theme="light" onTheme={() => undefined} inbox={null} profile={null}
        onInbox={() => undefined} onOverview={onOverview} onError={(error) => { throw error }} />,
    )
    const choice = host.querySelector('select, input')
    if (choice) await press('Enter', choice)
    expect(onOverview).not.toHaveBeenCalled()
    await press('Enter', document.body)
    expect(onOverview).toHaveBeenCalledOnce()
  })

  it('goes from the list of kinds to Overview', async () => {
    const onOverview = vi.fn()
    await show(<Templates kinds={[KIND]} profile={{ name: 'broker', title: 'Maklerprogramm', target: 'gdv', customer_folder_level: 1, kinds: [{ name: 'policy', title: 'Police', values: [] }], overview_columns: {} }}
      onOpenKind={() => undefined} onSettings={() => undefined} onOverview={onOverview} />)
    await press('Enter')
    expect(onOverview).toHaveBeenCalledOnce()
  })

  it('saves a kind, and leaves Enter in a value to the value', async () => {
    const onSaved = vi.fn()
    await show(<KindView kind={KIND} profile={null} onBack={() => undefined} onSaved={onSaved} onError={(error) => { throw error }} />)
    await press('Enter', host.querySelector('input')!)
    expect(onSaved).not.toHaveBeenCalled()
    await press('Enter', document.body)
    expect(onSaved).toHaveBeenCalledOnce()
  })

  it('never decides a duplicate: Enter on the page does nothing, a focused choice does', async () => {
    const { node, onDecide } = review({ entry: entry(8, { possible_duplicate_of: 7 }), first: { entry: entry(7), document: null } })
    await show(node)
    await press('Enter', document.body)
    expect(onDecide).not.toHaveBeenCalled()
    expect(button(de.inboxReview.same)?.querySelector('kbd')).toBeNull()
    await enterOn(button(de.inboxReview.different)!)
    expect(onDecide).toHaveBeenCalledExactlyOnceWith(false)
  })
})

describe('the core loop by keyboard alone (Z7.3)', () => {
  it('reviews an entry: Enter confirms the unclear value, the focused approval approves', async () => {
    const { node, onCorrect, onApprove } = review()
    await show(node)
    await press('Enter', document.body)
    expect(onCorrect).toHaveBeenCalledExactlyOnceWith({ confirmed: ['premium'] })
    // The test entry does not change with the answer, so the question stays; the approval is checked in inbox-review-keys.
    expect(onApprove).not.toHaveBeenCalled()
  })

  it('approves a settled entry only from the focused button', async () => {
    const settled = entry(7, { values: [value('insurer', 'Nordlicht AG', true), value('premium', '156.64', true)] })
    const { node, onApprove } = review({ entry: settled })
    await show(node)
    await press('Enter', document.body)
    expect(onApprove).not.toHaveBeenCalled()
    await enterOn(button(de.inboxReview.approve)!)
    expect(onApprove).toHaveBeenCalledOnce()
  })

  it('starts the hand-over from the simulation with Enter', async () => {
    const onWrite = vi.fn()
    const inbox = view([entry(1, { state: 'approved' })], [job(1, 'pending')])
    await show(<HandOverView inbox={inbox} previews={PREVIEWS} writing={false} onBack={() => undefined} onWrite={onWrite} />)
    await press('Enter', document.body)
    expect(onWrite).toHaveBeenCalledOnce()
  })

  it('saves the report with Enter once an answer is chosen, also from the chosen option', async () => {
    const onSave = vi.fn()
    const inbox = view([entry(1, { state: 'approved' })], [job(1, 'handed_over')])
    const report = (answers: Parameters<typeof FeedbackView>[0]['answers']) => (
      <FeedbackView inbox={inbox} answers={answers} saving={false} onAnswer={() => undefined} onBack={() => undefined} onSave={onSave} />
    )
    await show(report({}))
    await press('Enter', document.body)
    expect(onSave).not.toHaveBeenCalled()
    await show(report({ Brandt: { imported: true, reason: '' } }))
    await press('Enter', host.querySelector('input[type=radio]')!)
    expect(onSave).toHaveBeenCalledOnce()
  })
})

describe.each(['de', 'en'])('one dark button on every state of Review in %s, an open row included (v002 Z3.2, Z7.2)', (language) => {
  const DATED: ProfileKind[] = [
    {
      name: 'policy',
      title: 'Police',
      values: [
        { name: 'insurer', label: 'Versicherer', question: '', required: true, json_type: 'string' },
        { name: 'start_date', label: 'Beginn', question: '', required: true, json_type: 'date' },
        { name: 'premium', label: 'Beitrag', question: '', required: true, json_type: 'number' },
      ],
    },
  ]
  const row = (label: string) => [...host.querySelectorAll<HTMLElement>('[data-row]')].find((r) => r.textContent?.startsWith(label))!
  const dark = () => host.querySelectorAll('button.bg-ink').length
  const typed = (text: string): ExtractionResult => ({ ...value('premium', text, false), locator: null, source: 'manual' })
  // A question, a settled entry and a typed value that does not fit its type.
  const STATES: [string, InboxEntry][] = [
    ['question', entry(7, { values: [value('insurer', 'Nordlicht AG', false), value('start_date', '01.04.2025', true), value('premium', '1', true)] })],
    ['settled', entry(7, { values: [value('insurer', 'Nordlicht AG', true), value('start_date', '01.04.2025', true), value('premium', '1', true)] })],
    ['misfit', entry(7, { values: [value('insurer', 'Nordlicht AG', true), value('start_date', '01.04.2025', true), typed('abc')] })],
  ]

  beforeEach(() => localStorage.setItem('substrakt.language', language))
  afterEach(() => localStorage.removeItem('substrakt.language'))

  it.each(STATES)('%s: closed, with a row open, and with the hint of an impossible date', async (_, start) => {
    await show(review({ entry: start, kinds: DATED }).node)
    expect(dark()).toBe(1)
    await act(async () => row('Versicherer').click())
    expect(host.querySelector('[data-row] input')).not.toBeNull()
    expect(dark()).toBe(1)
    await press('Escape', host.querySelector('[data-row] input')!)
    await act(async () => row('Beginn').click())
    const input = host.querySelector<HTMLInputElement>('[data-row] input')!
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '31.02.2025')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await press('Enter', input)
    expect(host.querySelector('[role=alert]')).not.toBeNull()
    expect(dark()).toBe(1)
  })
})
