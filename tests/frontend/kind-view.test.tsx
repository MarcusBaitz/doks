/**
 * The rules behind changing the values of a kind in Templates: what saving
 * sends, what adding a value does, which refusal a clerk reads, and the
 * warning under a removed value the target receives. The places test renders
 * the whole screen; this one pins its rules.
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { SubstraktError } from '../../src/api/client'
import { LanguageProvider } from '../../src/i18n'
import { de } from '../../src/i18n/de'
import type { KindValues } from '../../src/api/types'
import {
  KindScreen,
  kindRefusal,
  onBackPressed,
  onEscape,
  unsaved,
  ValueLine,
  valuesToSend,
  withNewValue,
  type Line,
} from '../../src/places/KindView'

const KEPT: Line = { name: 'insurer', label: 'Gesellschaft', removed: false }
const REMOVED: Line = { name: 'line_of_business', label: 'Sparte', removed: true }
const ADDED: Line = { name: null, label: 'Selbstbeteiligung', removed: false }

describe('changing the values of a kind', () => {
  it('sends every value not removed, a new one without a name', () => {
    expect(valuesToSend([KEPT, REMOVED, ADDED])).toEqual([
      { name: 'insurer', label: 'Gesellschaft' },
      { name: null, label: 'Selbstbeteiligung' },
    ])
  })

  it('adds a typed value trimmed and ignores a blank one', () => {
    expect(withNewValue([KEPT], '  Selbstbeteiligung ')).toEqual([KEPT, ADDED])
    expect(withNewValue([KEPT], '   ')).toEqual([KEPT])
  })

  it('shows the text of a refused change and leaves every other error to the application', () => {
    const refused = new SubstraktError('kind-change-refused', '', null, 'label-twice')
    const unknownReason = new SubstraktError('kind-change-refused', '', null, 'nobody-knows')
    const other = new SubstraktError('internal-error', '')

    expect(kindRefusal(refused, de)).toBe(de.kinds.refused['label-twice'])
    expect(kindRefusal(unknownReason, de)).toBeNull()
    expect(kindRefusal(other, de)).toBeNull()
    expect(kindRefusal(new Error('broken'), de)).toBeNull()
  })

  it('warns under a removed value only when the target receives it', () => {
    const line = (row: Line, target: string | null) =>
      renderToStaticMarkup(
        <LanguageProvider>
          <ValueLine row={row} target={target} onChange={() => {}} />
        </LanguageProvider>,
      )

    expect(line(REMOVED, 'Zielprogramm')).toContain(de.kinds.warning('Zielprogramm'))
    expect(line(REMOVED, 'Zielprogramm')).toContain(de.kinds.restore)
    expect(line(REMOVED, null)).not.toContain(de.kinds.warning('Zielprogramm'))
    expect(line(KEPT, 'Zielprogramm')).not.toContain(de.kinds.warning('Zielprogramm'))
    expect(line(KEPT, null)).toContain(de.kinds.onlyShown)
  })
})

const KIND: KindValues = {
  name: 'policy',
  title: 'Police',
  values: [{ name: 'insurer', label: 'Versicherer' }, { name: 'policy_number', label: 'Nummer' }],
}
const STORED: Line[] = KIND.values.map((v) => ({ name: v.name, label: v.label, removed: false }))
const noop = () => undefined

function screen(rows: Line[], state: { asking?: boolean; refusal?: string | null } = {}): string {
  return renderToStaticMarkup(
    <LanguageProvider>
      <KindScreen
        kind={KIND}
        profile={null}
        rows={rows}
        asking={state.asking ?? false}
        saving={false}
        saved={false}
        refusal={state.refusal ?? null}
        onChange={noop}
        onSave={noop}
        onBack={noop}
        onDiscard={noop}
        onKeepEditing={noop}
      />
    </LanguageProvider>,
  )
}

describe('leaving a kind', () => {
  // Rename the first value, as typing into its line does.
  const renamed = STORED.map((row, i) => (i === 0 ? { ...row, label: 'Gesellschaft' } : row))

  it('leaves at once when nothing changed', () => {
    expect(unsaved(KIND, STORED)).toBe(false)
    expect(onBackPressed(KIND, STORED)).toBe('leave')
  })

  it('asks before leaving with a renamed, removed or added value', () => {
    expect(onBackPressed(KIND, renamed)).toBe('ask')
    expect(onBackPressed(KIND, STORED.map((r, i) => (i === 1 ? { ...r, removed: true } : r)))).toBe('ask')
    expect(onBackPressed(KIND, withNewValue(STORED, 'Selbstbeteiligung'))).toBe('ask')
  })

  it('lets Esc close an open question first and otherwise act like back', () => {
    expect(onEscape(true, KIND, renamed)).toBe('close')
    expect(onEscape(false, KIND, renamed)).toBe('ask')
    expect(onEscape(false, KIND, STORED)).toBe('leave')
  })

  it('shows the question with both answers and keeps the renamed value, so cancel loses nothing', () => {
    const asking = screen(renamed, { asking: true })
    expect(asking).toContain(de.kinds.leaveQuestion)
    expect(asking).toContain(de.kinds.keepEditing)
    expect(asking).toContain(de.kinds.discard)
    expect(asking).toMatch(/<input[^>]*value="Gesellschaft"/)
    // „Weiter bearbeiten“ only closes the question; the lines are the same ones.
    const afterCancel = screen(renamed)
    expect(afterCancel).not.toContain(de.kinds.leaveQuestion)
    expect(afterCancel).toMatch(/<input[^>]*value="Gesellschaft"/)
    expect(onBackPressed(KIND, renamed)).toBe('ask')
  })

  it('shows a refused change as a Notice above the save button and keeps what was typed', () => {
    const text = de.kinds.refused['label-twice']!
    const markup = screen(renamed, { refusal: text })
    expect(markup).toMatch(new RegExp(`class="flex gap-2.5 rounded-md[^"]*bg-warn-bg[^"]*"[^>]*>.*${text}`))
    expect(markup).not.toContain('text-bad')
    expect(markup.indexOf(text)).toBeLessThan(markup.indexOf(de.kinds.save))
    expect(markup).toMatch(/<input[^>]*value="Gesellschaft"/)
  })
})
