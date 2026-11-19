/**
 * The decisions behind Review of a watched-folder entry: which value is asked
 * about, when two entries read the same value, and which refusal text a
 * clerk sees. The places test renders the screens; this one pins their rules.
 */

import { describe, expect, it, vi } from 'vitest'

// The screens import the viewer, and PDF.js reads `DOMMatrix`, which Node lacks, while it loads.
vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: { workerSrc: '' } }))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '' }))

import { SubstraktError } from '../../src/api/client'
import type { DocumentInfo, ExtractionResult, InboxSettings, KindValue } from '../../src/api/types'
import { de } from '../../src/i18n/de'
import { en } from '../../src/i18n/en'
import { changeTarget, confirmation, isOpen, nextQuestion, reason, refusalText, same } from '../../src/places/InboxReview'
import { documentFor, target } from '../../src/places/Review'

const REQUIRED: KindValue = { name: 'insurer', label: 'Insurer', question: '', required: true, json_type: 'string' }
const OPTIONAL: KindValue = { name: 'payment_mode', label: 'Payment mode', question: '', required: false, json_type: 'string' }

function result(value: string | null, grounded: boolean, extra: Partial<ExtractionResult> = {}): ExtractionResult {
  return {
    field: 'insurer',
    value,
    normalized: null,
    confidence: grounded ? 0.98 : 0.6,
    source: 'extractor',
    locator: { kind: 'pdf_rect', page: 0, x0: 0, y0: 0, x1: 1, y1: 1 },
    matched_text: value ?? '',
    grounded,
    note: '',
    ...extra,
  }
}

describe('which value waits for the clerk', () => {
  it('waits on a required value until it is read and grounded', () => {
    expect(isOpen(REQUIRED, undefined, [])).toBe(true)
    expect(isOpen(REQUIRED, result('Nordlicht', false), [])).toBe(true)
    expect(isOpen(REQUIRED, result('Nordlicht', true), [])).toBe(false)
  })

  it('waits on an optional value only when it was read without certainty', () => {
    expect(isOpen(OPTIONAL, undefined, [])).toBe(false)
    expect(isOpen(OPTIONAL, result('jährlich', false), [])).toBe(true)
    expect(isOpen(OPTIONAL, result('jährlich', false), ['payment_mode'])).toBe(false)
  })

  it('asks about the value being edited before the first open one', () => {
    const results = new Map([['insurer', result(null, false)]])
    expect(nextQuestion([REQUIRED, OPTIONAL], results, [], null)).toBe(REQUIRED)
    expect(nextQuestion([REQUIRED, OPTIONAL], results, [], 'payment_mode')).toBe(OPTIONAL)
    expect(nextQuestion([OPTIONAL], new Map(), [], null)).toBeNull()
  })

  it('asks again about a value that was unclear when the view opened until it is answered there', () => {
    const settled = new Map([['insurer', result('Nordlicht', true)]])
    expect(nextQuestion([REQUIRED], settled, [], null)).toBeNull()
    expect(nextQuestion([REQUIRED], settled, [], null, ['insurer'])).toBe(REQUIRED)
  })

  it('offers to change the value looked at, else one a person changed, else the first', () => {
    expect(changeTarget([REQUIRED, OPTIONAL], [], 'payment_mode')).toBe(OPTIONAL)
    expect(changeTarget([REQUIRED, OPTIONAL], ['payment_mode'], null)).toBe(OPTIONAL)
    expect(changeTarget([REQUIRED, OPTIONAL], [], null)).toBe(REQUIRED)
  })
})

describe('what the clerk’s answer stores', () => {
  it('confirms the value as read, so it keeps its location and counts as unchanged', () => {
    expect(confirmation('insurer', 'Nordlicht', result(' Nordlicht ', false))).toEqual({ confirmed: ['insurer'] })
  })

  it('corrects a value the clerk typed differently or that was not read', () => {
    expect(confirmation('insurer', 'Nordstern', result('Nordlicht', false))).toEqual({ values: { insurer: 'Nordstern' } })
    expect(confirmation('insurer', 'Nordstern', undefined)).toEqual({ values: { insurer: 'Nordstern' } })
  })
})

describe('the reason a value is asked about', () => {
  it('names a missing value, a value without a place and an unclear one', () => {
    expect(reason(undefined, de.inboxReview.reason)).toBe(de.inboxReview.reason.noValue)
    expect(reason(result('x', false, { locator: null }), de.inboxReview.reason)).toBe(de.inboxReview.reason.noLocation)
    expect(reason(result('x', false), de.inboxReview.reason)).toBe(de.inboxReview.reason.unclear)
  })
})

describe('values two entries share', () => {
  it('compares the normalised value of the same name', () => {
    const mine = result('1.200,00', true, { normalized: '1200.00' })
    expect(same(mine, [result('1200,00', true, { normalized: '1200.00' })])).toBe(true)
    expect(same(mine, [result('1.200,00', true, { normalized: '1300.00' })])).toBe(false)
    expect(same(mine, [result('1.200,00', true, { field: 'premium' })])).toBe(false)
  })
})

describe('the text of a refusal', () => {
  const NO_WORDS = { kinds: [], target: '' }

  it('shows the reason in the clerk’s words when the dictionary has it', () => {
    const error = new SubstraktError('correction-refused', 'Refused', null, 'entry-changed')
    expect(refusalText(error, de, '', NO_WORDS)).toBe(de.inboxReview.refused['entry-changed'])
  })

  it('falls back to the text of the key for a reason without its own text', () => {
    const error = new SubstraktError('approval-refused', 'Refused', null, 'unheard-of')
    expect(refusalText(error, de, '', NO_WORDS)).toBe(de.errors.messages['approval-refused'])
  })

  it('names why a refused hand-over cannot be written, not only that it cannot', () => {
    const words = { kinds: [{ name: 'contract_change', title: 'Vertragsänderung', values: [] }], target: 'Zielprogramm' }
    const kind = new SubstraktError('approval-refused', 'Refused', null, 'hand-over-not-possible', ['kind_not_handed_over'])
    const mode = new SubstraktError('approval-refused', 'Refused', null, 'hand-over-not-possible', ['payment_mode_code'])
    for (const texts of [de, en]) {
      expect(refusalText(kind, texts, 'contract_change', words)).toBe(
        `${texts.inboxReview.refused['hand-over-not-possible']} ${texts.handOver.kindNotHandedOver('Vertragsänderung', 'Zielprogramm')}`,
      )
      expect(refusalText(mode, texts, 'policy', words)).toBe(
        `${texts.inboxReview.refused['hand-over-not-possible']} ${texts.handOver.unknownPaymentMode('', 'Zielprogramm')}`,
      )
      const long = new SubstraktError('approval-refused', 'Refused', null, 'hand-over-not-possible', ['value_fits_field:policy_number'])
      const policy = { name: 'policy', title: 'Police', values: [{ name: 'policy_number', label: 'Nummer' }] }
      expect(refusalText(long, texts, 'policy', { kinds: [policy], target: 'Zielprogramm' })).toContain(texts.handOver.doesNotFit('Nummer'))
    }
  })

  it('leaves every other error to the shell', () => {
    expect(refusalText(new SubstraktError('internal-error', 'Broken'), de, '', NO_WORDS)).toBeNull()
    expect(refusalText(new Error('Broken'), de, '', NO_WORDS)).toBeNull()
  })
})

describe('the target named when nothing waits', () => {
  const settings = (profile: string | null, titles: string[]): InboxSettings => ({
    folder: null,
    handover_folder: null,
    profile,
    profiles: titles.map((title, i) => ({ name: `p${i}`, title })),
    watching: false,
    retention_days: 90,
  })

  it('takes the active profile, else the only one, else none', () => {
    expect(target(null)).toBeNull()
    expect(target(settings('p1', ['A', 'B']))).toBe('B')
    expect(target(settings(null, ['A']))).toBe('A')
    expect(target(settings(null, ['A', 'B']))).toBeNull()
  })
})

describe('the document Review shows for an entry', () => {
  const info = { id: 'd1' } as DocumentInfo

  it('is the one opened for its own path, never the one of the entry before', () => {
    expect(documentFor({ path: '/a.pdf', document: info }, '/a.pdf')).toBe(info)
    // Before the cleanup closes it, the next entry would otherwise ask for pages of a closed document.
    expect(documentFor({ path: '/a.pdf', document: info }, '/b.pdf')).toBeNull()
    expect(documentFor(null, '/a.pdf')).toBeNull()
  })
})
