/**
 * Application shell with a sidebar and one of four places.
 *
 * One kind is a path from Templates rather than an additional place, so the
 * sidebar remains on Templates during it. The path for documents read by hand
 * (template detail, setup assistant, its review and „Ergebnis sichern“) has no
 * view here: it is hidden in the pilot, its code stays for stage 3 (decision 2
 * of docs/decisions.md, “Interface clarity”).
 */

import { open } from '@tauri-apps/plugin-dialog'
import { AlertCircle, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { api, SubstraktError } from './api/client'
import type { KindValues, Status } from './api/types'
import { applyTheme, storedTheme, type Theme } from './design/theme'
import { LanguageProvider, errorText, useTexts } from './i18n'
import { Settings } from './places/Settings'
import { Review } from './places/Review'
import { Feedback, HandOver } from './places/HandOver'
import { Overview, type InboxView } from './places/Overview'
import { ReadFolder } from './places/ReadFolder'
import { Templates } from './places/Templates'
import { KindView } from './places/KindView'
import { Sidebar, type Place } from './shell/Sidebar'
import { useSession } from './state/session'

/** Current place or nested template path, including the path's required data. */
type View =
  | { place: Place }
  | { place: 'review'; entryId: number | null }
  | { place: 'kind'; name: string }
  | { place: 'handOver' }
  | { place: 'feedback' }
  | { place: 'readFolder' }

/** The paths that are no place of their own light up the place they start from. */
const PARENT_PLACE: Partial<Record<View['place'], Place>> = {
  kind: 'templates',
  handOver: 'overview',
  feedback: 'overview',
  readFolder: 'overview',
}

/** The place the sidebar marks while a view is shown. */
export const sidebarPlace = (view: View): Place => PARENT_PLACE[view.place] ?? (view.place as Place)

/** Review opens on the entry a link names, or on the first one waiting. */
export function reviewOf(entryId?: number): View {
  return { place: 'review', entryId: entryId ?? null }
}

const EMPTY_INBOX: InboxView = { settings: null, entries: [], imports: [], jobs: [], profile: null }
/** The watched folder fills by itself, so the inbox is asked again this often. */
const INBOX_LOOK_MS = 2000

/** What the sidecar knows about the watched folder, asked again while it is connected. */
function useInbox(connected: boolean, showError: (error: unknown) => void) {
  const [inbox, setInbox] = useState<InboxView>(EMPTY_INBOX)
  const loadInbox = useCallback(async () => {
    try {
      const [settings, entries, imports, jobs] = await Promise.all([
        api.inboxSettings(),
        api.inboxEntries(),
        api.inboxImports(),
        api.jobs(),
      ])
      setInbox((before) => ({ ...before, settings, entries, imports, jobs }))
    } catch {
      // A failed look is repeated with the next one.
    }
  }, [])
  useEffect(() => {
    if (!connected) return
    void loadInbox()
    const timer = setInterval(() => void loadInbox(), INBOX_LOOK_MS)
    return () => clearInterval(timer)
  }, [connected, loadInbox])
  const profileName = inbox.settings?.profile ?? null
  useEffect(() => {
    if (!profileName) return
    api
      .pipelineProfile(profileName)
      .then((profile) => setInbox((before) => ({ ...before, profile })))
      .catch(showError)
  }, [profileName, showError])
  return [inbox, setInbox, loadInbox] as const
}

/**
 * What the error banner shows: the text of a known key, and for anything else
 * the message without the name of its class, which means nothing to a clerk.
 */
export function shownError(error: unknown, title: string): { key: string; fallback: string; detail?: string | undefined } {
  if (error instanceof SubstraktError) return { key: error.key, fallback: error.message, detail: error.detail ?? undefined }
  return { key: 'internal-error', fallback: title, detail: error instanceof Error ? error.message : String(error) }
}

/** Opens the file picker and returns null when the user cancels. */
export async function chooseDocument(filterName: string): Promise<string | null> {
  const selection = await open({
    multiple: false,
    filters: [{
      name: filterName,
      extensions: [
        'pdf', 'xlsx', 'xlsm', 'xls', 'csv', 'tsv',
        'png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp', 'webp',
      ],
    }],
  })
  return typeof selection === 'string' ? selection : null
}

export function App() {
  return (
    <LanguageProvider>
      <Application />
    </LanguageProvider>
  )
}

function Application() {
  const texts = useTexts()
  const [status, setStatus] = useState<Status | null>(null)
  const [view, setView] = useState<View>({ place: 'overview' })
  const [theme, setTheme] = useState<Theme>(storedTheme)
  const [kinds, setKinds] = useState<KindValues[]>([])
  // `detail` explicitly includes undefined because exact optional properties
  // distinguish a missing member from a member whose value is undefined.
  const [error, setError] = useState<{
    key: string
    fallback: string
    detail?: string | undefined
  } | null>(null)

  const session = useSession()

  const showError = useCallback((f: unknown) => {
    setError(shownError(f, texts.errors.title))
  }, [texts.errors.title])

  // Poll during sidecar start-up instead of claiming that it is already ready.
  useEffect(() => {
    let discarded = false
    let attempts = 0

    const check = () => {
      void api
        .status()
        .then((s) => {
          if (discarded) return
          setStatus(s)
          if (!s.connected && attempts < 60) {
            attempts++
            setTimeout(check, 500)
          }
        })
        .catch(() => {
          if (!discarded && attempts < 60) {
            attempts++
            setTimeout(check, 500)
          }
        })
    }

    check()
    return () => {
      discarded = true
    }
  }, [])

  useEffect(() => {
    if (!status?.connected) return
    api
      .documentKinds()
      .then(setKinds)
      .catch(showError)
  }, [status?.connected, showError])

  const [inbox, setInbox, loadInbox] = useInbox(status?.connected === true, showError)

  const changeTheme = useCallback((nextTheme: Theme) => {
    setTheme(nextTheme)
    applyTheme(nextTheme)
  }, [])

  // Escape closes the global error; all other shortcuts belong to a place.
  useEffect(() => {
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setError(null)
    }
    window.addEventListener('keydown', keyHandler)
    return () => window.removeEventListener('keydown', keyHandler)
  }, [])

  // After a run or a report, Overview shows the new states at once, not with the next look.
  const backToOverview = () => {
    setView({ place: 'overview' })
    void loadInbox()
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        place={sidebarPlace(view)}
        onPlace={(place) => setView({ place })}
        waiting={inbox.entries.filter((e) => e.state === 'waiting').length}
        theme={theme}
        onTheme={changeTheme}
        version={status?.version ?? '—'}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        {error && (
          <div
            role="alert"
            className="flex shrink-0 items-start gap-2.5 border-b border-line bg-bad-bg px-6 py-3 text-[13.5px] text-bad"
          >
            <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            <div className="flex-1">
              <p>{errorText(texts, error.key, error.fallback)}</p>
              {error.detail && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs opacity-70">
                    {texts.errors.showDetails}
                  </summary>
                  <pre className="mt-1 overflow-x-auto font-mono text-xs opacity-70">
                    {error.detail}
                  </pre>
                </details>
              )}
            </div>
            <button
              type="button"
              onClick={() => setError(null)}
              aria-label={texts.errors.close}
              className="rounded p-0.5 opacity-70 hover:opacity-100"
            >
              <X size={14} />
            </button>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {view.place === 'overview' && (
            <Overview
              status={status}
              inbox={inbox}
              onReview={(entryId) => setView(reviewOf(entryId))}
              onChooseFolder={() => setView({ place: 'readFolder' })}
              onHandOver={() => setView({ place: 'handOver' })}
              onFeedback={() => setView({ place: 'feedback' })}
              onError={showError}
            />
          )}

          {view.place === 'readFolder' && (
            <ReadFolder
              profile={inbox.profile}
              onBack={() => setView({ place: 'overview' })}
              onStarted={(settings) => {
                setInbox((before) => ({ ...before, settings }))
                backToOverview()
              }}
              onError={showError}
            />
          )}

          {view.place === 'handOver' && (
            <HandOver
              inbox={inbox}
              onBack={() => setView({ place: 'overview' })}
              onWritten={backToOverview}
              onError={showError}
            />
          )}

          {view.place === 'feedback' && (
            <Feedback
              inbox={inbox}
              onBack={() => setView({ place: 'overview' })}
              onSaved={backToOverview}
              onError={showError}
            />
          )}

          {view.place === 'review' && (
            <Review
              entryId={'entryId' in view ? view.entryId : null}
              session={session}
              onError={showError}
              onFinish={() => setView({ place: 'overview' })}
            />
          )}

          {view.place === 'templates' && (
            <Templates
              kinds={kinds}
              profile={inbox.profile}
              onOpenKind={(name) => setView({ place: 'kind', name })}
              onSettings={() => setView({ place: 'settings' })}
              onOverview={() => setView({ place: 'overview' })}
            />
          )}

          {view.place === 'kind' && kinds.some((k) => k.name === view.name) && (
            <KindView
              key={view.name}
              kind={kinds.find((k) => k.name === view.name)!}
              profile={inbox.profile}
              onBack={() => setView({ place: 'templates' })}
              onSaved={(stored) => {
                setKinds((before) => before.map((k) => (k.name === stored.name ? stored : k)))
                // A removed value may have left the profile too; ask for it again.
                const name = inbox.settings?.profile
                if (name) {
                  api
                    .pipelineProfile(name)
                    .then((profile) => setInbox((before) => ({ ...before, profile })))
                    .catch(showError)
                }
              }}
              onError={showError}
            />
          )}

          {view.place === 'settings' && (
            <Settings
              status={status}
              theme={theme}
              onTheme={changeTheme}
              inbox={inbox.settings}
              profile={inbox.profile}
              onInbox={(settings) => setInbox((before) => ({ ...before, settings }))}
              onOverview={() => setView({ place: 'overview' })}
              onError={showError}
            />
          )}
        </div>
      </main>
    </div>
  )
}
