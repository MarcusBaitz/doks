/**
 * Review presents one document and one decision at a time. Entries from the
 * watched folder come first, because their state lives in the sidecar and a
 * job waits on them; documents opened by hand follow. Technical evidence
 * becomes a plain explanation of what the clerk needs to check.
 */

import { AlertCircle, Check } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import type {
  DocumentInfo,
  ExtractionResult,
  InboxEntry,
  InboxSettings,
  ProfileKind,
} from '../api/types'
import { useLanguage, useTexts, type Texts } from '../i18n'
import { Surface, Card, Button, Empty, Key, TextLink, Title } from '../ui/components'
import { timeOfDay } from '../ui/format'
import { useKeys } from '../ui/keys'
import { ViewerHost } from '../viewer/ViewerHost'
import { displayName, openValues, type DocumentRecord, type Session } from '../state/session'
import { InboxReview, SameContent } from './InboxReview'

interface Props {
  /** The entry a link from Overview names; without it the first waiting entry. */
  entryId?: number | null
  session: Session
  onError: (error: unknown) => void
  onFinish: () => void
}

/** How often the list of entries is read again while Review is open. */
const POLL_MS = 5000

export function Review(props: Props) {
  const { onError } = props
  const { entries, settings, refresh } = useInbox(onError)
  // Entries the clerk put off; they wait again the next time Review opens.
  const [later, setLater] = useState<number[]>([])
  const { entry, first, waiting } = pick(entries, props.entryId ?? null, later)
  const kinds = useKinds(entry?.profile ?? null, onError)
  const document = useDocument(entry?.file_path ?? null, onError)
  const firstDocument = useDocument(first?.file_path ?? null, onError)

  // Every answer, also a refusal, reads the entries again, so the screen shows what is stored.
  const after = <T,>(work: Promise<T>) => work.finally(() => void refresh().catch(onError))

  if (entry?.state === 'duplicate')
    return <SameContent entry={entry} first={first} document={document} firstDocument={firstDocument} onFinish={props.onFinish} onError={onError} />
  // Documents read by hand are no longer reviewed here (decision 2); SessionReview stays unused.
  if (!entry) return <EmptyReview target={target(settings)} onFinish={props.onFinish} />
  if (!kinds) return null
  return (
    <InboxReview
      // A new kind starts the decision anew: its values and questions are others.
      key={`${entry.id}:${entry.kind}`}
      entry={entry}
      position={{ n: waiting.indexOf(entry) + 1, total: waiting.length }}
      kinds={kinds}
      target={target(settings)}
      document={document}
      first={first && { entry: first, document: firstDocument }}
      onCorrect={(c) => after(api.correctInboxEntry(entry.id, c))}
      onDecide={(same) => after(api.decideDuplicate(entry.id, same))}
      onApprove={() => after(api.approveInboxEntry(entry.id))}
      onLater={() => setLater([...later, entry.id])}
      onBack={props.onFinish}
      onError={onError}
    />
  )
}

/**
 * The entry Review shows and the one read first beside it: the entry asked for
 * while it waits or has the same bytes as another, else the first waiting one.
 */
export function pick(entries: InboxEntry[], asked: number | null, later: number[]) {
  const waiting = entries.filter((e) => e.state === 'waiting' && !later.includes(e.id))
  const wanted = entries.find((e) => e.id === asked)
  const entry = wanted && (wanted.state === 'duplicate' || waiting.includes(wanted)) ? wanted : waiting[0] ?? null
  const firstId =
    entry?.state === 'duplicate' ? entry.duplicate_of
    : entry?.duplicate_decision === null ? entry.possible_duplicate_of
    : null
  const first = (firstId != null && entries.find((e) => e.id === firstId)) || null
  return { entry, first, waiting }
}

/** The entries of the watched folder, read again every few seconds while Review is open. */
function useInbox(onError: (error: unknown) => void) {
  const [entries, setEntries] = useState<InboxEntry[]>([])
  const [settings, setSettings] = useState<InboxSettings | null>(null)
  const refresh = useCallback(() => api.inboxEntries().then(setEntries), [])
  useEffect(() => {
    refresh().catch(onError)
    api.inboxSettings().then(setSettings).catch(onError)
    const timer = window.setInterval(() => void refresh().catch(onError), POLL_MS)
    return () => window.clearInterval(timer)
  }, [refresh, onError])
  return { entries, settings, refresh }
}

/** The kinds of a profile, read once per profile. */
function useKinds(profile: string | null, onError: (error: unknown) => void): ProfileKind[] | null {
  const [kinds, setKinds] = useState<Record<string, ProfileKind[]>>({})
  useEffect(() => {
    if (!profile || kinds[profile]) return
    api
      .profileKinds(profile)
      .then((k) => setKinds((all) => ({ ...all, [profile]: k })))
      .catch(onError)
  }, [profile, kinds, onError])
  return (profile && kinds[profile]) || null
}

/** The title of the target, from the active profile or the only one there is. */
export function target(settings: InboxSettings | null): string | null {
  if (!settings) return null
  const { profiles, profile } = settings
  return (profiles.find((p) => p.name === profile) ?? (profiles.length === 1 ? profiles[0] : null))
    ?.title ?? null
}

/** Loads the file of an entry for the viewer and releases it when the path changes. */
function useDocument(path: string | null, onError: (error: unknown) => void): DocumentInfo | null {
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  useEffect(() => {
    if (!path) return
    let gone = false
    let id: string | null = null
    api
      .loadDocument(path)
      .then((d) => {
        if (gone) return api.closeDocument(d.id)
        id = d.id
        setLoaded({ path, document: d })
      })
      .catch(onError)
    return () => {
      gone = true
      setLoaded(null)
      if (id) api.closeDocument(id).catch(onError)
    }
  }, [path, onError])
  return documentFor(loaded, path)
}

interface Loaded {
  path: string
  document: DocumentInfo
}

/**
 * The document opened for this path, or none. The cleanup closes the old
 * document only after the render for the next entry, so the next entry must
 * not see it, or the viewer asks for pages of a closed document.
 */
export function documentFor(loaded: Loaded | null, path: string | null): DocumentInfo | null {
  return loaded && loaded.path === path ? loaded.document : null
}

/**
 * Documents opened by hand, held in the session until they are settled. No place leads here
 * since the decision in docs/decisions.md, “Interface clarity”; the code stays until the owner decides on the path.
 */
export function SessionReview({
  session,
  onError,
  onFinish,
  target,
}: Props & { target: string | null }) {
  const texts = useTexts()
  const [language] = useLanguage()
  const [change, setChanging] = useState<string | null>(null)
  const [inputValue, setInputValue] = useState('')

  const queue = useMemo(
    () => session.records.filter((a) => a.state === 'waiting' && openValues(a).length > 0),
    [session.records],
  )

  // Oldest first, so an already waiting document does not wait longer.
  const record = queue[queue.length - 1]
  const openItem = record ? openValues(record) : []
  const question = openItem[0]

  /** Completes one value and the document when no other value is open. */
  const complete = useCallback(
    (patch: Partial<DocumentRecord>) => {
      if (!record) return
      const next = { ...record, ...patch }
      const rest = openValues(next)
      session.change(record.id, {
        ...patch,
        ...(rest.length === 0 ? { state: 'read' as const } : {}),
      })
      setChanging(null)
      setInputValue('')
    },
    [record, session],
  )

  const confirm = useCallback(() => {
    if (!record || !question) return
    complete({ confirmed: [...record.confirmed, question.field] })
  }, [record, question, complete])

  const missingFromDocument = useCallback(() => {
    if (!record || !question) return
    complete({ missing: [...record.missing, question.field] })
  }, [record, question, complete])

  const accept = useCallback(() => {
    if (!record || !question) return
    const valueText = inputValue.trim()
    if (!valueText) return
    complete({ corrections: { ...record.corrections, [question.field]: valueText } })
  }, [record, question, inputValue, complete])

  // Enter confirms unless an input owns it; Escape leaves the queue.
  useEffect(() => {
    const keyHandler = (e: KeyboardEvent) => {
      const targetElement = e.target as HTMLElement | null
      const inInput = targetElement !== null && ['INPUT', 'TEXTAREA'].includes(targetElement.tagName)

      if (e.key === 'Enter' && !inInput && question) {
        e.preventDefault()
        confirm()
      } else if (e.key === 'Escape') {
        if (change) setChanging(null)
        else onFinish()
      }
    }
    window.addEventListener('keydown', keyHandler)
    return () => window.removeEventListener('keydown', keyHandler)
  }, [question, change, confirm, onFinish])

  if (!record || !question) return <EmptyReview target={target} onFinish={onFinish} />

  const name = displayName(record.fields, question.field)
  const valueText = question.value?.trim()
  const remaining = record.results.filter((e) => e.field !== question.field)

  return (
    <div className="flex h-full min-h-0">
      <div className="min-w-0 flex-1">
        <ViewerHost
          document={record.document}
          highlights={[]}
          onHighlights={() => undefined}
          onError={onError}
          highlighted={question.locator}
          readOnly
          labels="never"
        />
      </div>

      <aside className="flex w-[432px] shrink-0 flex-col border-l border-line bg-panel">
        <div className="border-b border-line px-7 pt-6 pb-5">
          <div className="flex items-center gap-2.5 text-[12.5px] text-ink-3">
            {texts.review.documentOf(
              queue.length - queue.indexOf(record),
              queue.length,
            )}
            <span className="ml-auto flex gap-1">
              {openItem.map((e, i) => (
                <span
                  key={e.field}
                  className={[
                    'h-[3px] w-4 rounded-full',
                    i === 0 ? 'bg-ink' : 'bg-line-2',
                  ].join(' ')}
                />
              ))}
            </span>
          </div>
          <p className="mt-2.5 truncate font-semibold tracking-[-0.01em]">
            {record.fileName}
          </p>
          <p className="mt-0.5 text-[12.5px] text-ink-3">
            {record.template} · {texts.review.readAt(timeOfDay(record.readAt, language))}
          </p>
        </div>

        <div className="border-b border-line px-7 py-7">
          <p className="flex items-center gap-2 text-[13px] font-semibold text-warn">
            <AlertCircle size={15} aria-hidden="true" />
            {texts.review.unclear}
          </p>

          <p className="mt-5 text-[13px] text-ink-2">{name}</p>

          {change === question.field ? (
            <>
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    accept()
                  }
                }}
                spellCheck={false}
                /* Choosing Change moves focus directly to the intended input. */
                autoFocus
                className="mt-1.5 w-full rounded-md border border-line-2 bg-card px-4 py-3.5 text-[21px] font-semibold tracking-[-0.025em]"
              />
              <div className="mt-6 flex gap-2">
                <Button
                  variant="primary"
                  large
                  className="flex-1"
                  disabled={!inputValue.trim()}
                  onClick={accept}
                >
                  {texts.review.accept}
                </Button>
                <Button large onClick={() => setChanging(null)}>
                  {texts.review.discard}
                </Button>
              </div>
              <p className="mt-3.5 text-center text-[12.5px] text-ink-3">
                {texts.review.appliesHere}
              </p>
            </>
          ) : (
            <>
              <p
                className={[
                  'mt-1.5 rounded-md border border-line-2 bg-card px-4 py-3.5',
                  'text-[21px] leading-snug font-semibold tracking-[-0.025em]',
                  valueText ? '' : 'text-ink-3',
                ].join(' ')}
              >
                {valueText || texts.review.none}
              </p>

              <p className="mt-3 text-[12.5px] leading-relaxed text-ink-3">
                {reason(question, texts)}
              </p>

              <div className="mt-6 flex gap-2">
                <Button variant="primary" large className="flex-1" onClick={confirm} autoFocus>
                  {texts.review.looksRight}
                  <Key>{texts.keys.enter}</Key>
                </Button>
                <Button
                  large
                  onClick={() => {
                    setChanging(question.field)
                    setInputValue(valueText ?? '')
                  }}
                >
                  {texts.review.change}
                </Button>
              </div>

              <p className="mt-3.5 text-center text-[12.5px] text-ink-3">
                <TextLink onClick={missingFromDocument}>{texts.review.isMissing}</TextLink>
              </p>
            </>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-7 pt-6 pb-10">
          <h2 className="mb-4 text-[13px] font-semibold text-ink-3">
            {texts.review.rest}
          </h2>

          {remaining.length === 0 ? (
            <p className="text-[13px] text-ink-3">{texts.review.noMore}</p>
          ) : (
            remaining.map((e) => {
              const corrected = record.corrections[e.field]
              const isMissing = record.missing.includes(e.field)
              const displayValue = corrected ?? e.value?.trim()
              return (
                <div
                  key={e.field}
                  className="flex items-baseline gap-4 border-b border-line py-2.5 text-[13.5px] last:border-b-0"
                >
                  <span className="w-[136px] shrink-0 text-ink-2">
                    {displayName(record.fields, e.field)}
                  </span>
                  <span
                    className={[
                      'min-w-0 flex-1 font-medium',
                      displayValue && !isMissing ? '' : 'text-ink-3',
                    ].join(' ')}
                  >
                    {isMissing ? texts.review.isMissing : displayValue || texts.review.none}
                  </span>
                  {(e.grounded || corrected) && (
                    <Check size={13} className="shrink-0 self-center text-good" />
                  )}
                </div>
              )
            })
          )}
        </div>
      </aside>
    </div>
  )
}

/** Converts a technical result note into a plain review reason. */
function reason(e: ExtractionResult, texts: Texts): string {
  const w = texts.review.reason
  if (!e.value?.trim()) return w.noValue
  if (!e.locator) return w.noEvidence
  if (e.note.includes('text recognition')) return w.weak
  if (e.note.includes('does not match type')) return w.type
  return w.uncertain
}

/** Nothing waits: the way back to the overview, where approved documents are listed. */
function EmptyReview({ target, onFinish }: { target: string | null; onFinish: () => void }) {
  const t = useTexts()
  useKeys(onFinish, onFinish)
  return (
    <Surface>
      <Title subtitle={t.inboxReview.emptyDetail}>{t.review.empty}</Title>
      <Card className="mt-8">
        <Empty
          title={t.inboxReview.emptyCard}
          {...(target && { detail: t.inboxReview.emptyCardDetail(target) })}
          action={
            <Button variant="primary" onClick={onFinish}>
              {t.inboxReview.toOverview}
            </Button>
          }
        />
      </Card>
    </Surface>
  )
}
