/**
 * Overview shows whether the watched folder is read and what needs a person.
 *
 * It follows the approved concept (docs/design/design-language.md): a headline that
 * names the next step with the one dark button, a status line that never
 * contradicts the list below it, and one entry per import with its customers,
 * documents and what was recognised. Each number stands once on the screen. Column headings come from the
 * profile file, so no target or kind term is written here.
 */

import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'

import type {
  InboxEntry,
  InboxImport,
  InboxSettings,
  Job,
  ProfileDescription,
  Status,
} from '../api/types'
import { api } from '../api/client'
import { errorText, useLanguage, useTexts, type Language, type Texts } from '../i18n'
import {
  SectionHeading,
  Surface,
  Card,
  Button,
  Header,
  Empty,
  Badge,
  Dot,
  Title,
  SearchInput,
  TextLink,
  OPTION,
  SELECT,
  type Tone,
} from '../ui/components'
import { formatAmount, longDate, timeOfDay, relativeTime } from '../ui/format'
import { useKeys } from '../ui/keys'
import { customersWith, importFailure, problemText } from './HandOver'

/** What the sidecar knows about the watched folder. */
export interface InboxView {
  settings: InboxSettings | null
  entries: InboxEntry[]
  imports: InboxImport[]
  jobs: Job[]
  profile: ProfileDescription | null
}

interface Props {
  status: Status | null
  inbox: InboxView
  /** Opens Review, at one entry when given. */
  onReview: (entryId?: number) => void
  onChooseFolder: () => void
  /** Opens the simulation of the hand-over. */
  onHandOver: () => void
  /** Opens the report of what importing the hand-over did. */
  onFeedback: () => void
  onError: (error: unknown) => void
}

type OverviewTexts = Texts['pilotOverview']

/** The state one document row shows. */
type RowState =
  | 'reading'
  | 'error'
  | 'duplicate'
  | 'possible'
  | 'unclear'
  | 'later'
  | 'waiting'
  | 'ready'
  | 'handedOver'
  | 'filed'
  | 'importFailed'
  | 'failed'

/** The states a person can filter by, and the row states each one holds. */
const FILTERS = {
  waiting: ['waiting', 'unclear', 'later'],
  ready: ['ready'],
  filed: ['handedOver', 'filed'],
  possible: ['possible'],
  duplicate: ['duplicate'],
  error: ['error', 'failed', 'importFailed'],
} as const satisfies Record<string, readonly RowState[]>
type Filter = keyof typeof FILTERS

/** The periods a person can narrow the list to; `latest` is the most recent import. */
export const PERIODS = ['latest', 'days3', 'week', 'month', 'months3'] as const
export type Period = (typeof PERIODS)[number]

/** What a person narrowed the list of read documents to. */
export interface Query {
  period: Period
  filter: Filter | ''
  search: string
}
const NO_QUERY: Query = { period: 'latest', filter: '', search: '' }

/** The documents a customer line shows before a person asks for all of them. */
const FIRST_SHOWN = 3

/** Rows that need a person; they are shown before a settled row is. */
const NEEDS_PERSON: readonly RowState[] = ['unclear', 'possible', 'error', 'failed', 'importFailed']

/** A value column of the import table, named by the profile. */
interface Column {
  name: string
  heading: string
  numeric: boolean
}

const FILTER = `${SELECT} w-[190px]`
const LINK = 'text-[12.5px] underline underline-offset-[3px] hover:text-ink'

function rowState(entry: InboxEntry, job: Job | undefined): RowState {
  switch (entry.state) {
    case 'new':
      return 'reading'
    case 'error':
      return 'error'
    case 'duplicate':
      return 'duplicate'
    case 'approved':
      if (job === undefined || job.state === 'pending') return 'ready'
      if (job.state === 'failed') return importFailure(job) === null ? 'failed' : 'importFailed'
      return job.state === 'done' ? 'filed' : 'handedOver'
    case 'waiting':
      if (entry.possible_duplicate_of !== null && entry.duplicate_decision === null)
        return 'possible'
      if (entry.values.some((v) => !v.grounded)) return 'unclear'
      return entry.later_arrival ? 'later' : 'waiting'
  }
}

/** True while a document is read or the latest import of a watched folder runs. */
function isReading({ entries, imports, settings }: InboxView): boolean {
  const latest = imports.at(-1)
  return (
    entries.some((e) => e.state === 'new') ||
    (latest !== undefined && latest.finished_at === null && settings?.watching === true)
  )
}

/** The step the headline offers as its one dark button. */
export type Next = 'review' | 'feedback' | 'release' | 'handOver' | 'errors' | null

/** What the headline weighs; the hand-over counts are customers, not documents. */
export interface Stage {
  starts: boolean
  reading: boolean
  read: number
  waiting: number
  pending: number
  /** Entries that could not be read and jobs that failed. */
  errors: number
  /** Customers whose hand-over waits for a person's report. */
  handedOver: number
  /** Customers whose import was reported as failed and not released. */
  failed: number
  /** Customers with a confirmed import and no failed one. */
  done: number
  target: string
}

/** Headline, subtitle and button name the next step, the most urgent first. */
export function headline(t: OverviewTexts, s: Stage): [string, string, Next] {
  if (s.starts) return [t.startTitle, t.startSubtitle, null]
  if (s.reading) return [t.readingTitle(s.read), t.readingSubtitle, s.waiting > 0 ? 'review' : null]
  if (s.waiting > 0) return [t.waitingTitle(s.waiting), t.waitingSubtitle, 'review']
  if (s.handedOver > 0)
    return [t.handedOverTitle(s.handedOver, s.target), t.handedOverSubtitle(s.target), 'feedback']
  if (s.failed > 0) return [t.resultTitle(s.done, s.failed), t.resultSubtitle, 'release']
  if (s.pending > 0) return [t.readyTitle, t.readySubtitle(s.pending), 'handOver']
  if (s.errors > 0) return [t.errorsTitle, t.errorsSubtitle, 'errors']
  return [t.quietTitle, t.quietSubtitle, null]
}

/** Entries that could not be read and jobs that failed; the status line names them. */
function errorCount({ entries, jobs }: Pick<InboxView, 'entries' | 'jobs'>): number {
  return entries.filter((e) => e.state === 'error').length + jobs.filter((j) => j.state === 'failed').length
}

/** The customers waiting for a report, with a failed import, and with a confirmed one. */
export function stageOfJobs(jobs: Job[]): Pick<Stage, 'handedOver' | 'failed' | 'done'> {
  const failed = new Set(
    jobs.flatMap((j) => (importFailure(j) !== null && j.file.customer !== null ? [j.file.customer] : [])),
  )
  const done = customersWith(jobs, 'done').filter((c) => !failed.has(c))
  return { handedOver: customersWith(jobs, 'handed_over').length, failed: failed.size, done: done.length }
}

export function Overview(props: Props) {
  const { status, inbox, onReview, onChooseFolder } = props
  const t = useTexts().pilotOverview
  const [query, setQuery] = useState<Query>(NO_QUERY)
  const { entries, jobs, settings } = inbox
  const read = entries.filter((e) => e.state === 'waiting' || e.state === 'approved').length
  const waiting = entries.filter((e) => e.state === 'waiting').length
  const pending = jobs.filter((j) => j.state === 'pending').length
  const errors = errorCount(inbox)
  const starts = entries.length === 0 && !settings?.folder
  const stage = { starts, reading: isReading(inbox), read, waiting, pending, errors, ...stageOfJobs(jobs) }
  const [title, subtitle, next] = headline(t, { ...stage, target: inbox.profile?.title ?? '' })
  const lastRead = entries.map((e) => e.arrived_at).sort().at(-1)
  // An error may lie in an older import, so the list opens on the longest period.
  const steps = { ...props, onErrors: () => setQuery({ ...NO_QUERY, period: 'months3', filter: 'error' }) }
  return (
    <Surface wide={!starts}>
      <Header>
        <Title subtitle={subtitle}>{title}</Title>
        <NextStep {...steps} next={next} />
      </Header>
      {starts ? (
        <StartCard onChooseFolder={onChooseFolder} />
      ) : (
        <StatusCard status={status} watching={settings?.watching === true} lastRead={lastRead} errors={errors}>
          <StepLinks {...steps} shown={handOverSteps(stage).filter((step) => step !== next)} />
        </StatusCard>
      )}
      <Imports inbox={inbox} query={query} onQuery={setQuery} onReview={onReview} />
    </Surface>
  )
}

/** The hand-over steps the counts allow, whatever else waits; nothing unapproved is among them. */
export function handOverSteps(s: Pick<Stage, 'pending' | 'handedOver' | 'failed'>): Step[] {
  const steps: [Step, number][] = [['feedback', s.handedOver], ['release', s.failed], ['handOver', s.pending]]
  return steps.filter(([, count]) => count > 0).map(([step]) => step)
}

type Step = Exclude<Next, null>
type StepProps = Props & { onErrors: () => void }

/** Label and action of each step; releasing failed imports leads back to the simulation. */
function useSteps({ inbox, onReview, onHandOver, onFeedback, onError, onErrors }: StepProps) {
  const texts = useTexts()
  const t = texts.pilotOverview
  const [busy, setBusy] = useState(false)
  const release = async () => {
    if (busy) return
    setBusy(true)
    try {
      for (const job of inbox.jobs) if (importFailure(job) !== null) await api.releaseJob(job.id)
      onHandOver()
    } catch (f) {
      onError(f)
    } finally {
      setBusy(false)
    }
  }
  const steps: Record<Step, readonly [string, () => void]> = {
    review: [texts.overview.reviewNow, () => onReview()],
    errors: [t.showErrors, onErrors],
    feedback: [t.giveFeedback, onFeedback],
    release: [t.releaseFailed, () => void release()],
    handOver: [t.showHandOver, onHandOver],
  }
  return { steps, busy }
}

/** The headline's button. */
function NextStep(props: StepProps & { next: Next }) {
  const { steps, busy } = useSteps(props)
  const step = props.next === null ? null : steps[props.next]
  useKeys(step && !busy ? step[1] : null)
  if (step === null) return null
  const [label, onClick] = step
  return (
    <Button variant="primary" large onClick={onClick} disabled={busy}>
      {label}
    </Button>
  )
}

/** The hand-over steps the headline does not offer, as quiet links, so that a waiting entry blocks none. */
function StepLinks(props: StepProps & { shown: Step[] }) {
  const { steps } = useSteps(props)
  if (props.shown.length === 0) return null
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1.5 border-t border-line px-7 py-3.5 text-[13px]">
      {props.shown.map((step) => (
        <TextLink key={step} onClick={steps[step][1]}>
          {steps[step][0]}
        </TextLink>
      ))}
    </div>
  )
}

function StartCard({ onChooseFolder }: { onChooseFolder: () => void }) {
  const t = useTexts().pilotOverview
  useKeys(onChooseFolder)
  return (
    <Card>
      <Empty
        title={t.startCard}
        detail={t.startCardDetail}
        action={
          <Button variant="primary" onClick={onChooseFolder}>
            {t.chooseFolder}
          </Button>
        }
      />
    </Card>
  )
}

/**
 * Whether the program runs, starts or cannot be reached, and whether it watches.
 * „Alles läuft“ is never said while an entry or a job below has failed.
 */
function serviceState(
  status: Status | null,
  watching: boolean,
  errors: number,
  texts: Texts,
): [Tone, string, string] {
  const t = texts.pilotOverview
  const detail = watching ? t.watching : t.notWatching
  if (status?.connected === true && errors > 0) return ['waiting', t.withErrors(errors), detail]
  if (status?.connected === true) return ['good', texts.state.running, detail]
  if (status === null || status.version === '')
    return ['neutral', texts.state.starting, texts.state.startingDetail]
  return ['error', texts.state.unavailable, texts.state.unavailableDetail]
}

interface StatusProps {
  status: Status | null
  watching: boolean
  lastRead: string | undefined
  errors: number
  /** The steps the headline does not offer, as quiet links. */
  children: React.ReactNode
}

/** Whether the program runs and watches, and whether anything below failed. */
function StatusCard({ status, watching, lastRead, errors, children }: StatusProps) {
  const texts = useTexts()
  const [language] = useLanguage()
  const [tone, word, detail] = serviceState(status, watching, errors, texts)
  const warn = tone === 'waiting' ? 'text-warn' : ''
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-5 p-7">
        <Dot tone={tone} />
        <div>
          <p className={`text-[19px] font-semibold tracking-[-0.02em] ${warn}`}>{word}</p>
          <p className="mt-0.5 text-[13.5px] text-ink-2">{detail}</p>
        </div>
        {lastRead && (
          <p className="ml-auto text-right text-[12.5px] text-ink-3">
            {texts.overview.lastRead}
            <br />
            {relativeTime(lastRead, language, texts)}
          </p>
        )}
      </div>
      {children}
    </Card>
  )
}

/** The earliest time of reading a period still holds, counted back from now. */
export function periodStart(period: Exclude<Period, 'latest'>, now: Date): Date {
  const start = new Date(now)
  if (period === 'days3') start.setDate(start.getDate() - 3)
  if (period === 'week') start.setDate(start.getDate() - 7)
  if (period === 'month') start.setMonth(start.getMonth() - 1)
  if (period === 'months3') start.setMonth(start.getMonth() - 3)
  return start
}

/** True when the entry was read in the period; `latest` holds the most recent import. */
export function inPeriod(
  entry: InboxEntry,
  period: Period,
  latestImport: number | undefined,
  now: Date,
): boolean {
  if (period === 'latest') return entry.import_id === latestImport
  return Date.parse(entry.arrived_at) >= periodStart(period, now).getTime()
}

/** The entries that match state, text and period at once. */
export function filtered(
  { entries, imports }: Pick<InboxView, 'entries' | 'imports'>,
  query: Query,
  stateOf: (e: InboxEntry) => RowState,
  now: Date,
): InboxEntry[] {
  const latest = imports.filter((i) => entries.some((e) => e.import_id === i.id)).at(-1)?.id
  return entries.filter((e) => matches(e, query, stateOf(e)) && inPeriod(e, query.period, latest, now))
}

/** The latest read first. */
const newestFirst = (a: InboxEntry, b: InboxEntry) =>
  Date.parse(b.arrived_at) - Date.parse(a.arrived_at)

/**
 * The documents a customer line shows, the latest read first. Folded it shows
 * three, and a document that needs a person is never hidden behind a settled one.
 */
export function shownDocuments(
  docs: InboxEntry[],
  stateOf: (e: InboxEntry) => RowState,
  all: boolean,
): InboxEntry[] {
  const sorted = [...docs].sort(newestFirst)
  if (all) return sorted
  const urgent = sorted.filter((e) => NEEDS_PERSON.includes(stateOf(e)))
  const kept = new Set([...urgent, ...sorted].slice(0, FIRST_SHOWN))
  return sorted.filter((e) => kept.has(e))
}

/** One filter for every import, and one card per import with a matching entry, the latest first. */
interface ImportsProps {
  inbox: InboxView
  query: Query
  onQuery: (query: Query) => void
  onReview: Props['onReview']
}

function Imports({ inbox, query, onQuery: setQuery, onReview }: ImportsProps) {
  const t = useTexts().pilotOverview
  const { entries: all, imports, jobs } = inbox
  const withEntries = imports.filter((i) => all.some((e) => e.import_id === i.id))
  if (withEntries.length === 0) return null
  const jobOf = new Map(jobs.map((j) => [j.entry_id, j]))
  const entries = filtered(inbox, query, (e) => rowState(e, jobOf.get(e.id)), new Date())
  const shown = withEntries.filter((i) => entries.some((e) => e.import_id === i.id)).reverse()
  const narrowed = isFiltered(query)
  return (
    <>
      <SectionHeading className="mt-11">{t.imported}</SectionHeading>
      <FilterBar
        query={query}
        onQuery={setQuery}
        hits={narrowed ? t.hits(entries.length, all.length) : null}
      />
      {shown.length === 0 && <p className="py-6 text-[13.5px] text-ink-2">{t.noMatch}</p>}
      <div className="flex flex-col gap-6">
        {shown.map((item) => (
          <ImportCard
            key={item.id}
            item={item}
            inbox={inbox}
            shown={entries.filter((e) => e.import_id === item.id)}
            filtered={narrowed}
            jobOf={jobOf}
            watching={inbox.settings?.watching === true}
            onReview={onReview}
          />
        ))}
      </div>
    </>
  )
}

function columnsOf(profile: ProfileDescription | null, entries: InboxEntry[]): Column[] {
  return Object.entries(profile?.overview_columns ?? {}).map(([name, heading]) => ({
    name,
    heading,
    numeric: entries.some((e) =>
      e.values.some((v) => v.field === name && typeof v.normalized === 'number'),
    ),
  }))
}

/** File, kind, the value columns and the state; amounts get a narrow right column. */
function gridOf(columns: Column[]): React.CSSProperties {
  const values = columns.map((c) => (c.numeric ? '96px' : 'minmax(0,1fr)'))
  return { gridTemplateColumns: ['minmax(0,1fr)', '116px', ...values, '280px'].join(' ') }
}

export function matches(entry: InboxEntry, query: Query, state: RowState): boolean {
  const needle = query.search.trim().toLowerCase()
  const texts = [entry.file_name, entry.customer ?? '', ...entry.values.map((v) => v.value ?? '')]
  return (
    (query.filter === '' || (FILTERS[query.filter] as readonly RowState[]).includes(state)) &&
    (needle === '' || texts.some((s) => s.toLowerCase().includes(needle)))
  )
}

const isFiltered = (query: Query) =>
  query.period !== 'latest' || query.filter !== '' || query.search.trim() !== ''

/** What one import table needs to show a row, shared by its customer groups. */
interface Table {
  all: InboxEntry[]
  columns: Column[]
  stateOf: (entry: InboxEntry) => RowState
  kindTitle: (kind: string | null) => string
  jobOf: (entry: InboxEntry) => Job | undefined
  /** The label of a value of a kind, or null when the profile does not name it. */
  labelOf: (kind: string | null, name: string) => string | null
  onReview: Props['onReview']
}

interface ImportProps {
  item: InboxImport
  inbox: InboxView
  /** The entries of this import that match the filter. */
  shown: InboxEntry[]
  filtered: boolean
  jobOf: Map<number, Job>
  watching: boolean
  onReview: Props['onReview']
}

/** One chosen folder: its customers, their documents and the hand-overs. */
function ImportCard({ item, inbox, shown, filtered, jobOf, watching, onReview }: ImportProps) {
  const t = useTexts().pilotOverview
  const { entries: all, profile } = inbox
  const entries = all.filter((e) => e.import_id === item.id)
  const stateOf = (e: InboxEntry) => rowState(e, jobOf.get(e.id))
  const nameOf = (e: InboxEntry) => e.customer ?? t.noCustomer
  // Customers by their latest read document, the latest first.
  const customers = [...new Set([...shown].sort(newestFirst).map(nameOf))]
  const kindTitle = (kind: string | null) =>
    kind === null ? t.notRecognised : (profile?.kinds.find((k) => k.name === kind)?.title ?? kind)
  const table: Table = {
    all,
    columns: columnsOf(profile, entries),
    stateOf,
    kindTitle,
    jobOf: (e) => jobOf.get(e.id),
    labelOf: (kind, name) => labelIn(profile, kind, name),
    onReview,
  }
  return (
    <Card className="overflow-hidden">
      <ImportHeader
        item={item}
        entries={entries}
        customers={new Set(entries.map(nameOf)).size}
        table={table}
      />
      {item.finished_at === null && watching && <Progress entries={entries} />}
      <ColumnHeadings columns={table.columns} />
      {customers.map((name) => (
        <CustomerGroup
          key={name}
          name={name}
          docs={shown.filter((e) => nameOf(e) === name)}
          filtered={filtered}
          table={table}
        />
      ))}
    </Card>
  )
}

/** The label the profile gives a value of a kind, or null when it names none. */
function labelIn(profile: ProfileDescription | null, kind: string | null, name: string): string | null {
  return profile?.kinds.find((k) => k.name === kind)?.values.find((v) => v.name === name)?.label ?? null
}

/** When the import began, its folder, and its counts as badges. */
function ImportHeader({
  item,
  entries,
  customers,
  table,
}: {
  item: InboxImport
  entries: InboxEntry[]
  customers: number
  table: Table
}) {
  const t = useTexts().pilotOverview
  const [language] = useLanguage()
  const count = (state: RowState) => entries.filter((e) => table.stateOf(e) === state).length
  const later = entries.filter((e) => e.later_arrival).length
  return (
    <div className="flex items-start justify-between gap-6 px-7 py-5">
      <div className="min-w-0">
        <p className="text-[15px] font-semibold">
          {t.importOf(longDate(item.started_at, language), timeOfDay(item.started_at, language))}
        </p>
        <p className="mt-1 truncate text-[12.5px] text-ink-3" title={item.folder}>
          {folderName(item.folder)}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
        <Badge>{t.customersAndDocuments(customers, entries.length)}</Badge>
        {count('reading') > 0 && <Badge>{t.beingRead(count('reading'))}</Badge>}
        {later > 0 && <Badge>{t.laterArrivals(later)}</Badge>}
        {count('duplicate') > 0 && <Badge>{t.duplicates(count('duplicate'))}</Badge>}
        {count('possible') > 0 && <Badge>{t.possibleDuplicates(count('possible'))}</Badge>}
      </div>
    </div>
  )
}

/** The last name of a folder path; the whole path is a tooltip here and stands in Settings. */
export function folderName(path: string): string {
  return path.replace(/[\\/]+$/, '').split(/[\\/]/).at(-1) || path
}

/** A thin bar for the share of documents already read. */
function Progress({ entries }: { entries: InboxEntry[] }) {
  const done = entries.filter((e) => e.state !== 'new').length
  return (
    <div className="h-[3px] bg-line" aria-hidden="true">
      <div
        className="h-full bg-ink-3 transition-[width] duration-(--dur-2)"
        style={{ width: `${Math.round((100 * done) / Math.max(1, entries.length))}%` }}
      />
    </div>
  )
}

interface FilterProps {
  query: Query
  onQuery: (query: Query) => void
  /** The count of matching rows while a filter is set. */
  hits: string | null
}

function FilterBar({ query, onQuery, hits }: FilterProps) {
  const t = useTexts().pilotOverview
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2.5">
      <select
        aria-label={t.period}
        value={query.period}
        onChange={(e) => onQuery({ ...query, period: e.target.value as Period })}
        className={FILTER}
      >
        {PERIODS.map((p) => (
          <option key={p} value={p} className={OPTION}>
            {t.periods[p]}
          </option>
        ))}
      </select>
      <FilterSelect
        label={t.state}
        value={query.filter}
        all={t.allStates}
        options={(Object.keys(FILTERS) as Filter[]).map((f) => [f, t.states[f]])}
        onChange={(filter) => onQuery({ ...query, filter: filter as Filter | '' })}
      />
      <SearchInput
        valueText={query.search}
        onChange={(search) => onQuery({ ...query, search })}
        placeholder={t.search}
        stretch
      />
      {hits !== null && (
        <span className="ml-auto flex items-center gap-3 text-[12.5px] text-ink-2">
          {hits}
          <button type="button" onClick={() => onQuery(NO_QUERY)} className={LINK}>
            {t.resetFilter}
          </button>
        </span>
      )}
    </div>
  )
}

function FilterSelect({
  label,
  value,
  all,
  options,
  onChange,
}: {
  label: string
  value: string
  all: string
  options: [string, string][]
  onChange: (value: string) => void
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={FILTER}
    >
      <option value="" className={OPTION}>{all}</option>
      {options.map(([option, text]) => (
        <option key={option} value={option} className={OPTION}>
          {text}
        </option>
      ))}
    </select>
  )
}

function ColumnHeadings({ columns }: { columns: Column[] }) {
  const t = useTexts().pilotOverview
  return (
    <div
      className="grid gap-x-3 border-b border-line px-7 py-2.5 text-[12.5px] text-ink-3"
      style={gridOf(columns)}
    >
      <span className="pl-4">{t.file}</span>
      <span>{t.recognisedAs}</span>
      {columns.map((c) => (
        <span key={c.name} className={c.numeric ? 'pr-3 text-right' : ''}>
          {c.heading}
        </span>
      ))}
      <span>{t.state}</span>
    </div>
  )
}

/** The state a customer line shows: the most urgent of its documents. */
export function groupState(
  docs: InboxEntry[],
  states: RowState[],
  failureOf: (entry: InboxEntry) => string | null,
  t: OverviewTexts,
): [Tone, string] {
  const unclear = docs
    .filter((_, i) => states[i] === 'unclear')
    .reduce((n, e) => n + e.values.filter((v) => !v.grounded).length, 0)
  const reason = docs.map(failureOf).find((r) => r !== null)
  if (reason) return ['error', t.failedBecause(reason)]
  if (states.some((s) => s === 'error' || s === 'failed')) return ['error', t.states.error]
  if (unclear > 0) return ['waiting', t.unclearValues(unclear)]
  if (states.includes('possible')) return ['waiting', t.states.possible]
  if (states.includes('reading')) return ['neutral', t.states.reading]
  if (states.includes('handedOver')) return ['neutral', t.handedOverGroup]
  if (states.every((s) => s === 'filed')) return ['good', t.done]
  if (states.every((s) => s === 'ready' || s === 'handedOver' || s === 'filed'))
    return ['good', t.states.ready]
  return ['good', t.certain]
}

/** The count of documents and of each recognised kind, for one customer line. */
function documentsLine(docs: InboxEntry[], table: Table, t: OverviewTexts): string {
  const kinds = new Map<string, number>()
  for (const e of docs) {
    if (e.kind === null) continue
    const title = table.kindTitle(e.kind)
    kinds.set(title, (kinds.get(title) ?? 0) + 1)
  }
  return [t.documents(docs.length), ...[...kinds].map(([kind, n]) => `${n} × ${kind}`)].join(' · ')
}

/** One customer: a line that opens to its documents, open while something needs a person. */
interface GroupProps {
  name: string
  docs: InboxEntry[]
  filtered: boolean
  table: Table
}

function CustomerGroup({ name, docs, filtered, table }: GroupProps) {
  const t = useTexts().pilotOverview
  const [open, setOpen] = useState<boolean | null>(null)
  const [all, setAll] = useState(false)
  const rows = shownDocuments(docs, table.stateOf, all)
  const states = docs.map(table.stateOf)
  const expanded =
    open ?? (filtered || states.some((s) => !['waiting', 'ready', 'handedOver', 'filed'].includes(s)))
  const [tone, word] = groupState(docs, states, (e) => importFailure(table.jobOf(e)), t)
  const Chevron = expanded ? ChevronDown : ChevronRight
  return (
    <div className={`border-b border-line px-7 last:border-b-0 ${expanded ? 'pb-3' : ''}`}>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setOpen(!expanded)}
        className="grid w-full items-center gap-x-3 py-4 text-left"
        style={gridOf(table.columns)}
      >
        <span className="flex min-w-0 items-center gap-1 text-[14.5px] font-semibold">
          <Chevron size={14} className="shrink-0 text-ink-3" aria-hidden="true" />
          <span className="truncate">{name}</span>
        </span>
        <span className="truncate text-[14px] text-ink-2" style={{ gridColumn: `span ${table.columns.length + 1}` }}>
          {documentsLine(docs, table, t)}
        </span>
        <span className="flex items-center gap-2.5 text-[13.5px]">
          <Dot tone={tone} />
          {word}
        </span>
      </button>
      {expanded && rows.map((e) => <DocumentRow key={e.id} entry={e} table={table} />)}
      {expanded && rows.length < docs.length && (
        <p className="border-t border-line py-2.5 pl-4 text-[13px]">
          <TextLink onClick={() => setAll(true)}>{t.showAll(docs.length)}</TextLink>
        </p>
      )}
    </div>
  )
}

/** A value as the row shows it; every number the pilot kinds read is an amount. */
export function shownValue(entry: InboxEntry, name: string, language: Language): string {
  const value = entry.values.find((v) => v.field === name)
  return typeof value?.normalized === 'number'
    ? formatAmount(value.normalized, language)
    : (value?.value ?? '')
}

/** A waiting entry and a duplicate open in Review; any other row opens below itself, read-only. */
export function opensReview(entry: InboxEntry): boolean {
  return entry.state === 'waiting' || entry.state === 'duplicate'
}

function DocumentRow({ entry, table }: { entry: InboxEntry; table: Table }) {
  const [open, setOpen] = useState(false)
  const review = opensReview(entry)
  return (
    <>
      <button
        type="button"
        aria-expanded={review ? undefined : open}
        onClick={() => (review ? table.onReview(entry.id) : setOpen(!open))}
        className="grid w-full items-center gap-x-3 border-t border-line py-2.5 text-left text-[13.5px] hover:bg-card-2"
        style={gridOf(table.columns)}
      >
        <RowCells entry={entry} table={table} />
      </button>
      {open && <RowDetails entry={entry} job={table.jobOf(entry)} labelOf={table.labelOf} />}
    </>
  )
}

/** File, kind, the value columns and the state of one row. */
function RowCells({ entry, table }: { entry: InboxEntry; table: Table }) {
  const texts = useTexts()
  const [language] = useLanguage()
  const t = texts.pilotOverview
  const state = table.stateOf(entry)
  const notRead = state === 'reading' || state === 'error' || state === 'duplicate'
  const first = table.all.find((o) => o.id === entry.duplicate_of)?.file_name ?? ''
  return (
    <>
      <span className="truncate pl-4 font-medium" title={entry.file_name}>
        {entry.file_name}
      </span>
      <span className="truncate text-ink-2">
        {state === 'reading' ? t.states.reading : notRead ? t.notRead : table.kindTitle(entry.kind)}
      </span>
      {notRead ? (
        <span className="truncate text-ink-2" style={{ gridColumn: `span ${table.columns.length}` }}>
          {state === 'error' && errorText(texts, entry.problem_key ?? 'internal-error', texts.errors.title)}
          {state === 'duplicate' && t.sameContentAs(first)}
        </span>
      ) : (
        table.columns.map((c) => (
          <span
            key={c.name}
            className={['truncate text-ink-2', c.numeric ? 'tabular-number pr-3 text-right' : ''].join(' ')}
          >
            {shownValue(entry, c.name, language)}
          </span>
        ))
      )}
      <span className="flex items-center gap-3 text-ink-2">
        <RowEnd state={state} />
      </span>
    </>
  )
}

/** What one row holds, read-only: every labelled value, and why it failed. */
export function RowDetails({
  entry,
  job,
  labelOf,
}: {
  entry: InboxEntry
  job: Job | undefined
  labelOf: Table['labelOf']
}) {
  const texts = useTexts()
  const [language] = useLanguage()
  const values = entry.values.flatMap((v) => {
    const label = labelOf(entry.kind, v.field)
    return label === null ? [] : [[v.field, label, shownValue(entry, v.field, language)] as const]
  })
  const reason = job?.state === 'failed' ? job.transitions.at(-1)?.reason ?? '' : null
  return (
    <div className="border-t border-line bg-card-2 py-3 pl-4 text-[13px]">
      {entry.state === 'error' && <p>{errorText(texts, entry.problem_key ?? 'internal-error', texts.errors.title)}</p>}
      {reason !== null && (
        <p>{importFailure(job) ?? problemText(reason, texts.handOver)}</p>
      )}
      {values.length > 0 && (
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1">
          {values.map(([name, label, shown]) => (
            <div key={name} className="contents">
              <dt className="text-ink-3">{label}</dt>
              <dd>{shown}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

/** The state of one row in words. */
function RowEnd({ state }: { state: RowState }) {
  const t = useTexts().pilotOverview
  switch (state) {
    case 'reading':
      return null
    case 'error':
    case 'failed':
      return <Badge tone="error">{t.states.error}</Badge>
    case 'importFailed':
      return <Badge tone="error">{t.importFailed}</Badge>
    case 'handedOver':
      return <Badge>{t.handedOverRow}</Badge>
    case 'duplicate':
      return (
        <>
          <Badge>{t.states.duplicate}</Badge>
          <span className={LINK}>{t.compare}</span>
        </>
      )
    case 'possible':
      return <Badge tone="waiting">{t.states.possible}</Badge>
    case 'unclear':
      return <Badge tone="waiting">{t.unclear}</Badge>
    case 'later':
      return <Badge>{t.laterArrival}</Badge>
    case 'waiting':
    case 'ready':
      return t.states[state]
    case 'filed':
      return <Badge tone="good">{t.done}</Badge>
  }
}
