// @vitest-environment happy-dom
/**
 * Review of a watched-folder entry as a clerk operates it, with clicks and
 * keys in a DOM: the approval waits until every unclear value was confirmed or
 * corrected in this view, Enter settles only the active value and never
 * approves, and an entry without a kind asks for one inside the panel.
 * Any value, also one missing in the
 * document, is corrected in its row with Enter, Escape closes the row and
 * stays in Review, and corrections in rows alone open the approval.
 */

import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The screen imports the viewer, and PDF.js reads `DOMMatrix` while it loads.
vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: { workerSrc: '' } }))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '' }))

import type { ExtractionResult, InboxCorrection, InboxEntry, ProfileKind } from '../../src/api/types'
import { LanguageProvider } from '../../src/i18n'
import { de } from '../../src/i18n/de'
import { InboxReview } from '../../src/places/InboxReview'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const KINDS: ProfileKind[] = [
  {
    name: 'policy',
    title: 'Police',
    values: [
      { name: 'insurer', label: 'Versicherer', question: '', required: true, json_type: 'string' },
      { name: 'premium', label: 'Beitrag', question: '', required: true, json_type: 'string' },
      { name: 'payment_mode', label: 'Zahlweise', question: '', required: false, json_type: 'string' },
    ],
  },
  { name: 'invoice', title: 'Beitragsrechnung', values: [] },
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

/** Sure insurer, unclear premium and unclear payment mode. */
const TWO_UNCLEAR: InboxEntry = {
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
  values: [value('insurer', 'Nordlicht AG', true), value('premium', '156.64', false), value('payment_mode', 'jährlich', false)],
  timings: {},
  duplicate_of: null,
  possible_duplicate_of: null,
  duplicate_decision: null,
  problem_key: null,
  changed: [],
  later_arrival: false,
  arrived_at: '2026-11-11T09:00:00Z',
}

/** Answers like the sidecar: a confirmed or typed value is settled, a chosen kind is set. */
function stored(entry: InboxEntry, c: InboxCorrection): InboxEntry {
  const values = entry.values.map((r) => {
    if (c.confirmed?.includes(r.field)) return { ...r, grounded: true }
    const typed = c.values?.[r.field]
    return typed === undefined ? r : { ...r, value: typed, grounded: true }
  })
  // A value that was not read arrives with the person's text.
  for (const [field, text] of Object.entries(c.values ?? {}))
    if (!values.some((r) => r.field === field)) values.push({ ...value(field, text, true), locator: null, source: 'manual' })
  return { ...entry, kind: c.kind ?? entry.kind, values, changed: [...entry.changed, ...Object.keys(c.values ?? {})] }
}

function Harness(props: { start: InboxEntry; kinds: ProfileKind[]; onCorrect: (c: InboxCorrection) => void; onApprove: () => void; onBack: () => void }) {
  const [entry, setEntry] = useState(props.start)
  return (
    <InboxReview
      key={`${entry.id}:${entry.kind}`}
      entry={entry}
      position={{ n: 1, total: 1 }}
      kinds={props.kinds}
      document={null}
      first={null}
      onCorrect={async (c) => {
        props.onCorrect(c)
        setEntry((e) => stored(e, c))
      }}
      onDecide={() => Promise.resolve()}
      onApprove={async () => props.onApprove()}
      onLater={() => undefined}
      onBack={props.onBack}
      onError={(error) => {
        throw error
      }}
    />
  )
}

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

async function settle(step: () => void = () => undefined) {
  await act(async () => {
    step()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

function show(start: InboxEntry, kinds: ProfileKind[] = KINDS) {
  const onCorrect = vi.fn()
  const onApprove = vi.fn()
  const onBack = vi.fn()
  act(() =>
    root.render(
      <LanguageProvider>
        <Harness start={start} kinds={kinds} onCorrect={onCorrect} onApprove={onApprove} onBack={onBack} />
      </LanguageProvider>,
    ),
  )
  return { onCorrect, onApprove, onBack }
}

const button = (text: string) =>
  [...host.querySelectorAll('button')].find((b) => b.textContent?.trim().startsWith(text)) ?? null
const enter = () => document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
const darkButtons = () => host.querySelectorAll('button.bg-ink').length

describe('the approval waits for a look at every unclear value', () => {
  it('stays disabled after confirming one of two unclear values and opens after correcting the other', async () => {
    const { onCorrect } = show(TWO_UNCLEAR)
    expect(button(de.inboxReview.approve)?.disabled).toBe(true)

    await settle(() => button(de.review.looksRight)!.click())
    expect(onCorrect).toHaveBeenLastCalledWith({ confirmed: ['premium'] })
    expect(button(de.inboxReview.approve)?.disabled).toBe(true)

    await settle(() => button(de.review.change)!.click())
    const input = host.querySelector<HTMLInputElement>('input[type=text]')!
    await settle(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'halbjährlich')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await settle(() => button(de.review.accept)!.click())
    expect(onCorrect).toHaveBeenLastCalledWith({ values: { payment_mode: 'halbjährlich' } })

    expect(button(de.inboxReview.approve)?.disabled).toBe(false)
    expect(darkButtons()).toBe(1)
  })
})

describe('the line above the question and the note below the approval', () => {
  // The number each text names, found by the texts it can render.
  const named = (text: (n: number) => string) => [1, 2, 3, 4, 5, 6].filter((n) => host.textContent?.includes(text(n)))
  const counts = () => ({ above: named(de.inboxReview.unclear), below: named(de.inboxReview.approveAfter) })

  it('name the same number of values that still wait, before and after one is confirmed', async () => {
    show(TWO_UNCLEAR)
    expect(counts()).toEqual({ above: [2], below: [2] })
    await settle(() => button(de.review.looksRight)!.click())
    expect(counts()).toEqual({ above: [1], below: [1] })
  })
})

describe('Enter settles the active value and nothing else', () => {
  it('confirms one value per press, moves to the next and never approves', async () => {
    const { onCorrect, onApprove } = show(TWO_UNCLEAR)
    for (let press = 0; press < 5; press++) await settle(enter)
    expect(onCorrect.mock.calls).toEqual([[{ confirmed: ['premium'] }], [{ confirmed: ['payment_mode'] }]])
    expect(onApprove).not.toHaveBeenCalled()
    expect(button(de.inboxReview.approve)?.disabled).toBe(false)
  })

  it('shows no Enter key on the approval', async () => {
    show({ ...TWO_UNCLEAR, values: TWO_UNCLEAR.values.map((r) => ({ ...r, grounded: true })) })
    expect(button(de.inboxReview.approve)?.querySelector('kbd')).toBeNull()
  })
})

describe('an entry without a kind', () => {
  const NO_KIND: InboxEntry = { ...TWO_UNCLEAR, kind: null, values: [] }

  it('offers the kinds in the panel with „Damit lesen“ as the one dark button', () => {
    show(NO_KIND)
    const options = [...host.querySelectorAll<HTMLInputElement>('input[type=radio]')]
    expect(options.map((o) => o.value)).toEqual(['policy', 'invoice'])
    expect(host.querySelector('select')).toBeNull()
    expect(darkButtons()).toBe(1)
    expect(button(de.inboxReview.readWith)?.classList.contains('bg-ink')).toBe(true)
    expect(button(de.inboxReview.readWith)?.disabled).toBe(true)
    expect(host.textContent).not.toMatch(/\boben\b/)
  })

  it('reads the entry with the chosen kind on Enter', async () => {
    const { onCorrect } = show(NO_KIND)
    const option = host.querySelector<HTMLInputElement>('input[value=invoice]')!
    await settle(() => option.click())
    await settle(() => option.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
    expect(onCorrect).toHaveBeenCalledWith({ kind: 'invoice' })
  })
})

describe('a correction in the row (v002 Z6.1, Z6.2)', () => {
  /** Insurer sure, policyholder not read, premium unclear: two values keep the approval back. */
  const HOLDER: ProfileKind[] = [
    {
      name: 'policy',
      title: 'Police',
      values: [
        { name: 'insurer', label: 'Versicherer', question: '', required: true, json_type: 'string' },
        { name: 'policyholder', label: 'Versicherungsnehmer', question: '', required: true, json_type: 'string' },
        { name: 'premium', label: 'Beitrag', question: '', required: true, json_type: 'number' },
      ],
    },
  ]
  const ENTRY: InboxEntry = { ...TWO_UNCLEAR, values: [value('insurer', 'Nordlicht AG', true), value('premium', '156.64', false)] }

  const row = (label: string) => [...host.querySelectorAll<HTMLElement>('[data-row]')].find((r) => r.textContent?.startsWith(label))!
  const rowInput = () => host.querySelector<HTMLInputElement>('[data-row] input')!
  async function typeInRow(text: string) {
    const input = rowInput()
    await settle(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, text)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
  }
  const key = (target: EventTarget, name: string) =>
    settle(() => target.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true, cancelable: true })))

  it('saves a value missing in the document with Enter in its row', async () => {
    const { onCorrect } = show(ENTRY, HOLDER)
    expect(row('Versicherungsnehmer').textContent).toContain(de.inboxReview.missing)
    await settle(() => row('Versicherungsnehmer').click())
    expect(rowInput().value).toBe('')
    await typeInRow('Jonas Brandt')
    await key(rowInput(), 'Enter')
    expect(onCorrect.mock.calls).toEqual([[{ values: { policyholder: 'Jonas Brandt' } }]])
    expect(row('Versicherungsnehmer').textContent).toContain('Jonas Brandt')
  })

  it('closes a row with Escape as it was, sends nothing and stays in Review', async () => {
    const { onCorrect, onBack } = show(ENTRY, HOLDER)
    await settle(() => row('Versicherer').click())
    expect(rowInput().value).toBe('Nordlicht AG')
    await typeInRow('Südlicht AG')
    await key(rowInput(), 'Escape')
    expect(host.querySelector('[data-row] input')).toBeNull()
    expect(row('Versicherer').textContent).toContain('Nordlicht AG')
    expect(onCorrect).not.toHaveBeenCalled()
    expect(onBack).not.toHaveBeenCalled()
  })

  it('opens the approval when both waiting values were corrected in rows, and Enter never approves', async () => {
    const { onCorrect, onApprove } = show(ENTRY, HOLDER)
    expect(button(de.inboxReview.approve)?.disabled).toBe(true)
    await settle(() => row('Beitrag').click())
    await typeInRow('165.64')
    await key(rowInput(), 'Enter')
    await settle(() => row('Versicherungsnehmer').click())
    await typeInRow('Jonas Brandt')
    await key(rowInput(), 'Enter')
    expect(onCorrect.mock.calls).toEqual([[{ values: { premium: '165.64' } }], [{ values: { policyholder: 'Jonas Brandt' } }]])
    expect(button(de.inboxReview.approve)?.disabled).toBe(false)
    expect(darkButtons()).toBe(1)
    for (let press = 0; press < 3; press++) await settle(enter)
    await settle(() => row('Versicherer').click())
    await key(rowInput(), 'Enter')
    expect(onApprove).not.toHaveBeenCalled()
  })
})
