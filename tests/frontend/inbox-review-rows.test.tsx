// @vitest-environment happy-dom
/**
 * The rows under „Weitere Angaben“ and the question above them in Review, as a
 * clerk operates them with clicks and keys:
 *
 * - every value that waits carries a round „?“ in the warn colour and a
 *   settled one its ✓, both with a label (Z2.1);
 * - the page shows the frame the text speaks of, and a value without a place
 *   never speaks of a mark (Z4.1, Z4.2);
 * - a date takes digits only and an impossible one is not sent (Z5.2, Z5.3).
 *
 * The viewer is replaced by a recorder of the location it is handed.
 */

import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const viewer = vi.hoisted(() => ({ highlighted: [] as unknown[] }))
vi.mock('../../src/viewer/ViewerHost', () => ({
  ViewerHost: (props: { highlighted: unknown }) => {
    viewer.highlighted.push(props.highlighted)
    return null
  },
}))

import type { DocumentInfo, ExtractionResult, InboxCorrection, InboxEntry, ProfileKind } from '../../src/api/types'
import { LanguageProvider, type Language } from '../../src/i18n'
import { de } from '../../src/i18n/de'
import { en } from '../../src/i18n/en'
import { InboxReview } from '../../src/places/InboxReview'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const KINDS: ProfileKind[] = [
  {
    name: 'policy',
    title: 'Police',
    values: [
      { name: 'insurer', label: 'Versicherer', question: '', required: true, json_type: 'string' },
      { name: 'premium', label: 'Beitrag', question: '', required: true, json_type: 'number' },
      { name: 'start_date', label: 'Beginn', question: '', required: true, json_type: 'date' },
      { name: 'policyholder', label: 'Versicherungsnehmer', question: '', required: true, json_type: 'string' },
    ],
  },
]

const at = (y: number) => ({ kind: 'pdf_rect' as const, page: 0, x0: 50, y0: y, x1: 170, y1: y + 12 })
const INSURER_AT = at(777)
const PREMIUM_AT = at(534)
const START_AT = at(591)

function read(field: string, text: string, grounded: boolean, locator: ExtractionResult['locator']): ExtractionResult {
  return {
    field,
    value: text,
    normalized: null,
    confidence: grounded ? 0.98 : 0.6,
    source: 'extractor',
    locator,
    matched_text: text,
    grounded,
    note: '',
  }
}

/** The reported case of policy_b_1.pdf: insurer unclear with its frame, premium settled, start unclear, policyholder not read. */
const ENTRY: InboxEntry = {
  id: 1,
  import_id: 1,
  state: 'waiting',
  file_path: '/scans/Brandt/policy_b_1.pdf',
  folder: '/scans/Brandt',
  file_name: 'policy_b_1.pdf',
  sha256: 'ab',
  customer: 'Brandt',
  profile: 'broker',
  kind: 'policy',
  page_count: 1,
  values: [
    read('insurer', 'Nordlicht Versicherung AG', false, INSURER_AT),
    read('premium', '250,94', true, PREMIUM_AT),
    read('start_date', '01.04.2025', false, START_AT),
  ],
  timings: {},
  duplicate_of: null,
  possible_duplicate_of: null,
  duplicate_decision: null,
  problem_key: null,
  changed: [],
  later_arrival: false,
  arrived_at: '2026-11-11T09:00:00Z',
}

const DOCUMENT = { id: 'doc', filename: 'policy_b_1.pdf', pages: [] } as unknown as DocumentInfo

/** Answers like the sidecar: a confirmed or typed value is settled. */
function stored(entry: InboxEntry, c: InboxCorrection): InboxEntry {
  const values = entry.values.map((r) => (c.confirmed?.includes(r.field) ? { ...r, grounded: true } : r))
  for (const [field, text] of Object.entries(c.values ?? {})) {
    const typed: ExtractionResult = { ...read(field, text, true, null), source: 'manual' }
    const i = values.findIndex((r) => r.field === field)
    if (i < 0) values.push(typed)
    else values[i] = typed
  }
  return { ...entry, values }
}

function Harness(props: { start: InboxEntry; kinds: ProfileKind[]; onCorrect: (c: InboxCorrection) => void }) {
  const [entry, setEntry] = useState(props.start)
  return (
    <InboxReview entry={entry} position={{ n: 1, total: 1 }} kinds={props.kinds} document={DOCUMENT} first={null}
      onCorrect={async (c) => {
        props.onCorrect(c)
        setEntry((e) => stored(e, c))
      }}
      onDecide={() => Promise.resolve()} onApprove={() => Promise.resolve()}
      onLater={() => undefined} onBack={() => undefined} onError={(e) => { throw e }} />
  )
}

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  viewer.highlighted = []
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

function show(language: Language, entry: InboxEntry = ENTRY, kinds: ProfileKind[] = KINDS) {
  vi.stubGlobal('localStorage', { getItem: () => language, setItem: () => undefined })
  const onCorrect = vi.fn()
  act(() =>
    root.render(
      <LanguageProvider>
        <Harness start={entry} kinds={kinds} onCorrect={onCorrect} />
      </LanguageProvider>,
    ),
  )
  return onCorrect
}

async function settle(step: () => void = () => undefined) {
  await act(async () => {
    step()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

const rows = () => [...host.querySelectorAll<HTMLElement>('[data-row]')]
const row = (label: string) => rows().find((r) => r.textContent?.startsWith(label))!
const button = (text: string) => [...host.querySelectorAll('button')].find((b) => b.textContent?.trim().startsWith(text))!
const shown = () => viewer.highlighted.at(-1)
const panelText = () => host.querySelector('aside')!.textContent ?? ''
const MARK = /markiert|marks where/

/** Types one character after another, as the browser reports each to React. */
async function type(input: HTMLInputElement, text: string) {
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  for (const char of text)
    await settle(() => {
      set.call(input, input.value + char)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
}
const press = (input: HTMLElement, key: string) =>
  settle(() => input.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })))
const rowInput = () => host.querySelector<HTMLInputElement>('[data-row] input')!

const LANGUAGES: [Language, typeof de][] = [['de', de], ['en', en]]

describe.each(LANGUAGES)('the marks of the rows in %s (Z2.1)', (language, texts) => {
  it('renders ✓, ? and ? in that order for one settled, one unclear and one unread required value', () => {
    // The kind without the insurer: premium settled, start unclear, policyholder not read.
    show(language, ENTRY, [{ ...KINDS[0]!, values: KINDS[0]!.values.slice(1) }])
    const t = texts.inboxReview
    const marks = rows().map((r) => {
      const mark = r.querySelector('[role=img]')
      return mark && [mark.textContent?.trim(), mark.getAttribute('aria-label')]
    })
    expect(marks).toEqual([['✓', t.settledMark], ['?', t.waitingMark], ['?', t.waitingMark]])
  })

  it('shows ? for the unclear question, ✓ for the settled value and ? for the unclear and the unread one', () => {
    show(language)
    const t = texts.inboxReview
    const marks = rows().map((r) => {
      const mark = r.querySelector('[role=img]')
      return mark && [mark.textContent?.trim(), mark.getAttribute('aria-label')]
    })
    expect(marks).toEqual([['?', t.waitingMark], ['✓', t.settledMark], ['?', t.waitingMark], ['?', t.waitingMark]])
    // As many „?“ below as the count above names.
    expect(panelText()).toContain(t.unclear(3))
    const question = rows()[0]!.querySelector('[role=img]')!
    expect(question.className).toMatch(/\brounded-full\b/)
    expect(question.className).toMatch(/\bbg-warn\b/)
    for (const r of rows()) expect(r.querySelectorAll('[role=img]').length).toBeLessThanOrEqual(1)
  })
})

describe('the frame the text speaks of (Z4.1)', () => {
  it('stays the question’s after a click on a row without a place, and the text keeps its mark', async () => {
    show('de')
    expect(shown()).toEqual(INSURER_AT)
    expect(panelText()).toContain(de.inboxReview.reason.unclear)
    await settle(() => row('Versicherungsnehmer').click())
    expect(shown()).toEqual(INSURER_AT)
    expect(panelText()).toContain(de.inboxReview.reason.unclear)
  })

  it('names no mark while a row with a place of its own is open', async () => {
    show('de')
    await settle(() => row('Beitrag').click())
    expect(shown()).toEqual(PREMIUM_AT)
    expect(panelText()).not.toMatch(MARK)
    expect(panelText()).toContain(de.inboxReview.reason.unclearUnmarked)
  })

  it('shows the next question’s frame after the question is answered, whatever row was clicked before', async () => {
    show('de')
    await settle(() => row('Beitrag').click())
    await settle(() => button(de.review.looksRight).click())
    expect(host.querySelector('h1')!.textContent).toContain('Beginn')
    expect(shown()).toEqual(START_AT)
    expect(panelText()).toContain(de.inboxReview.reason.unclear)
  })
})

describe.each(LANGUAGES)('a value without a place in %s (Z4.2)', (language, texts) => {
  const t = texts.inboxReview
  const NO_PLACE: InboxEntry = { ...ENTRY, values: [{ ...ENTRY.values[0]!, locator: null }, ...ENTRY.values.slice(1)] }

  it('asks its question without a mark and says it has no place', () => {
    show(language, NO_PLACE)
    expect(shown()).toBeNull()
    expect(panelText()).toContain(t.reason.noLocation)
    expect(panelText()).not.toMatch(MARK)
  })

  it('says at its row that the document has no place for it', async () => {
    show(language, NO_PLACE)
    await settle(() => row('Versicherungsnehmer').click())
    expect(row('Versicherungsnehmer').textContent).toContain(t.noPlace)
    expect(panelText()).not.toMatch(MARK)
  })
})

describe('the date mask (Z5.2)', () => {
  it('sets the points while digits are typed in a row', async () => {
    show('de')
    await settle(() => row('Beginn').click())
    const input = rowInput()
    await settle(() => input.dispatchEvent(new Event('focus')))
    await settle(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await type(input, '01042025')
    expect(input.value).toBe('01.04.2025')
  })

  it('ignores a letter and removes a digit with the point before it on Backspace', async () => {
    const UNREAD = { ...ENTRY, values: ENTRY.values.filter((r) => r.field !== 'insurer' && r.field !== 'start_date') }
    show('de', { ...UNREAD, values: [...UNREAD.values, read('insurer', 'Nordlicht', true, INSURER_AT)] })
    // The question is the unread start date, typed in the large input.
    expect(host.querySelector('h1')!.textContent).toContain('Beginn')
    const input = host.querySelector<HTMLInputElement>('aside > input')!
    await type(input, '0a1')
    expect(input.value).toBe('01')
    await type(input, '04.')
    expect(input.value).toBe('01.04.')
    await press(input, 'Backspace')
    expect(input.value).toBe('01.0')
  })
})

describe.each(LANGUAGES)('an impossible date in %s (Z5.3)', (language, texts) => {
  it.each(['31022025', '01132025', '010425'])('is not sent: %s', async (digits) => {
    const onCorrect = show(language)
    await settle(() => row('Beginn').click())
    const input = rowInput()
    await press(input, 'Backspace')
    for (let i = 0; i < 10; i++) await press(input, 'Backspace')
    await type(input, digits)
    const typed = input.value
    input.focus()
    await press(input, 'Enter')
    expect(onCorrect).not.toHaveBeenCalled()
    expect(host.querySelector('[role=alert]')?.textContent).toContain(language === 'de' ? 'TT.MM.JJJJ' : 'DD.MM.YYYY')
    expect(rowInput().value).toBe(typed)
    expect(document.activeElement).toBe(rowInput())
  })

  it('is sent as typed when it is possible, and settles the value', async () => {
    const onCorrect = show(language)
    await settle(() => row('Beginn').click())
    const input = rowInput()
    for (let i = 0; i < 10; i++) await press(input, 'Backspace')
    await type(input, '02042025')
    await press(input, 'Enter')
    expect(onCorrect.mock.calls).toEqual([[{ values: { start_date: '02.04.2025' } }]])
    const mark = row('Beginn').querySelector('[role=img]')
    expect(mark?.getAttribute('aria-label')).toBe(texts.inboxReview.settledMark)
  })
})
