/**
 * Settings says in plain words how the program reads: the profile with the
 * folder structure it expects, and the one watched folder, whose subfolder
 * `Ausgabe` receives what leaves. Every name of a target comes from the
 * profile file through the sidecar, never from this file or a dictionary.
 */

import { open } from '@tauri-apps/plugin-dialog'
import { ChevronDown, ChevronRight, Lock } from 'lucide-react'
import { useState } from 'react'

import { api, SubstraktError } from '../api/client'
import type { InboxSettings, ProfileDescription, Status } from '../api/types'
import type { Theme } from '../design/theme'
import { errorText, useLanguage, useTexts } from '../i18n'
import { Button, SectionHeading, Surface, Card, Header, Dot, Title, SELECT, OPTION } from '../ui/components'
import { useKeys } from '../ui/keys'

interface Props {
  status: Status | null
  theme: Theme
  onTheme: (theme: Theme) => void
  inbox: InboxSettings | null
  profile: ProfileDescription | null
  onInbox: (settings: InboxSettings) => void
  onOverview: () => void
  onError: (error: unknown) => void
}

type Choice = Parameters<typeof api.chooseInboxSettings>[0]

const RETENTION = [30, 90, 365]
/** The sidecar's default, shown until its settings have arrived. */
const DEFAULT_RETENTION_DAYS = 90

const LINK = 'underline underline-offset-[3px] hover:text-ink'

/** Opens the folder picker and returns null when the user cancels. */
export async function chooseFolder(): Promise<string | null> {
  const selection = await open({ directory: true, multiple: false })
  return typeof selection === 'string' ? selection : null
}

/** A line of Settings that stores what a person changes in it. */
export type Line = 'profile' | 'folder' | 'retention'

const CHOICE: Record<Line, (value: string | number) => Choice> = {
  profile: (value) => ({ profile: String(value) }),
  folder: (value) => ({ folder: String(value) }),
  retention: (value) => ({ retentionDays: Number(value) }),
}

/** Stores the change of one line at once; true when the sidecar took it, otherwise the error is shown. */
export async function changeLine(
  line: Line,
  value: string | number,
  onInbox: Props['onInbox'],
  onError: Props['onError'],
): Promise<boolean> {
  try {
    onInbox(await api.chooseInboxSettings(CHOICE[line](value)))
    return true
  } catch (failure) {
    onError(failure)
    return false
  }
}

/** Every line takes effect when changed and confirms itself in place; there is no save button. */
function useLines(onInbox: Props['onInbox'], onError: Props['onError']) {
  const [saved, setSaved] = useState<Line | null>(null)
  // A refused folder is named beside the folder line, not in the general notice (R10).
  const [refused, setRefused] = useState<SubstraktError | null>(null)
  const change = async (line: Line, value: string | number) => {
    setSaved(null)
    setRefused(null)
    const failed = (failure: unknown) =>
      line === 'folder' && failure instanceof SubstraktError ? setRefused(failure) : onError(failure)
    if (await changeLine(line, value, onInbox, failed)) setSaved(line)
  }
  // A cancelled picker changes nothing.
  const pick = async () => {
    const path = await chooseFolder()
    if (path) await change('folder', path)
  }
  return { saved, refused, change, pick }
}

export function Settings(props: Props) {
  const lines = useLines(props.onInbox, props.onError)
  // Settings is a place of its own, so Escape has nowhere to go back to.
  useKeys(props.onOverview)
  return <SettingsView {...props} {...lines} />
}

type ViewProps = Omit<Props, 'onInbox' | 'onError'> & ReturnType<typeof useLines>

/** Settings as drawn; the line just changed carries its confirmation. */
export function SettingsView({ status, theme, onTheme, inbox, profile, onOverview, saved, refused, change, pick }: ViewProps) {
  const texts = useTexts()
  const profileName = inbox?.profile ?? ''
  // The description follows once the sidecar has sent the newly chosen profile.
  const shown = profile?.name === profileName ? profile : null
  return (
    <Surface>
      <Header>
        <Title>{texts.settings.title}</Title>
        <Button variant="primary" onClick={onOverview}>
          {texts.pilotSettings.toOverview}
        </Button>
      </Header>
      <Reading
        inbox={inbox}
        profileName={profileName}
        shown={shown}
        saved={saved}
        refused={refused}
        onProfile={(name) => void change('profile', name)}
        onFolder={pick}
      />
      <Retention
        days={inbox?.retention_days ?? DEFAULT_RETENTION_DAYS}
        saved={saved === 'retention'}
        onDays={(d) => void change('retention', d)}
      />
      <Privacy status={status} shown={shown} />
      <Appearance theme={theme} onTheme={onTheme} />
      <LanguageChoice />
    </Surface>
  )
}

/** The confirmation beside a changed line; the live region is always there so it is announced. */
function Saved({ shown }: { shown: boolean }) {
  const t = useTexts().pilotSettings
  return (
    <span role="status" className="ml-3 text-[12.5px] text-good">
      {shown ? t.saved : ''}
    </span>
  )
}

interface ReadingProps {
  inbox: InboxSettings | null
  profileName: string
  shown: ProfileDescription | null
  saved: Line | null
  refused: SubstraktError | null
  onProfile: (name: string) => void
  onFolder: () => Promise<void>
}

function Reading({ inbox, profileName, shown, saved, refused, onProfile, onFolder }: ReadingProps) {
  const t = useTexts().pilotSettings
  return (
    <>
      <SectionHeading>{t.reading}</SectionHeading>
      <Card padded>
        <dl className="grid grid-cols-[204px_1fr] gap-x-6 gap-y-3 text-[14px]">
          <dt className="pt-2 text-ink-2">{t.profile}</dt>
          <dd>
            <ProfileSelect inbox={inbox} profileName={profileName} onProfile={onProfile} />
            <Saved shown={saved === 'profile'} />
            {shown && (
              <p className="mt-1.5 text-[12.5px] text-ink-2">
                {t.folderStructure(shown.customer_folder_level)}
              </p>
            )}
          </dd>
          <dt className="text-ink-2">{t.readFrom}</dt>
          <dd>
            <WatchedFolder inbox={inbox} onFolder={onFolder} />
            <Saved shown={saved === 'folder'} />
            <FolderRefusal refused={refused} />
          </dd>
        </dl>
      </Card>
    </>
  )
}

function ProfileSelect({
  inbox,
  profileName,
  onProfile,
}: Pick<ReadingProps, 'inbox' | 'profileName' | 'onProfile'>) {
  const t = useTexts().pilotSettings
  return (
    <select
      aria-label={t.profile}
      value={profileName}
      onChange={(e) => onProfile(e.target.value)}
      className={SELECT}
    >
      {profileName === '' && <option value="" className={OPTION}>{t.chooseProfile}</option>}
      {(inbox?.profiles ?? []).map((p) => (
        <option key={p.name} value={p.name} className={OPTION}>
          {p.title}
        </option>
      ))}
    </select>
  )
}

function WatchedFolder({ inbox, onFolder }: Pick<ReadingProps, 'inbox' | 'onFolder'>) {
  const texts = useTexts()
  const t = texts.pilotSettings
  return (
    <>
      {inbox?.folder ? (
        <span className="font-mono text-[12.5px]">{inbox.folder}</span>
      ) : (
        <span className="text-ink-3">{t.noFolder}</span>
      )}
      {' · '}
      <button type="button" onClick={() => void onFolder()} className={LINK}>
        {inbox?.folder ? t.change : t.choose}
      </button>
      {inbox?.folder && (
        <p className="mt-1.5 flex items-center gap-2.5 text-[12.5px] text-ink-2">
          <Dot tone={inbox.watching ? 'good' : 'neutral'} />
          {inbox.watching ? texts.pilotOverview.watching : texts.pilotOverview.notWatching}
        </p>
      )}
    </>
  )
}

/** Why the folder was refused, beside the folder line, with the way out; the alert is announced. */
function FolderRefusal({ refused }: { refused: SubstraktError | null }) {
  const texts = useTexts()
  if (!refused) return null
  return (
    <p role="alert" className="mt-1.5 max-w-[64ch] text-[12.5px] text-bad">
      {errorText(texts, refused.key, refused.message)}
    </p>
  )
}

function Retention({ days, saved, onDays }: { days: number; saved: boolean; onDays: (days: number) => void }) {
  const t = useTexts().pilotSettings
  return (
    <>
      <SectionHeading className="mt-11">{t.retention}</SectionHeading>
      <Card padded>
        <div className="flex items-center gap-6">
          <div>
            <p className="text-[14px]">{t.retentionLabel}</p>
            <p className="mt-1 max-w-[64ch] text-[12.5px] text-ink-2">{t.retentionDetail}</p>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-3">
            <Saved shown={saved} />
            <select
              aria-label={t.retentionLabel}
              value={days}
              onChange={(e) => onDays(Number(e.target.value))}
              className={SELECT}
            >
            {[...new Set([...RETENTION, days])]
              .sort((a, b) => a - b)
              .map((d) => (
                <option key={d} value={d} className={OPTION}>
                  {t.days(d)}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>
    </>
  )
}

interface DetailProps {
  status: Status | null
  shown: ProfileDescription | null
}

function Privacy({ status, shown }: DetailProps) {
  const texts = useTexts()
  const [technical, setTechnical] = useState(false)
  return (
    <>
      <SectionHeading className="mt-11">{texts.settings.privacy}</SectionHeading>
      <Card padded>
        <div className="flex items-center gap-3.5">
          <Dot tone="good" />
          <div>
            <p className="font-semibold">{texts.settings.noConnection}</p>
            <p className="mt-1 max-w-[64ch] text-[13px] text-ink-2">
              {texts.settings.noConnectionDetail}
            </p>
          </div>
          <Lock size={18} className="ml-auto shrink-0 text-good" aria-hidden="true" />
        </div>
        <div className="mt-6 border-t border-line pt-5">
          <button
            type="button"
            onClick={() => setTechnical(!technical)}
            aria-expanded={technical}
            className="flex items-center gap-1.5 text-[13px] text-ink-2 transition-colors duration-(--dur-1) hover:text-ink"
          >
            {technical ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            {texts.settings.technical}
          </button>
          {technical && <Technical status={status} shown={shown} />}
        </div>
      </Card>
    </>
  )
}

function Technical({ status, shown }: DetailProps) {
  const texts = useTexts()
  return (
    <div className="mt-4">
      <p className="mb-4 max-w-[64ch] text-[12.5px] text-ink-3">{texts.settings.technicalDetail}</p>
      <dl className="grid grid-cols-[180px_1fr] gap-x-6 gap-y-2.5 text-[13px]">
        <dt className="text-ink-3">{texts.info.mode}</dt>
        <dd>{status ? texts.mode[status.mode] : '—'}</dd>
        <dt className="text-ink-3">{texts.info.sidecar}</dt>
        <dd className="font-mono text-[12.5px]">
          {status?.backend ?? '—'}
          {status?.version ? ` · ${status.version}` : ''}
        </dd>
        <dt className="text-ink-3">{texts.settings.textRecognition}</dt>
        <dd>{texts.settings.localEngine}</dd>
        <dt className="text-ink-3">{texts.settings.storageLocation}</dt>
        <dd>{texts.settings.thisDevice}</dd>
        {shown && (
          <>
            <dt className="text-ink-3">{texts.pilotSettings.profileFile}</dt>
            <dd className="font-mono text-[12.5px]">{shown.name}.yml</dd>
            <dt className="text-ink-3">{texts.pilotSettings.kindFiles}</dt>
            <dd className="font-mono text-[12.5px]">
              {shown.kinds.map((k) => `${k.name}.yml`).join(', ')}
            </dd>
          </>
        )}
      </dl>
    </div>
  )
}

function Appearance({ theme, onTheme }: Pick<Props, 'theme' | 'onTheme'>) {
  const texts = useTexts()
  return (
    <>
      <SectionHeading className="mt-11">{texts.settings.appearance}</SectionHeading>
      <div className="grid max-w-[520px] grid-cols-2 gap-3">
        <ThemeChoice
          selected={theme === 'light'}
          onClick={() => onTheme('light')}
          title={texts.settings.light}
          detail={texts.settings.lightDetail}
          preview="bg-[#F3F3F1] border-[rgba(23,25,29,.12)]"
          fieldSpec="bg-white"
        />
        <ThemeChoice
          selected={theme === 'dark'}
          onClick={() => onTheme('dark')}
          title={texts.settings.dark}
          detail={texts.settings.darkDetail}
          preview="bg-[#0D0E11] border-[rgba(255,255,255,.14)]"
          fieldSpec="bg-[#17181C]"
        />
      </div>
    </>
  )
}

function LanguageChoice() {
  const texts = useTexts()
  const [language, setLanguage] = useLanguage()
  return (
    <>
      <SectionHeading className="mt-11">{texts.settings.language}</SectionHeading>
      <div className="grid max-w-[520px] grid-cols-2 gap-3">
        <ThemeChoice
          selected={language === 'de'}
          onClick={() => setLanguage('de')}
          title={texts.settings.german}
          detail={texts.settings.germanDetail}
          preview="bg-card-2 border-line"
          fieldSpec="bg-card"
          sample={texts.settings.germanCode}
        />
        <ThemeChoice
          selected={language === 'en'}
          onClick={() => setLanguage('en')}
          title={texts.settings.english}
          detail={texts.settings.englishDetail}
          preview="bg-card-2 border-line"
          fieldSpec="bg-card"
          sample={texts.settings.englishCode}
        />
      </div>
    </>
  )
}

function ThemeChoice({
  selected,
  onClick,
  title,
  detail,
  preview,
  fieldSpec,
  sample,
}: {
  selected: boolean
  onClick: () => void
  title: string
  detail: string
  preview: string
  fieldSpec: string
  sample?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={[
        'rounded-md border bg-card p-4 text-left transition-all duration-(--dur-1) ease-gentle',
        selected ? 'border-ink shadow-[0_0_0_1px_var(--ink)]' : 'border-line hover:border-line-2',
      ].join(' ')}
    >
      {/* A small sample shows the choice directly. */}
      <span
        className={[
          'mb-3 flex h-14 items-center justify-center gap-1.5 rounded-sm border p-2',
          preview,
        ].join(' ')}
        aria-hidden="true"
      >
        {sample ? (
          <span className="text-[17px] font-semibold tracking-[0.08em] text-ink-2">
            {sample}
          </span>
        ) : (
          <>
            <span className={['h-full w-1/3 rounded-[3px]', fieldSpec].join(' ')} />
            <span className={['h-full flex-1 rounded-[3px]', fieldSpec].join(' ')} />
          </>
        )}
      </span>
      <span className="block text-sm font-semibold">{title}</span>
      <span className="mt-0.5 block text-[12.5px] text-ink-2">{detail}</span>
    </button>
  )
}
