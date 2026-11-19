// @vitest-environment happy-dom
/**
 * Every select on the four places takes its colours from the tokens, so that
 * WebKitGTK never draws light text on a white native list in the dark theme:
 * the two filters on Overview, „Erkannt als“ in
 * Review, the way of working and the retention period in Settings.
 */

import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: { workerSrc: '' } }))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '' }))

import type { ExtractionResult, InboxEntry, InboxSettings, ProfileDescription, ProfileKind } from '../../src/api/types'
import { LanguageProvider, type Language } from '../../src/i18n'
import { InboxReview } from '../../src/places/InboxReview'
import { Overview, type InboxView } from '../../src/places/Overview'
import { SettingsView } from '../../src/places/Settings'
import { OPTION, SELECT } from '../../src/ui/components'

const noop = () => undefined
const done = () => Promise.resolve()

const KINDS: ProfileKind[] = [
  { name: 'policy', title: 'Police', values: [{ name: 'insurer', label: 'Versicherer', question: '', required: true, json_type: 'string' }] },
  { name: 'invoice', title: 'Beitragsrechnung', values: [] },
]
const PROFILE: ProfileDescription = {
  name: 'broker',
  title: 'Broker program',
  target: 'gdv',
  customer_folder_level: 1,
  kinds: [{ name: 'policy', title: 'Police', values: [] }],
  overview_columns: {},
}
// Built without the hand-over folder, which another contract milestone removes.
const SETTINGS = {
  folder: '/scans',
  profile: 'broker',
  profiles: [{ name: 'broker', title: 'Broker program' }],
  watching: true,
  retention_days: 90,
} as InboxSettings

const INSURER: ExtractionResult = {
  field: 'insurer',
  value: 'Nordlicht AG',
  normalized: null,
  confidence: 0.98,
  source: 'extractor',
  locator: { kind: 'pdf_rect', page: 0, x0: 50, y0: 600, x1: 300, y1: 620 },
  matched_text: 'Nordlicht AG',
  grounded: true,
  note: '',
}
const ENTRY: InboxEntry = {
  id: 1,
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
  values: [INSURER],
  timings: {},
  duplicate_of: null,
  possible_duplicate_of: null,
  duplicate_decision: null,
  problem_key: null,
  changed: [],
  later_arrival: false,
  arrived_at: '2026-11-11T09:00:00Z',
}
const VIEW: InboxView = {
  settings: SETTINGS,
  entries: [ENTRY],
  imports: [{ id: 1, folder: '/scans', started_at: '2026-11-11T09:00:00Z', finished_at: '2026-11-11T09:05:00Z' }],
  jobs: [],
  profile: PROFILE,
}

function render(language: Language, node: React.ReactNode): HTMLElement {
  vi.stubGlobal('localStorage', { getItem: () => language, setItem: noop })
  document.documentElement.dataset.theme = 'dark'
  const host = document.createElement('div')
  host.innerHTML = renderToStaticMarkup(<LanguageProvider>{node}</LanguageProvider>)
  return host
}

const screens = (language: Language) => ({
  overview: render(
    language,
    <Overview status={null} inbox={VIEW} onReview={noop} onChooseFolder={noop} onHandOver={noop} onFeedback={noop} onError={noop} />,
  ),
  review: render(
    language,
    <InboxReview entry={ENTRY} position={{ n: 1, total: 1 }} kinds={KINDS} document={null} first={null}
      onCorrect={done} onDecide={done} onApprove={done} onLater={noop} onBack={noop} onError={noop} />,
  ),
  settings: render(
    language,
    <SettingsView status={null} theme="dark" onTheme={noop} inbox={SETTINGS} profile={PROFILE} onOverview={noop}
      saved={null} refused={null} change={done} pick={done} />,
  ),
})

/** The selects whose own classes or options leave the shared token style. */
function unstyled(host: HTMLElement): string[] {
  const has = (el: Element, classes: string) => classes.split(' ').every((c) => el.classList.contains(c))
  // A colour of its own besides the shared one would decide the colour by cascade order.
  const ownColour = (el: Element, shared: string) =>
    [...el.classList].some((c) => /^(bg|text)-(?!\[)/.test(c) && !shared.split(' ').includes(c))
  return [...host.querySelectorAll('select')].flatMap((select) => {
    const bad = !has(select, SELECT) || ownColour(select, SELECT)
    const badOptions = [...select.querySelectorAll('option')].filter((o) => !has(o, OPTION) || ownColour(o, OPTION))
    return bad || badOptions.length > 0 ? [select.getAttribute('aria-label') ?? select.outerHTML.slice(0, 80)] : []
  })
}

afterEach(() => vi.unstubAllGlobals())

describe.each<Language>(['de', 'en'])('selects in the dark theme in %s', (language) => {
  it('colour every select and option of Overview, Review and Settings from the tokens', () => {
    const counts = Object.fromEntries(
      Object.entries(screens(language)).map(([place, host]) => {
        expect(unstyled(host), place).toEqual([])
        return [place, host.querySelectorAll('select').length]
      }),
    )
    expect(counts).toEqual({ overview: 2, review: 1, settings: 2 })
    expect(SELECT).toMatch(/\bbg-card\b/)
    expect(SELECT).toMatch(/\btext-ink\b/)
    expect(OPTION).toMatch(/\bbg-card\b/)
    expect(OPTION).toMatch(/\btext-ink\b/)
  })
})

describe('the check of the shared style', () => {
  it('rejects a select without it, and one whose option has no colours', () => {
    const host = document.createElement('div')
    host.innerHTML = `<select aria-label="bare"><option>a</option></select><select aria-label="option" class="${SELECT}"><option>a</option></select>`
    expect(unstyled(host)).toEqual(['bare', 'option'])
  })

  it('rejects a select with a colour of its own', () => {
    const host = document.createElement('div')
    host.innerHTML = `<select aria-label="own" class="${SELECT} bg-panel"><option class="${OPTION}">a</option></select>`
    expect(unstyled(host)).toEqual(['own'])
  })
})

describe('color-scheme', () => {
  it('is dark under the dark theme and light under the light one', () => {
    const tokens = readFileSync('src/design/tokens.css', 'utf8')
    const block = (theme: string) => tokens.match(new RegExp(`\\[data-theme='${theme}'\\] \\{([^}]*)\\}`))?.[1] ?? ''
    expect(block('dark')).toMatch(/color-scheme:\s*dark;/)
    expect(block('light')).toMatch(/color-scheme:\s*light;/)
    expect(readFileSync('src/index.css', 'utf8')).toContain("@import './design/tokens.css'")
  })
})
