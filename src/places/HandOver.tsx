/**
 * The path from Overview to the target: what a hand-over would write, and what importing it did.
 *
 * The simulation shows per customer and per contract, value by value, what the
 * file would hold, from the same run the writer makes, before anything is
 * written; a value the writer would refuse is named in words. The program
 * cannot look into the target, so after the import a person reports per
 * customer whether it worked. Record numbers, field positions and the format
 * name never appear here; the target is named by the title of the profile.
 */

import { ChevronLeft } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { HandOverItem, HandOverPreview, InboxEntry, Job, KindValues } from '../api/types'
import { useLanguage, useTexts, type Texts } from '../i18n'
import { Button, Card, Empty, Header, Notice, Surface, TextInput, Title } from '../ui/components'
import { formatAmount, longDate, timeOfDay } from '../ui/format'
import { useKeys } from '../ui/keys'
import type { InboxView } from './Overview'

type HandOverTexts = Texts['handOver']

/** The customers with a job in this state, sorted; a job without a customer is never handed over. */
export function customersWith(jobs: Job[], state: Job['state']): string[] {
  const names = jobs.flatMap((j) => (j.state === state && j.file.customer !== null ? [j.file.customer] : []))
  return [...new Set(names)].sort((a, b) => a.localeCompare(b))
}

/** What a person typed when the import failed, or null for any other job. */
export function importFailure(job: Job | undefined): string | null {
  const reason = job?.state === 'failed' ? job.transitions.at(-1)?.reason : undefined
  return reason?.startsWith(IMPORT_FAILED) ? reason.slice(IMPORT_FAILED.length) : null
}
const IMPORT_FAILED = 'import-failed: '

/** What names a kind, its title and its values, for the texts of the hand-over. */
export interface Words {
  kinds: KindValues[]
  /** The title of the target, as the profile names it. */
  target: string
}

/** The label of a value of a kind, or a word for “a value” when the profile does not name it. */
function labelOf(words: Words, kind: string, name: string, t: HandOverTexts): string {
  const values = words.kinds.find((k) => k.name === kind)?.values ?? []
  return values.find((v) => v.name === name)?.label ?? t.aValue
}

function kindTitle(words: Words, kind: string): string {
  return words.kinds.find((k) => k.name === kind)?.title ?? kind
}

/** The words of the active profile on Overview. */
export function wordsOf(inbox: InboxView): Words {
  return { kinds: inbox.profile?.kinds ?? [], target: inbox.profile?.title ?? '' }
}

/** An item as a refused approval names it, `name` or `name:field`; the value never travels. */
export function parseItem(text: string): HandOverItem {
  const [item = '', field] = text.split(':')
  return field === undefined ? { item } : { item, field }
}

/**
 * One thing that keeps a document of this kind out of the file, in words.
 * Without its value (a refused approval sends none) the text names the value by its kind.
 */
export function itemText(item: HandOverItem, kind: string, words: Words, t: HandOverTexts): string {
  const value = String(item.value ?? '')
  const { target } = words
  switch (item.item) {
    case 'insurer':
    case 'policy_number':
    case 'policyholder':
    case 'line_of_business':
      return t.missing(labelOf(words, kind, item.item, t))
    case 'insurer_number':
      return t.unknownInsurer(value, target)
    case 'line_of_business_code':
      return t.unknownLine(value, target)
    case 'payment_mode_code':
      return t.unknownPaymentMode(value, target)
    case 'premium_per_payment_period':
      return t.annualOnly
    case 'value_fits_field':
      return t.doesNotFit(labelOf(words, kind, item.field ?? '', t))
    case 'one_contract_per_policy_number':
      return t.twoPolicies
    case 'same_policyholder':
      return t.twoHolders
    case 'kind_not_handed_over':
      return t.kindNotHandedOver(kindTitle(words, value || kind), target)
    default:
      return t.cannotWrite
  }
}

/** Why nothing of a customer can be written; the key stands before a colon. */
export function problemText(problem: string, t: HandOverTexts): string {
  const key = problem.split(':')[0] ?? ''
  return t.problems[key as keyof HandOverTexts['problems']] ?? t.cannotWrite
}

interface HandOverProps {
  inbox: InboxView
  onBack: () => void
  /** Called once the runs were started, to go back to Overview. */
  onWritten: () => void
  onError: (error: unknown) => void
}

/** Asks the sidecar what a run would write per customer, and starts the runs on request. */
export function HandOver({ inbox, onBack, onWritten, onError }: HandOverProps) {
  const [previews, setPreviews] = useState<HandOverPreview[] | null>(null)
  const [writing, setWriting] = useState(false)
  // The inbox is asked again every two seconds; only another set of customers asks again here.
  const customers = customersWith(inbox.jobs, 'pending').join('\n')
  useEffect(() => {
    const names = customers === '' ? [] : customers.split('\n')
    Promise.all(names.map((name) => api.previewHandOver(name)))
      .then(setPreviews)
      .catch(onError)
  }, [customers, onError])
  const write = async () => {
    setWriting(true)
    try {
      // One run per customer, each writing the file of that customer only.
      for (const p of previews ?? []) if (writable(p)) await api.runHandOver(p.customer)
      onWritten()
    } catch (f) {
      onError(f)
    } finally {
      setWriting(false)
    }
  }
  return <HandOverView inbox={inbox} previews={previews} writing={writing} onBack={onBack} onWrite={() => void write()} />
}

const writable = (p: HandOverPreview) => p.problem === null && p.contracts.length > 0

interface ViewProps {
  inbox: InboxView
  /** Null while the sidecar is asked. */
  previews: HandOverPreview[] | null
  writing: boolean
  onBack: () => void
  onWrite: () => void
}

export function HandOverView({ inbox, previews, writing, onBack, onWrite }: ViewProps) {
  const t = useTexts().handOver
  const target = inbox.profile?.title ?? ''
  const ready = !writing && previews?.some(writable) === true
  useKeys(ready ? onWrite : null, onBack)
  return (
    <Surface wide>
      <BackButton onBack={onBack} />
      <Header>
        <Title subtitle={t.subtitle}>{t.title(target)}</Title>
      </Header>
      {previews === null && <p className="text-[13.5px] text-ink-2">{t.preparing}</p>}
      {previews?.length === 0 && (
        <Card>
          <Empty title={t.nothingTitle} detail={t.nothingDetail} />
        </Card>
      )}
      <div className="flex flex-col gap-6">
        {previews?.map((p) => <CustomerCard key={p.customer} preview={p} inbox={inbox} />)}
      </div>
      <div className="mt-7 flex items-center gap-5">
        <p className="flex-1 text-[13px] text-ink-2">
          {t.fileIn} <span className="font-mono">{inbox.settings?.handover_folder ?? ''}</span>.{' '}
          {t.importYourself(target)}
        </p>
        <Button variant="primary" large onClick={onWrite} disabled={!ready}>
          {t.write}
        </Button>
      </div>
    </Surface>
  )
}

export function BackButton({ onBack }: { onBack: () => void }) {
  const texts = useTexts()
  return (
    <Button variant="quiet" onClick={onBack} className="-ml-3 mb-4">
      <ChevronLeft size={15} aria-hidden="true" />
      {texts.places.overview}
    </Button>
  )
}

/** One customer: the contracts the file would hold, and what stays out and why. */
function CustomerCard({ preview, inbox }: { preview: HandOverPreview; inbox: InboxView }) {
  const t = useTexts().handOver
  const jobOf = (id: string) => inbox.jobs.find((j) => j.id === id)
  const documents = preview.contracts.flat().length
  return (
    <Card className="overflow-hidden">
      <div className="px-7 py-5">
        <p className="text-[15px] font-semibold">{preview.customer}</p>
        <p className="mt-0.5 text-[13.5px] text-ink-2">
          {documents > 0 && preview.problem === null ? t.contractsFrom(preview.contracts.length, documents) : t.notYet}
        </p>
      </div>
      {preview.problem === null &&
        preview.contracts.map((ids, i) => (
          <Contract key={ids.join()} jobs={ids.flatMap((id) => jobOf(id) ?? [])} inbox={inbox} open={i === 0} />
        ))}
      <div className="flex flex-col gap-2 px-7 pb-5 empty:hidden">
        {preview.problem !== null && <Notice tone="waiting">{problemText(preview.problem, t)}</Notice>}
        {Object.entries(preview.waiting).map(([id, items]) => {
          const job = jobOf(id)
          return job && <Waiting key={id} job={job} items={items} inbox={inbox} />
        })}
      </div>
    </Card>
  )
}

/** A document the file leaves out; a kind that is not handed over is no warning. */
function Waiting({ job, items, inbox }: { job: Job; items: HandOverItem[]; inbox: InboxView }) {
  const t = useTexts().handOver
  const name = inbox.entries.find((e) => e.id === job.entry_id)?.file_name ?? ''
  const quiet = items.every((i) => i.item === 'kind_not_handed_over')
  return (
    <Notice tone={quiet ? 'accent' : 'waiting'}>
      <b className="font-semibold">{name}</b> · {items.map((i) => itemText(i, job.file.kind, wordsOf(inbox), t)).join(' ')}
    </Notice>
  )
}

/** The heading of a contract: the profile's text columns of its first document. */
function contractTitle(entry: InboxEntry | undefined, inbox: InboxView): string {
  const names = Object.keys(inbox.profile?.overview_columns ?? {})
  const values = names.map((n) => entry?.values.find((v) => v.field === n))
  return values.flatMap((v) => (v?.value && typeof v.normalized !== 'number' ? [v.value] : [])).join(' · ')
}

/** One row of the simulation: the name in the target, the value, and where it comes from. */
interface Row {
  key: string
  name: string
  value: string
  source: string
  changed: boolean
}

function rowsOf(job: Job, inbox: InboxView, t: HandOverTexts, language: 'de' | 'en'): Row[] {
  const entry = inbox.entries.find((e) => e.id === job.entry_id)
  const kind = inbox.profile?.kinds.find((k) => k.name === job.file.kind)
  const source = t.source(kindTitle(wordsOf(inbox), job.file.kind), job.file.pages.first)
  return Object.entries(job.file.values).map(([name, value]) => {
    const own = kind?.values.find((v) => v.target_name === name)?.name ?? ''
    const changed = entry?.changed.includes(own) ?? false
    const shown = typeof value.normalized === 'number' ? formatAmount(value.normalized, language) : value.text
    return { key: `${job.id}:${name}`, name, value: shown, source: changed ? `${source} · ${t.changed}` : source, changed }
  })
}

function Contract({ jobs, inbox, open }: { jobs: Job[]; inbox: InboxView; open: boolean }) {
  const t = useTexts().handOver
  const [language] = useLanguage()
  const first = inbox.entries.find((e) => e.id === jobs[0]?.entry_id)
  return (
    <details open={open} className="group border-t border-line">
      <summary className="flex cursor-pointer list-none items-center gap-1 px-7 py-3.5 font-medium">
        <span className="inline-block w-4 text-ink-3 transition-transform group-open:rotate-90">›</span>
        {contractTitle(first, inbox)}
      </summary>
      <table className="tabular-number w-full table-fixed border-collapse text-[13.5px]">
        <tbody>
          {jobs.flatMap((job) => rowsOf(job, inbox, t, language)).map((row) => (
            <tr key={row.key} className="border-t border-line">
              <td className="w-[270px] truncate py-2 pl-7 text-ink-2">{row.name}</td>
              <td className={['truncate py-2', row.changed ? 'font-bold' : ''].join(' ')}>{row.value}</td>
              <td className="w-[300px] truncate py-2 pr-7 text-[12.5px] text-ink-3">{row.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}

// --- Feedback after the import ------------------------------------------------

/** What a person reported for one customer; an unanswered customer stays open. */
export interface Answer {
  imported: boolean
  reason: string
}

/** A report can be saved once something is answered and every failure has a reason. */
export function canSave(answers: Record<string, Answer>): boolean {
  const given = Object.values(answers)
  return given.length > 0 && given.every((a) => a.imported || a.reason.trim() !== '')
}

interface FeedbackProps {
  inbox: InboxView
  onBack: () => void
  onSaved: () => void
  onError: (error: unknown) => void
}

/** Stores per customer what importing the hand-over did. */
export function Feedback({ inbox, onBack, onSaved, onError }: FeedbackProps) {
  const [answers, setAnswers] = useState<Record<string, Answer>>({})
  const [saving, setSaving] = useState(false)
  const save = async () => {
    setSaving(true)
    try {
      for (const [customer, a] of Object.entries(answers))
        await api.reportImport(customer, a.imported, a.imported ? '' : a.reason)
      onSaved()
    } catch (f) {
      onError(f)
    } finally {
      setSaving(false)
    }
  }
  return (
    <FeedbackView
      inbox={inbox}
      answers={answers}
      saving={saving}
      onAnswer={(customer, answer) => setAnswers((before) => ({ ...before, [customer]: answer }))}
      onBack={onBack}
      onSave={() => void save()}
    />
  )
}

interface FeedbackViewProps {
  inbox: InboxView
  answers: Record<string, Answer>
  saving: boolean
  onAnswer: (customer: string, answer: Answer) => void
  onBack: () => void
  onSave: () => void
}

const FEEDBACK_GRID = { gridTemplateColumns: 'minmax(0,1fr) 260px 140px 170px' }

export function FeedbackView({ inbox, answers, saving, onAnswer, onBack, onSave }: FeedbackViewProps) {
  const t = useTexts().handOver
  const target = inbox.profile?.title ?? ''
  const ready = !saving && canSave(answers)
  useKeys(ready ? onSave : null, onBack)
  return (
    <Surface>
      <BackButton onBack={onBack} />
      <Header>
        <Title subtitle={t.feedbackSubtitle(target)}>{t.feedbackTitle(target)}</Title>
      </Header>
      <Card className="overflow-hidden">
        <div className="grid gap-x-3 border-b border-line px-7 py-2.5 text-[12.5px] text-ink-3" style={FEEDBACK_GRID}>
          <span>{t.customer}</span>
          <span>{t.handOverColumn}</span>
          <span>{t.done}</span>
          <span>{t.failed}</span>
        </div>
        {customersWith(inbox.jobs, 'handed_over').map((name) => (
          <FeedbackRow key={name} customer={name} inbox={inbox} answer={answers[name]} onAnswer={(a) => onAnswer(name, a)} />
        ))}
      </Card>
      <div className="mt-7 flex items-center gap-5">
        <p className="flex-1 text-[13px] text-ink-2">{t.feedbackFooter}</p>
        <Button variant="primary" large onClick={onSave} disabled={!ready}>
          {t.saveFeedback}
        </Button>
      </div>
    </Surface>
  )
}

/** When the hand-over of a customer was written: the latest move to handed over. */
function writtenAt(customer: string, jobs: Job[]): string | undefined {
  const moves = jobs
    .filter((j) => j.state === 'handed_over' && j.file.customer === customer)
    .map((j) => j.transitions.at(-1)?.at ?? '')
  return moves.sort().at(-1)
}

interface RowProps {
  customer: string
  inbox: InboxView
  answer: Answer | undefined
  onAnswer: (answer: Answer) => void
}

function FeedbackRow({ customer, inbox, answer, onAnswer }: RowProps) {
  const t = useTexts().handOver
  const [language] = useLanguage()
  const at = writtenAt(customer, inbox.jobs)
  const choice = (imported: boolean, label: string) => (
    <label className="flex cursor-pointer items-center gap-2.5 rounded-md border border-line px-3.5 py-2.5 has-checked:border-ink">
      <input
        type="radio"
        name={`import-${customer}`}
        checked={answer?.imported === imported}
        onChange={() => onAnswer({ imported, reason: answer?.reason ?? '' })}
        className="accent-ink"
      />
      <span className="font-medium">{label}</span>
    </label>
  )
  return (
    <div className="border-b border-line px-7 py-4 text-[13.5px] last:border-b-0">
      <div className="grid items-center gap-x-3" style={FEEDBACK_GRID}>
        <span className="truncate font-semibold">{customer}</span>
        <span className="text-ink-2">{at ? t.writtenAt(longDate(at, language), timeOfDay(at, language)) : ''}</span>
        {choice(true, t.done)}
        {choice(false, t.failed)}
      </div>
      {answer?.imported === false && (
        <div className="mt-3">
          <TextInput
            label={t.reason}
            valueText={answer.reason}
            onChange={(reason) => onAnswer({ imported: false, reason })}
            placeholder={t.reasonPlaceholder}
          />
          <p className="mt-1.5 text-[12.5px] text-ink-2">{t.reasonNote}</p>
        </div>
      )}
    </div>
  )
}
