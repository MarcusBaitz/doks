/**
 * Review of one entry from the watched folder: the document on the left, one
 * decision on the right. What the clerk changes is stored with the entry in
 * the sidecar at once, so nothing typed lives only in this screen; a refusal
 * names its reason and leaves the typed text in place.
 */

import { useCallback, useMemo, useState, type ReactNode } from 'react'

import { SubstraktError } from '../api/client'
import type {
  DocumentInfo,
  ExtractionResult,
  InboxCorrection,
  InboxEntry,
  KindValue,
  ProfileKind,
} from '../api/types'
import { errorText, useTexts, type Texts } from '../i18n'
import { Button, Key, Notice, OPTION, SELECT, TextLink } from '../ui/components'
import { useKeys } from '../ui/keys'
import { ViewerHost } from '../viewer/ViewerHost'
import { itemText, parseItem, type Words } from './HandOver'

/** Errors a person can act on; every other error goes to the shell's banner. */
const REFUSALS = ['correction-refused', 'approval-refused', 'inbox-entry-unknown']

const HEADING = 'text-[24px] font-semibold tracking-[-0.03em]'
const DETAIL = 'mt-3 text-[13px] leading-relaxed text-ink-2'

interface Props {
  entry: InboxEntry
  position: { n: number; total: number }
  /** The kinds of the entry's profile. */
  kinds: ProfileKind[]
  /** The title of the target, for a refusal of the hand-over format. */
  target?: string | null
  document: DocumentInfo | null
  /** The entry read first, while this one is an undecided possible duplicate. */
  first: { entry: InboxEntry; document: DocumentInfo | null } | null
  onCorrect: (correction: InboxCorrection) => Promise<unknown>
  onDecide: (same: boolean) => Promise<unknown>
  onApprove: () => Promise<unknown>
  onLater: () => void
  /** Escape: back to Overview. */
  onBack: () => void
  onError: (error: unknown) => void
}

/** A change the clerk tries: whether one is running, the refusal it met, and how to try one. */
interface Attempt {
  busy: boolean
  notice: ReactNode
  run: (work: () => Promise<unknown>) => Promise<boolean>
}

export function InboxReview(props: Props) {
  const { entry, kinds, first } = props
  const words = useMemo(() => ({ kinds, target: props.target ?? '' }), [kinds, props.target])
  const attempt = useAttempt(props.onError, entry.kind ?? '', words)
  const [editing, setEditing] = useState<string | null>(null)
  // The row under „Weitere Angaben“ whose input is open.
  const [row, setRow] = useState<string | null>(null)
  // Optional values the clerk marked as missing; they never block an approval.
  const [skipped, setSkipped] = useState<string[]>([])
  const kind = kinds.find((k) => k.name === entry.kind) ?? null
  const results = new Map(entry.values.map((r) => [r.field, r]))
  const { unanswered, answer } = useAnswers(kind, results)
  const question = kind && nextQuestion(kind.values, results, skipped, editing, unanswered)
  const waits = kind ? waiting(kind.values, results, skipped, unanswered).map((v) => v.name) : []
  const left = waits.length
  const shown = shownValue(row, question?.name ?? null, results)
  // The question speaks of a mark only while the page shows its own frame (Z4.1).
  const marked = question !== null && shown === question.name
  const saveRow = (name: string, value: string) =>
    attempt.run(() => props.onCorrect(confirmation(name, value, results.get(name)))).then((saved) => {
      if (!saved) return
      answer(name)
      setSkipped((all) => all.filter((n) => n !== name))
      setRow(null)
    })
  const rows = (values: KindValue[]) => (
    <ValueRows values={values} results={results} skipped={skipped} changed={entry.changed} open={row}
      current={question?.name ?? null} onOpen={setRow} onClose={() => setRow(null)} onSave={saveRow} waiting={waits} />
  )

  let panel
  if (first) panel = <DuplicatePanel entry={entry} first={first.entry} kinds={kinds} attempt={attempt} onDecide={props.onDecide} onBack={props.onBack} />
  else if (!kind) panel = <NoKindPanel kinds={kinds} attempt={attempt} onRead={(name) => props.onCorrect({ kind: name })} onLater={props.onLater} onBack={props.onBack} />
  else if (question)
    panel = (
      <QuestionPanel key={question.name} question={question} result={results.get(question.name)} editing={editing === question.name} attempt={attempt} left={left} marked={marked}
        onSave={(value) => props.onCorrect(confirmation(question.name, value, results.get(question.name))).then(() => { answer(question.name); setRow(null) })}
        onEdit={setEditing} onBack={props.onBack} onSkip={() => { setSkipped([...skipped, question.name]); answer(question.name) }}
        // Every value has its row, the question's too: each „?“ below matches the count above, and any value can be corrected in place (Z2.1, Z6.2).
        rest={rows(kind.values)} />
    )
  else panel = <SettledPanel kind={kind} entry={entry} selected={row} attempt={attempt} onApprove={props.onApprove} onEdit={setEditing} onLater={props.onLater} onBack={props.onBack} rows={rows(kind.values)} />

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 gap-px bg-line">
        {first && <Paper caption="firstRead" entry={first.entry} document={first.document} onError={props.onError} />}
        <Paper caption={first ? 'nowRead' : null} entry={entry} document={props.document} highlighted={(shown && results.get(shown)?.locator) || null} onError={props.onError} />
      </div>
      <aside className="flex w-[480px] shrink-0 flex-col overflow-y-auto border-l border-line bg-panel p-7">
        <Header entry={entry} position={props.position} kinds={kinds} kind={kind} choose={!first} attempt={attempt} onCorrect={props.onCorrect} />
        {panel}
      </aside>
    </div>
  )
}

/** A file with the same bytes as one read first: both side by side, and nothing to decide. */
export function SameContent(props: {
  entry: InboxEntry
  first: InboxEntry | null
  document: DocumentInfo | null
  firstDocument: DocumentInfo | null
  onFinish: () => void
  onError: (error: unknown) => void
}) {
  const t = useTexts().inboxReview
  useKeys(props.onFinish, props.onFinish)
  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 gap-px bg-line">
        {props.first && <Paper caption="firstRead" entry={props.first} document={props.firstDocument} onError={props.onError} />}
        <Paper caption="nowRead" entry={props.entry} document={props.document} onError={props.onError} />
      </div>
      <aside className="flex w-[480px] shrink-0 flex-col overflow-y-auto border-l border-line bg-panel p-7">
        <h1 className={`mt-1.5 ${HEADING}`}>{t.identical}</h1>
        <p className={`${DETAIL} mb-5`}>{t.identicalDetail}</p>
        <Button variant="primary" large onClick={props.onFinish}>
          {t.toOverview}
        </Button>
      </aside>
    </div>
  )
}

/**
 * Every value unclear when the view opened must be confirmed or corrected in it before the
 * approval (decision 3). Review starts the screen anew for each entry and kind.
 */
function useAnswers(kind: ProfileKind | null, results: Map<string, ExtractionResult>) {
  const [unclear] = useState(() => kind?.values.filter((v) => isOpen(v, results.get(v.name), [])).map((v) => v.name) ?? [])
  const [answered, setAnswered] = useState<string[]>([])
  return {
    unanswered: unclear.filter((name) => !answered.includes(name)),
    answer: (name: string) => setAnswered((all) => [...all, name]),
  }
}

/** Runs a change, shows a refusal as the dictionary's text, and hands every other error on. */
function useAttempt(onError: (error: unknown) => void, kind: string, words: Words): Attempt {
  const texts = useTexts()
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)
  const run = useCallback(
    async (work: () => Promise<unknown>) => {
      setBusy(true)
      setRefusal(null)
      try {
        await work()
        return true
      } catch (error) {
        const text = refusalText(error, texts, kind, words)
        if (text) setRefusal(text)
        else onError(error)
        return false
      } finally {
        setBusy(false)
      }
    },
    [onError, texts, kind, words],
  )
  const notice = refusal && (
    <Notice tone="waiting" className="mt-4">
      <span role="alert">{refusal}</span>
    </Notice>
  )
  return { busy, notice, run }
}

function Header(props: {
  entry: InboxEntry
  position: { n: number; total: number }
  kinds: ProfileKind[]
  kind: ProfileKind | null
  choose: boolean
  attempt: Attempt
  onCorrect: (correction: InboxCorrection) => Promise<unknown>
}) {
  const t = useTexts().inboxReview
  const { entry, kinds, kind, attempt } = props
  // A changed kind arrives as a new entry state, and Review starts this screen anew for it.
  const change = (name: string) => void attempt.run(() => props.onCorrect({ kind: name }))
  return (
    <>
      <p className="text-[12.5px] text-ink-2">{t.documentOf(props.position.n, props.position.total, entry.customer)}</p>
      {/* Without a kind the panel asks for one; a second choice up here would say it twice. */}
      {props.choose && kind && (
        <label className="mt-3.5 mb-6 flex items-center gap-2.5 text-[13px] text-ink-2">
          {t.recognisedAs}
          <select
            value={entry.kind ?? ''}
            disabled={attempt.busy}
            onChange={(e) => change(e.target.value)}
            className={SELECT}
          >
            {kinds.map((k) => (
              <option key={k.name} value={k.name} className={OPTION}>
                {k.title}
              </option>
            ))}
          </select>
        </label>
      )}
    </>
  )
}

function ValueRows(props: {
  values: KindValue[]
  results: Map<string, ExtractionResult>
  skipped: string[]
  changed: string[]
  /** The value the question above asks about. */
  current: string | null
  /** The row whose input is open. */
  open: string | null
  onOpen: (name: string) => void
  onClose: () => void
  /** Saves a row through the same correction as the question above (Z6.1). */
  onSave: (name: string, value: string) => Promise<void>
  /** The values that keep the approval back, by the rule the count above the question follows. */
  waiting: string[]
}) {
  const t = useTexts().inboxReview
  const ROW = 'grid grid-cols-[196px_minmax(0,1fr)_16px] gap-3 text-[13.5px]'
  return (
    <div className="mt-3">
      {props.values.map((v) => {
        const r = props.results.get(v.name)
        const value = r?.value?.trim()
        const missing = props.skipped.includes(v.name) || !value
        const misfit = !missing && mismatch(r)
        if (props.open === v.name)
          return (
            <div key={v.name} data-row="" className={`-mx-2 w-[calc(100%+16px)] rounded-sm bg-card px-2 py-[7px] ${ROW}`}>
              <span className="truncate pt-[5px] text-ink-2">{v.label}</span>
              <div className="col-span-2">
                <RowEditor label={v.label} type={v.json_type} start={missing ? '' : (value ?? '')}
                  onSubmit={(text) => void props.onSave(v.name, text)} onCancel={props.onClose} />
                {misfit && <p className="mt-1.5 text-[12.5px] text-warn">{typeHint(t, v.json_type)}</p>}
                {/* A value without a place says so at its row and never speaks of a mark (Z4.2). */}
                {!r?.locator && <p className="mt-1.5 text-[12.5px] text-ink-2">{t.noPlace}</p>}
              </div>
            </div>
          )
        return (
          <div key={v.name}>
            <button
              data-row=""
              type="button"
              onClick={() => props.onOpen(v.name)}
              aria-current={props.current === v.name || undefined}
              className={`-mx-2 w-[calc(100%+16px)] rounded-sm px-2 py-[7px] text-left whitespace-nowrap hover:bg-card ${props.current === v.name ? 'bg-card' : ''} ${ROW}`}
            >
              <span className="truncate text-ink-2">{v.label}</span>
              <span className={`truncate ${missing ? 'text-ink-3' : ''} ${props.changed.includes(v.name) ? 'font-bold' : ''}`}>
                {missing ? t.missing : value}
              </span>
              {props.waiting.includes(v.name) ? (
                <span role="img" aria-label={t.waitingMark} title={t.waitingMark}
                  className="mt-[3px] flex size-4 items-center justify-center rounded-full bg-warn text-[11px] leading-none font-bold text-card">
                  ?
                </span>
              ) : (
                !missing && r?.grounded && (
                  <span role="img" className="text-good" aria-label={t.settledMark} title={t.settledMark}>
                    ✓
                  </span>
                )
              )}
            </button>
            {/* A typed value that does not fit its type keeps its text and says so beside it. */}
            {misfit && <p className="mb-1 pl-[208px] text-[12.5px] text-warn">{typeHint(t, v.json_type)}</p>}
          </div>
        )
      })}
    </div>
  )
}

function DuplicatePanel(props: {
  entry: InboxEntry
  first: InboxEntry
  kinds: ProfileKind[]
  attempt: Attempt
  onDecide: (same: boolean) => Promise<unknown>
  onBack: () => void
}) {
  const t = useTexts().inboxReview
  const { entry, kinds, attempt } = props
  const decide = (same: boolean) => void attempt.run(() => props.onDecide(same))
  // „Same“ is final (R12): Enter takes no step here, a person tabs to the button they mean.
  useKeys(null, props.onBack)
  const kind = kinds.find((k) => k.name === entry.kind)
  const label = (name: string) => kinds.flatMap((k) => k.values).find((v) => v.name === name)?.label ?? name
  const matches = entry.values.filter((r) => r.grounded && same(r, props.first.values))
  return (
    <>
      <h1 className={`mt-1.5 ${HEADING}`}>{t.sameQuestion}</h1>
      {/* The comparison hash matched, so at least one value does. */}
      <p className={`${DETAIL} mb-5`}>{t.sameDetail(Math.max(1, matches.length))}</p>
      <dl className="grid grid-cols-[204px_1fr] gap-x-4 gap-y-1.5 text-[13.5px]">
        {matches.map((r) => (
          <Pair key={r.field} term={label(r.field)} value={r.value ?? ''} />
        ))}
        {kind && <Pair term={t.recognisedAs} value={kind.title} />}
      </dl>
      {attempt.notice}
      <div className="mt-5 flex flex-col">
        <Button variant="primary" large disabled={attempt.busy} onClick={() => decide(true)}>
          {t.same}
        </Button>
        <p className="mt-2 mb-3 text-[12.5px] text-ink-2">{t.sameMeans}</p>
        <Button large disabled={attempt.busy} onClick={() => decide(false)}>
          {t.different}
        </Button>
        <p className="mt-2 text-[12.5px] text-ink-2">{t.differentMeans}</p>
      </div>
    </>
  )
}

function NoKindPanel(props: {
  kinds: ProfileKind[]
  attempt: Attempt
  onRead: (kind: string) => Promise<unknown>
  onLater: () => void
  onBack: () => void
}) {
  const texts = useTexts()
  const t = texts.inboxReview
  const { attempt, onLater } = props
  const [chosen, setChosen] = useState<string | null>(null)
  const read = chosen && !attempt.busy ? () => void attempt.run(() => props.onRead(chosen)) : null
  useKeys(read, props.onBack)
  return (
    <>
      <h1 id="kind-question" className={`mt-6 ${HEADING}`}>{t.noKindQuestion}</h1>
      <p className={DETAIL}>{t.chooseKindDetail}</p>
      <div role="radiogroup" aria-labelledby="kind-question" className="mt-5 flex flex-col gap-2">
        {props.kinds.map((k) => (
          <label
            key={k.name}
            className={`flex cursor-pointer items-center gap-3 rounded-md border bg-card px-4 py-3 text-[14px] ${chosen === k.name ? 'border-ink' : 'border-line-2'}`}
          >
            <input type="radio" name="kind" value={k.name} checked={chosen === k.name} onChange={() => setChosen(k.name)} />
            {k.title}
          </label>
        ))}
      </div>
      {attempt.notice}
      <div className="mt-5 mb-3 flex">
        <Button variant="primary" large className="flex-1" disabled={!read} onClick={() => read?.()}>
          {t.readWith}
          <Key>{texts.keys.enter}</Key>
        </Button>
      </div>
      <p className="text-[13px]">
        <TextLink onClick={onLater}>{t.later}</TextLink>
      </p>
    </>
  )
}

function QuestionPanel(props: {
  question: KindValue; result: ExtractionResult | undefined; editing: boolean; attempt: Attempt; left: number; marked: boolean
  onSave: (value: string) => Promise<unknown>; onEdit: (name: string | null) => void; onBack: () => void; onSkip: () => void; rest: ReactNode
}) {
  const { inboxReview: t, review } = useTexts()
  const { question, attempt } = props
  const read = props.result?.value?.trim() ?? ''
  const typed = useTyped(question.json_type, read)
  const misfit = Boolean(read) && mismatch(props.result)
  // A value without text can only be typed in; one that does not fit its type stays in the input.
  const typing = props.editing || !read || misfit
  const save = async (value: string) => {
    if (await attempt.run(() => props.onSave(value))) props.onEdit(null)
  }
  const accept = () => {
    const text = typed.take()
    if (text) void save(text)
  }
  // Escape first leaves the change, then the screen; typed text is never dropped with the screen (R12).
  const escape = () => (props.editing ? props.onEdit(null) : typing && typed.input.trim() && !misfit ? undefined : props.onBack())
  useKeys(attempt.busy || typing ? null : () => void save(read), escape)
  return (
    <>
      {props.left > 0 && <p className="font-medium text-warn">{t.unclear(props.left)}</p>}
      <h1 className={`mt-1.5 ${HEADING}`}>{question.question || t.questionFor(question.label)}</h1>
      {typing ? (
        <ValueInput label={question.label} typed={typed} onSubmit={accept} />
      ) : (
        <p className="mt-3.5 text-[21px] leading-snug font-semibold tracking-[-0.025em]">{read}</p>
      )}
      {misfit && <p className="mt-2 text-[13px] text-warn">{typeHint(t, question.json_type)}</p>}
      <p className={DETAIL}>{typing && read ? review.appliesHere : reason(props.result, t.reason, props.marked)}</p>
      {attempt.notice}
      <QuestionActions typing={typing} read={read} input={typed.input} busy={attempt.busy} onAccept={accept} onConfirm={() => void save(read)}
        onEdit={(on) => { props.onEdit(on ? question.name : null); typed.reset(read) }} />
      {!question.required && (
        <p className="text-[13px]">
          <TextLink onClick={() => { props.onSkip(); props.onEdit(null) }}>{review.isMissing}</TextLink>
        </p>
      )}
      <h2 className="mt-10 text-[13px] font-semibold text-ink-3">{t.rest}</h2>
      <p className="mt-3 text-[13px] text-ink-2">{t.clickShows}</p>
      {props.rest}
      <ApprovalWaits left={props.left} />
    </>
  )
}

/** The approval, disabled while values wait for a confirmation or correction. */
function ApprovalWaits({ left }: { left: number }) {
  const t = useTexts().inboxReview
  if (left === 0) return null
  return (
    <div className="mt-8 flex flex-col gap-2">
      <Button large disabled>
        {t.approve}
      </Button>
      <p className="text-[12.5px] text-ink-2">{t.approveAfter(left)}</p>
    </div>
  )
}

type Typed = ReturnType<typeof useTyped>

/**
 * What a clerk types for one value. A date takes digits only, the field sets the points, and an
 * impossible or incomplete date is not sent: the hint names the form and the text stays (Z5.2, Z5.3).
 */
function useTyped(type: string, start: string) {
  const [input, setInput] = useState(start)
  const [refused, setRefused] = useState(false)
  const date = type === 'date'
  const onInput = (text: string) => {
    setInput(date ? maskDate(text) : text)
    setRefused(false)
  }
  return {
    input,
    date,
    refused,
    onInput,
    reset: (text: string) => {
      setInput(text)
      setRefused(false)
    },
    /** The text to send, or null while it is empty or an impossible date. */
    take: (): string | null => {
      const text = input.trim()
      if (!text) return null
      if (date && !possibleDate(text)) {
        setRefused(true)
        return null
      }
      return text
    },
  }
}

/** The input of a row in „Weitere Angaben“: Enter saves only this row, Escape closes it as it was (Z6.1, Z6.2). */
function RowEditor(props: { label: string; type: string; start: string; onSubmit: (text: string) => void; onCancel: () => void }) {
  const typed = useTyped(props.type, props.start)
  return (
    <ValueInput label={props.label} typed={typed} small onCancel={props.onCancel}
      onSubmit={() => {
        const text = typed.take()
        if (text) props.onSubmit(text)
      }} />
  )
}

function ValueInput(props: { label: string; typed: Typed; onSubmit: () => void; onCancel?: () => void; small?: boolean }) {
  const t = useTexts().inboxReview
  const { typed } = props
  return (
    <>
      <input
        type="text"
        inputMode={typed.date ? 'numeric' : undefined}
        placeholder={typed.date ? t.dateForm : undefined}
        value={typed.input}
        aria-label={props.label}
        aria-invalid={typed.refused || undefined}
        onChange={(e) => typed.onInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            props.onSubmit()
          } else if (e.key === 'Escape' && props.onCancel) {
            // The row closes and Review stays, so the key goes no further.
            e.preventDefault()
            e.stopPropagation()
            props.onCancel()
          } else if (e.key === 'Backspace' && typed.date && atEnd(e.currentTarget)) {
            // A digit goes together with the point the field set before it.
            e.preventDefault()
            typed.onInput(maskDate(typed.input.replace(/\D/g, '').slice(0, -1)))
          }
        }}
        spellCheck={false}
        /* Choosing Change or a row moves focus directly to the intended input. */
        autoFocus
        className={props.small
          ? 'w-full rounded-sm border border-line-2 bg-card-2 px-2 py-1 text-[13.5px]'
          : 'mt-3.5 w-full rounded-md border border-line-2 bg-card px-4 py-3 text-[21px] font-semibold tracking-[-0.025em]'}
      />
      {typed.refused && (
        <p role="alert" className="mt-1.5 text-[12.5px] text-warn">
          {t.dateHint}
        </p>
      )}
    </>
  )
}

function atEnd(input: HTMLInputElement): boolean {
  return input.selectionStart === input.selectionEnd && (input.selectionEnd ?? input.value.length) === input.value.length
}

function QuestionActions(props: {
  typing: boolean
  read: string
  input: string
  busy: boolean
  onAccept: () => void
  onConfirm: () => void
  onEdit: (on: boolean) => void
}) {
  const texts = useTexts()
  const { typing, read, busy } = props
  const enter = <Key>{texts.keys.enter}</Key>
  return (
    <div className="mt-5 mb-3 flex gap-2">
      <Button
        variant="primary"
        large
        className="flex-1"
        disabled={busy || (typing && !props.input.trim())}
        onClick={typing ? props.onAccept : props.onConfirm}
      >
        {typing ? texts.review.accept : texts.review.looksRight}
        {enter}
      </Button>
      {typing && read && (
        <Button large className="flex-1" onClick={() => props.onEdit(false)}>
          {texts.review.discard}
        </Button>
      )}
      {!typing && (
        <Button large className="flex-1" onClick={() => props.onEdit(true)}>
          {texts.review.change}
        </Button>
      )}
    </div>
  )
}

function SettledPanel(props: {
  kind: ProfileKind; entry: InboxEntry; selected: string | null; attempt: Attempt
  onApprove: () => Promise<unknown>; onEdit: (name: string) => void; onLater: () => void; onBack: () => void; rows: ReactNode
}) {
  const texts = useTexts()
  const t = texts.inboxReview
  const { entry, attempt } = props
  // Enter never approves (decision 3): a run of Enter presses must not become a rubber stamp.
  const approve = () => void attempt.run(props.onApprove)
  useKeys(null, props.onBack)
  const target = changeTarget(props.kind.values, entry.changed, props.selected)
  return (
    <>
      <h1 className={HEADING}>{t.settled}</h1>
      <p className={DETAIL}>{t.settledDetail}</p>
      {props.rows}
      {entry.changed.length > 0 && <p className="mt-3 text-[12.5px] text-ink-2">{t.boldChanged}</p>}
      {attempt.notice}
      <div className="mt-5 mb-3 flex flex-wrap gap-2">
        <Button variant="primary" large className="flex-1" disabled={attempt.busy} onClick={approve}>
          {t.approve}
        </Button>
        {target && (
          <Button large className="flex-1" onClick={() => props.onEdit(target.name)}>
            {t.changeValue(target.label)}
          </Button>
        )}
      </div>
      <p className="text-[12.5px] leading-relaxed text-ink-2">{t.approveMeans}</p>
      <p className="mt-3.5 text-[13px]">
        <TextLink onClick={props.onLater}>{t.later}</TextLink>
      </p>
    </>
  )
}

function Paper(props: {
  caption: 'firstRead' | 'nowRead' | null
  entry: InboxEntry
  document: DocumentInfo | null
  highlighted?: ExtractionResult['locator']
  onError: (error: unknown) => void
}) {
  const t = useTexts().inboxReview
  return (
    <div className="flex min-w-0 flex-1 flex-col bg-bg">
      {props.caption && (
        <p className="shrink-0 truncate px-5 pt-4 pb-2 text-[12.5px] text-ink-2">
          {t[props.caption]} · <span className="font-mono">{props.entry.file_name}</span>
        </p>
      )}
      <div className="min-h-0 flex-1">
        {props.document ? (
          <ViewerHost
            document={props.document}
            highlights={[]}
            onHighlights={() => undefined}
            onError={props.onError}
            highlighted={props.highlighted ?? null}
            readOnly
            labels="never"
          />
        ) : (
          <p className="p-8 text-[13px] text-ink-3">{t.noDocument}</p>
        )}
      </div>
    </div>
  )
}

function Pair({ term, value }: { term: string; value: string }) {
  return (
    <>
      <dt className="whitespace-nowrap text-ink-2">{term}</dt>
      <dd>{value}</dd>
    </>
  )
}

/** The value the change button offers: the one looked at, else one a person changed, else the first. */
export function changeTarget(values: KindValue[], changed: string[], selected: string | null): KindValue | undefined {
  return values.find((v) => v.name === selected) ?? values.find((v) => changed.includes(v.name)) ?? values[0]
}

/**
 * The value being edited, else the first value that waits for the clerk: one that is open,
 * or one that was unclear when the view opened and has not been answered in it.
 */
export function nextQuestion(
  values: KindValue[],
  results: Map<string, ExtractionResult>,
  skipped: string[],
  editing: string | null,
  unanswered: string[] = [],
): KindValue | null {
  return values.find((v) => v.name === editing) ?? waiting(values, results, skipped, unanswered)[0] ?? null
}

/** The values that keep the approval back; the count above the question and below it is theirs. */
export function waiting(values: KindValue[], results: Map<string, ExtractionResult>, skipped: string[], unanswered: string[]): KindValue[] {
  return values.filter((v) => isOpen(v, results.get(v.name), skipped) || unanswered.includes(v.name))
}

/** A value waits for the clerk when an approval needs it, or when it was read without certainty. */
export function isOpen(v: KindValue, r: ExtractionResult | undefined, skipped: string[]): boolean {
  if (skipped.includes(v.name)) return false
  const has = Boolean(r?.value?.trim())
  return v.required ? !(has && r?.grounded) : has && !r?.grounded
}

/** A value as it was read is confirmed and keeps its location; any other text corrects it. */
export function confirmation(name: string, value: string, read: ExtractionResult | undefined): InboxCorrection {
  return value === read?.value?.trim() ? { confirmed: [name] } : { values: { [name]: value } }
}

/** Whether the other entry read the same value under the same name. */
export function same(r: ExtractionResult, others: ExtractionResult[]): boolean {
  const other = others.find((o) => o.field === r.field)
  return other !== undefined && (other.normalized ?? other.value) === (r.normalized ?? r.value)
}

/**
 * Why a value is asked about, in the clerk's words. Only a value whose frame the page shows
 * speaks of a mark; one without a place says so (Z4.1, Z4.2).
 */
export function reason(r: ExtractionResult | undefined, w: Texts['inboxReview']['reason'], marked = true): string {
  if (!r?.value?.trim()) return w.noValue
  if (!r.locator) return w.noLocation
  return marked ? w.unclear : w.unclearUnmarked
}

/**
 * The value whose frame the page shows: an open row with a place in the document, else the
 * question, else the open row. A row without a place never takes the question's frame away.
 */
export function shownValue(row: string | null, question: string | null, results: Map<string, ExtractionResult>): string | null {
  if (row && results.get(row)?.locator) return row
  return question ?? row
}

/** A value a person typed that does not fit its type; it stays unclear until corrected. */
export function mismatch(r: ExtractionResult | undefined): boolean {
  return r?.source === 'manual' && !r.grounded
}

/** The hint for a typed value that does not fit its type. */
function typeHint(t: Texts['inboxReview'], type: string): string {
  return type === 'date' ? t.dateHint : type === 'number' ? t.numberHint : t.typeHint
}

/** The digits of a date as DD.MM.YYYY; the field sets the points, a typed point stands only after day or month. */
export function maskDate(text: string): string {
  const digits = text.replace(/\D/g, '').slice(0, 8)
  const masked = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean).join('.')
  return text.endsWith('.') && (digits.length === 2 || digits.length === 4) ? `${masked}.` : masked
}

/** Whether DD.MM.YYYY names a day of the calendar. */
export function possibleDate(text: string): boolean {
  const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(text)
  if (!m) return false
  const [day, month, year] = [Number(m[1]), Number(m[2]), Number(m[3])]
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}

/**
 * The dictionary's text for a refusal a person can act on, or null for any other error.
 * What the hand-over format refuses follows in words, so the clerk sees what to do.
 */
export function refusalText(
  error: unknown,
  texts: Texts,
  kind: string,
  words: Words,
): string | null {
  if (!(error instanceof SubstraktError) || !REFUSALS.includes(error.key)) return null
  const text = (error.reason && texts.inboxReview.refused[error.reason]) || errorText(texts, error.key, error.message)
  const items = error.items.map((name) => itemText(parseItem(name), kind, words, texts.handOver))
  return [text, ...new Set(items)].join(' ')
}
