/**
 * The path „Ordner einlesen“ from Overview (concept step 2): the clerk sees
 * the active way of working in words, picks a folder and starts reading. It
 * is a path, not a place, so the sidebar keeps Overview selected, and nothing
 * is stored until „Einlesen starten“; Esc and the back link leave unchanged.
 */

import { useState } from 'react'

import type { InboxSettings, ProfileDescription } from '../api/types'
import { useTexts, type Texts } from '../i18n'
import { Button, Card, Header, SectionHeading, Surface, Title } from '../ui/components'
import { useKeys } from '../ui/keys'
import { BackButton } from './HandOver'
import { folderName } from './Overview'
import { changeLine, chooseFolder } from './Settings'

interface Props {
  profile: ProfileDescription | null
  onBack: () => void
  /** Called with the settings the sidecar returns once reading has started. */
  onStarted: (settings: InboxSettings) => void
  onError: (error: unknown) => void
}

/** The active way of working as sentences: what is read, who the customer is, where it goes. */
export function wayInWords(t: Texts['readFolder'], profile: ProfileDescription): string[] {
  const level = profile.customer_folder_level
  return [
    t.reads(profile.kinds.map((k) => k.title)),
    level === null ? t.customerNone : level === 1 ? t.customerFirst : t.customerLevel(level),
    t.goesTo(profile.title),
  ]
}

export function ReadFolder({ profile, onBack, onStarted, onError }: Props) {
  const [folder, setFolder] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const start = async () => {
    // The button is disabled without a folder and while starting.
    if (!folder) return
    setStarting(true)
    // Storing the folder starts reading; a refusal keeps the screen open.
    if (!(await changeLine('folder', folder, onStarted, onError))) setStarting(false)
  }
  const pick = async () => {
    const path = await chooseFolder()
    if (path) setFolder(path)
  }
  // Enter starts once a folder is chosen; Esc leaves and stores nothing.
  useKeys(folder && !starting ? () => void start() : null, onBack)
  return (
    <ReadFolderView
      profile={profile}
      folder={folder}
      starting={starting}
      onBack={onBack}
      onPick={() => void pick()}
      onStart={() => void start()}
    />
  )
}

interface ViewProps {
  profile: ProfileDescription | null
  folder: string | null
  starting: boolean
  onBack: () => void
  onPick: () => void
  onStart: () => void
}

export function ReadFolderView({ profile, folder, starting, onBack, onPick, onStart }: ViewProps) {
  const t = useTexts().readFolder
  return (
    <Surface>
      <BackButton onBack={onBack} />
      <Header>
        <Title subtitle={t.subtitle}>{t.title}</Title>
      </Header>
      <SectionHeading>{t.way}</SectionHeading>
      <Card padded>
        {/* shortcut: with several ways of working and none chosen, Settings chooses one first. */}
        <p className="max-w-[72ch] text-[14px]">
          {profile ? wayInWords(t, profile).join(' ') : t.noWay}
        </p>
      </Card>
      <SectionHeading className="mt-9">{t.folder}</SectionHeading>
      <Card padded>
        <div className="flex items-center gap-6">
          {folder ? (
            <p className="flex-1 text-[14px] font-semibold" title={folder}>
              {folderName(folder)}
            </p>
          ) : (
            <p className="flex-1 text-[14px] text-ink-3">{t.noFolder}</p>
          )}
          <Button onClick={onPick}>{folder ? t.chooseOther : t.choose}</Button>
        </div>
      </Card>
      <p className="mt-4 rounded-md bg-card-2 px-4 py-3 text-[12.5px] text-ink-2">{t.filesStay}</p>
      <div className="mt-7 flex items-center gap-5">
        <p className="flex-1 text-[13px] text-ink-2">{t.runsOn}</p>
        <Button variant="primary" large onClick={onStart} disabled={!folder || starting}>
          {t.start}
        </Button>
      </div>
    </Surface>
  )
}
