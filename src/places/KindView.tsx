/**
 * The values one document kind reads, as lines a clerk renames, removes or adds.
 *
 * Saving sends the whole list; the sidecar writes it as an override file next
 * to the shipped kind, so the next document read uses it without a restart.
 * Values already read stay as they are; this screen only says so. Leaving with
 * unsaved lines, by the back link or Esc, asks first.
 */

import { AlertCircle, ArrowLeft, Check } from 'lucide-react'
import { useState } from 'react'

import { api, SubstraktError } from '../api/client'
import type { KindValues, ProfileDescription, ValueChange } from '../api/types'
import { useTexts, type Texts } from '../i18n'
import { Button, Card, Header, Notice, Surface, TextLink, Title } from '../ui/components'
import { useKeys } from '../ui/keys'

interface Props {
  kind: KindValues
  profile: ProfileDescription | null
  onBack: () => void
  onSaved: (kind: KindValues) => void
  onError: (error: unknown) => void
}

export interface Line {
  name: string | null
  label: string
  removed: boolean
}

const lines = (kind: KindValues): Line[] =>
  kind.values.map((v) => ({ name: v.name, label: v.label, removed: false }))

/** What saving sends: every line not removed, a new one without a name. */
export const valuesToSend = (rows: Line[]): ValueChange[] =>
  rows.filter((r) => !r.removed).map(({ name, label }) => ({ name, label }))

/** The lines with one more value, typed as it stands in the document; a blank text adds nothing. */
export const withNewValue = (rows: Line[], typed: string): Line[] =>
  typed.trim() ? [...rows, { name: null, label: typed.trim(), removed: false }] : rows

/** Whether the lines differ from what is stored, so leaving would lose them. */
export const unsaved = (kind: KindValues, rows: Line[]): boolean =>
  JSON.stringify(rows) !== JSON.stringify(lines(kind))

/** What back or Esc does: leave at once, or ask first while lines are unsaved. */
export const onBackPressed = (kind: KindValues, rows: Line[]): 'leave' | 'ask' =>
  unsaved(kind, rows) ? 'ask' : 'leave'

/** What Esc does: close an open question first, otherwise the same as back. */
export const onEscape = (asking: boolean, kind: KindValues, rows: Line[]): 'close' | 'leave' | 'ask' =>
  asking ? 'close' : onBackPressed(kind, rows)

/** The text for a change the sidecar refused, or null for any other error. */
export function kindRefusal(error: unknown, texts: Texts): string | null {
  if (!(error instanceof SubstraktError) || !error.reason) return null
  return texts.kinds.refused[error.reason] ?? null
}

/** The lines of a kind and saving them, with the answer the sidecar gave. */
function useKindLines({ kind, onSaved, onError }: Pick<Props, 'kind' | 'onSaved' | 'onError'>) {
  const texts = useTexts()
  const [rows, setRows] = useState<Line[]>(() => lines(kind))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)
  const change = (next: (before: Line[]) => Line[]) => {
    setRows(next)
    setSaved(false)
    setRefusal(null)
  }
  const save = async () => {
    setSaving(true)
    setRefusal(null)
    try {
      const stored = await api.changeKindValues(kind.name, valuesToSend(rows))
      setRows(lines(stored))
      setSaved(true)
      onSaved(stored)
    } catch (error) {
      const text = kindRefusal(error, texts)
      if (text) setRefusal(text)
      else onError(error)
    } finally {
      setSaving(false)
    }
  }
  return { rows, change, save, saving, saved, refusal }
}

export function KindView({ kind, profile, onBack, onSaved, onError }: Props) {
  const { rows, change, save, saving, saved, refusal } = useKindLines({ kind, onSaved, onError })
  const [asking, setAsking] = useState(false)
  const back = () => (onBackPressed(kind, rows) === 'leave' ? onBack() : setAsking(true))
  useKeys(saving ? null : () => void save(), () => {
    const step = onEscape(asking, kind, rows)
    if (step === 'leave') onBack()
    else setAsking(step === 'ask')
  })
  return (
    <KindScreen
      kind={kind}
      profile={profile}
      rows={rows}
      asking={asking}
      saving={saving}
      saved={saved}
      refusal={refusal}
      onChange={change}
      onSave={() => void save()}
      onBack={back}
      onDiscard={onBack}
      onKeepEditing={() => setAsking(false)}
    />
  )
}

/** The screen of one kind in a given state; KindView holds the state. */
export function KindScreen({ kind, profile, rows, asking, saving, saved, refusal, onChange, onSave, onBack, onDiscard, onKeepEditing }: {
  kind: KindValues
  profile: ProfileDescription | null
  rows: Line[]
  asking: boolean
  saving: boolean
  saved: boolean
  refusal: string | null
  onChange: (next: (before: Line[]) => Line[]) => void
  onSave: () => void
  onBack: () => void
  onDiscard: () => void
  onKeepEditing: () => void
}) {
  const t = useTexts().kinds
  const change = onChange
  const handedOver = new Set(profile?.kinds.find((k) => k.name === kind.name)?.values.map((v) => v.name))
  return (
    <Surface>
      <Button variant="quiet" onClick={onBack} className="mb-2.5 !px-2.5 !py-1.5">
        <ArrowLeft size={16} />
        {t.back}
      </Button>
      {asking && <LeaveQuestion onKeepEditing={onKeepEditing} onDiscard={onDiscard} />}
      <Header>
        <Title subtitle={t.subtitle}>{t.kindTitle(kind.title)}</Title>
      </Header>
      <Card className="overflow-hidden">
        {rows.map((row, index) => (
          <ValueLine
            key={row.name ?? `new-${index}`}
            row={row}
            target={row.name !== null && handedOver.has(row.name) ? (profile?.title ?? null) : null}
            onChange={(edit) => change((before) => before.map((r, i) => (i === index ? { ...r, ...edit } : r)))}
          />
        ))}
        <NewValue onAdd={(typed) => change((before) => withNewValue(before, typed))} />
      </Card>
      <Outcome refusal={refusal} saved={saved} />
      <div className="mt-6 flex items-center justify-between gap-4">
        <span className="text-[13px] text-ink-3">{t.renameHint}</span>
        <Button variant="primary" large onClick={onSave} disabled={saving}>
          {t.save}
        </Button>
      </div>
    </Surface>
  )
}

/** The question before unsaved lines are lost, next to the back link that asked it. */
function LeaveQuestion({ onKeepEditing, onDiscard }: { onKeepEditing: () => void; onDiscard: () => void }) {
  const t = useTexts().kinds
  return (
    <div role="alertdialog" aria-label={t.leaveQuestion} className="mb-4">
      <Notice tone="waiting" symbol={<AlertCircle size={14} />}>
        {t.leaveQuestion}
        <span className="ml-3 inline-flex gap-4">
          <TextLink onClick={onKeepEditing}>{t.keepEditing}</TextLink>
          <TextLink onClick={onDiscard}>{t.discard}</TextLink>
        </span>
      </Notice>
    </div>
  )
}

/** What saving answered, above the save button: a refusal or the confirmation. */
function Outcome({ refusal, saved }: { refusal: string | null; saved: boolean }) {
  const t = useTexts().kinds
  if (refusal) {
    return (
      <Notice tone="waiting" symbol={<AlertCircle size={14} />} className="mt-4">
        {refusal}
      </Notice>
    )
  }
  if (!saved) return null
  return (
    <div role="status" className="mt-4">
      <Notice tone="good" symbol={<Check size={14} />}>
        {t.saved}
      </Notice>
    </div>
  )
}

/** One value: its label to rename, where it goes, and remove or restore. */
export function ValueLine({ row, target, onChange }: {
  row: Line
  target: string | null
  onChange: (edit: Partial<Line>) => void
}) {
  const t = useTexts().kinds
  return (
    <div className="border-b border-line px-6 py-3">
      <div className="flex items-center gap-4">
        <input
          type="text"
          value={row.label}
          disabled={row.removed}
          aria-label={row.label}
          spellCheck={false}
          onChange={(e) => onChange({ label: e.target.value })}
          className={[
            'min-w-0 flex-1 rounded-sm border border-transparent bg-transparent px-2 py-1.5',
            'text-[14px] hover:border-line-2 focus:border-line-2 focus:bg-card-2',
            row.removed ? 'text-ink-3 line-through' : '',
          ].join(' ')}
        />
        <span className={['shrink-0 text-[12.5px]', target ? 'text-accent' : 'text-ink-3'].join(' ')}>
          {target ? t.goesTo(target) : t.onlyShown}
        </span>
        <TextLink onClick={() => onChange({ removed: !row.removed })}>
          {row.removed ? t.restore : t.remove}
        </TextLink>
      </div>
      {row.removed && target && <p className="mt-1.5 px-2 text-[12.5px] text-warn">{t.warning(target)}</p>}
    </div>
  )
}

/** The last line: a new value, named as it stands in the document. */
function NewValue({ onAdd }: { onAdd: (typed: string) => void }) {
  const t = useTexts().kinds
  const [typed, setTyped] = useState('')
  const add = () => {
    onAdd(typed)
    setTyped('')
  }
  return (
    <div className="flex items-center gap-4 px-6 py-3">
      <input
        type="text"
        value={typed}
        placeholder={t.newPlaceholder}
        aria-label={t.newPlaceholder}
        spellCheck={false}
        onChange={(e) => setTyped(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') add()
        }}
        className="min-w-0 flex-1 rounded-sm border border-dashed border-line-2 bg-transparent px-2 py-1.5 text-[14px] placeholder:text-ink-3"
      />
      <span className="shrink-0 text-[12.5px] text-ink-3">{t.newHint}</span>
      <TextLink onClick={add}>{t.add}</TextLink>
    </div>
  )
}
