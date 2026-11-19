// @vitest-environment happy-dom
/**
 * Starting to read a folder and changing Settings as a clerk does it, with
 * clicks and keys in a DOM against the whole application: „Ordner einlesen“
 * stays a path of Overview, Esc leaves it without storing anything, the start
 * lands on Overview while it reads, and every line of Settings stores itself
 * and confirms in place without moving focus. Settings has no subtitle, describes the way of working in
 * one line of folder structure and has one folder, whose refusal stands
 * beside it. The sidecar is a Tauri
 * `invoke` answering from fixed data.
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: { workerSrc: '' } }))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '' }))

const FOLDER = '/home/sachbearbeitung/Scans/Neukunden'
const picked = vi.hoisted(() => ({ path: '' as string | null }))
vi.mock('@tauri-apps/plugin-dialog', () => ({ open: async () => picked.path }))

const invoke = vi.hoisted(() => vi.fn())
vi.mock('@tauri-apps/api/core', () => ({ invoke }))

import type { InboxSettings, ProfileDescription } from '../../src/api/types'
import { App } from '../../src/App'
import { de } from '../../src/i18n/de'
import { en } from '../../src/i18n/en'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const PROFILE: ProfileDescription = {
  name: 'broker',
  title: 'Broker program',
  target: 'gdv',
  customer_folder_level: 1,
  kinds: [{ name: 'policy', title: 'Police', values: [] }],
  overview_columns: {},
}

/** What the sidecar holds; a choice changes it as the real one does. */
function sidecar(start: Partial<InboxSettings> = {}, profile: ProfileDescription = PROFILE) {
  let settings: InboxSettings = {
    folder: null,
    handover_folder: null,
    profile: 'broker',
    profiles: [{ name: 'broker', title: 'Broker program' }, { name: 'second', title: 'Second' }],
    watching: false,
    retention_days: 90,
    ...start,
  }
  invoke.mockImplementation(async (command: string, args?: Record<string, unknown>) => {
    switch (command) {
      case 'sidecar_status':
        return { connected: true, version: 'dev', mode: 'airgap', backend: 'sidecar' }
      case 'inbox_settings':
        return settings
      case 'inbox_imports':
        return settings.folder
          ? [{ id: 1, folder: settings.folder, started_at: new Date().toISOString(), finished_at: null }]
          : []
      case 'pipeline_profile':
        return profile
      case 'choose_inbox_settings': {
        const { folder, profile, retentionDays } = args as Record<string, string & number>
        settings = {
          ...settings,
          ...(folder ? { folder, handover_folder: `${folder}/Ausgabe`, watching: true } : {}),
          ...(profile ? { profile } : {}),
          ...(retentionDays ? { retention_days: retentionDays } : {}),
        }
        return settings
      }
      default:
        return []
    }
  })
}

let root: Root
let host: HTMLElement

async function settle() {
  for (let i = 0; i < 5; i++) await act(async () => await new Promise((r) => setTimeout(r, 0)))
}

async function mount(language: 'de' | 'en' = 'de') {
  localStorage.setItem('substrakt.language', language)
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
  await act(async () => root.render(<App />))
  await settle()
}

const button = (text: string) =>
  [...host.querySelectorAll('button')].find((b) => b.textContent?.trim() === text)!
const headline = () => host.querySelector('h1')?.textContent
const marked = () => host.querySelector('[aria-current="page"]')?.textContent
const chosen = () => invoke.mock.calls.filter(([command]) => command === 'choose_inbox_settings')
async function click(element: HTMLElement) {
  await act(async () => element.click())
  await settle()
}
async function press(key: string) {
  await act(async () => window.dispatchEvent(new KeyboardEvent('keydown', { key })))
  await settle()
}

beforeEach(() => {
  invoke.mockReset()
  picked.path = FOLDER
})
afterEach(() => {
  act(() => root.unmount())
  host.remove()
})

describe('„Ordner einlesen“ is one path from Overview', () => {
  it('opens the folder question while the sidebar keeps Overview (Z6.1)', async () => {
    sidecar()
    await mount()
    await click(button(de.pilotOverview.chooseFolder))
    expect(headline()).toBe(de.readFolder.title)
    expect(marked()).toContain(de.places.overview)
  })

  it('enables „Einlesen starten“ only once a folder is chosen, and names it (Z6.2)', async () => {
    sidecar()
    await mount()
    await click(button(de.pilotOverview.chooseFolder))
    expect(button(de.readFolder.start).disabled).toBe(true)
    await click(button(de.readFolder.choose))
    expect(button(de.readFolder.start).disabled).toBe(false)
    expect(host.textContent).toContain('Neukunden')
    expect(chosen()).toHaveLength(0)
  })

  it('stores the folder on start and shows Overview reading it (Z6.3)', async () => {
    sidecar()
    await mount()
    await click(button(de.pilotOverview.chooseFolder))
    await click(button(de.readFolder.choose))
    await click(button(de.readFolder.start))
    expect(chosen()).toEqual([['choose_inbox_settings', { folder: FOLDER }]])
    expect(headline()).toBe(de.pilotOverview.readingTitle(0))
    expect(marked()).toContain(de.places.overview)
  })

  it('keeps the start disabled when the folder picker is cancelled', async () => {
    sidecar()
    picked.path = null
    await mount()
    await click(button(de.pilotOverview.chooseFolder))
    await click(button(de.readFolder.choose))
    expect(button(de.readFolder.start).disabled).toBe(true)
  })

  it('stays on the folder question with the start enabled again when the sidecar refuses the folder', async () => {
    sidecar()
    const answer = invoke.getMockImplementation()!
    invoke.mockImplementation(async (command: string, args?: Record<string, unknown>) => {
      if (command === 'choose_inbox_settings') throw { key: 'path-not-allowed', title: '', status: 403 }
      return answer(command, args)
    })
    await mount()
    await click(button(de.pilotOverview.chooseFolder))
    await click(button(de.readFolder.choose))
    await click(button(de.readFolder.start))
    expect(headline()).toBe(de.readFolder.title)
    expect(host.querySelector('[role="alert"]')).not.toBeNull()
    expect(button(de.readFolder.start).disabled).toBe(false)
  })

  it('goes back to Overview on Esc and stores nothing, even after a folder was picked (Z6.3)', async () => {
    sidecar()
    await mount()
    await click(button(de.pilotOverview.chooseFolder))
    await click(button(de.readFolder.choose))
    await press('Escape')
    expect(headline()).toBe(de.pilotOverview.startTitle)
    expect(chosen()).toHaveLength(0)
  })
})

describe('every line of Settings takes effect at once', () => {
  async function openSettings() {
    sidecar({ folder: '/scans', handover_folder: '/scans/Ausgabe', watching: true })
    await mount()
    await click(button(de.places.settings))
    expect(headline()).toBe(de.settings.title)
  }

  async function choose(select: HTMLSelectElement, value: string) {
    await act(async () => {
      select.value = value
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await settle()
  }

  it('stores folder, way of working and retention through the same call, with no save button (Z5.1)', async () => {
    await openSettings()
    expect(host.textContent).not.toMatch(/speichern/i)
    await click(button(de.pilotSettings.change))
    await choose(host.querySelector(`select[aria-label="${de.pilotSettings.profile}"]`)!, 'second')
    await choose(host.querySelector(`select[aria-label="${de.pilotSettings.retentionLabel}"]`)!, '30')
    expect(chosen()).toEqual([
      ['choose_inbox_settings', { folder: FOLDER }],
      ['choose_inbox_settings', { profile: 'second' }],
      ['choose_inbox_settings', { retentionDays: 30 }],
    ])
  })

  it('confirms the change beside its line as a status message and keeps focus (Z5.2)', async () => {
    await openSettings()
    const retention = host.querySelector<HTMLSelectElement>(`select[aria-label="${de.pilotSettings.retentionLabel}"]`)!
    retention.focus()
    await choose(retention, '365')
    expect(document.activeElement).toBe(retention)
    const confirmations = [...host.querySelectorAll('[role="status"]')].filter((s) => s.textContent === de.pilotSettings.saved)
    expect(confirmations).toHaveLength(1)
    expect(confirmations[0]!.parentElement).toBe(retention.parentElement)
  })
})

describe('Settings says less and has one folder', () => {
  async function settingsIn(language: 'de' | 'en', profile: ProfileDescription = PROFILE) {
    sidecar({ folder: '/scans', handover_folder: '/scans/Ausgabe', watching: true }, profile)
    await mount(language)
    await click(button(language === 'de' ? de.places.settings : en.places.settings))
  }

  it('renders no subtitle under the title, in German and English (Z8.1)', async () => {
    for (const language of ['de', 'en'] as const) {
      await settingsIn(language)
      const title = host.querySelector('h1')!
      expect(title.textContent).toBe((language === 'de' ? de : en).settings.title)
      expect(title.nextElementSibling).toBeNull()
      act(() => root.unmount())
      host.remove()
    }
    await mount()
  })

  it('describes the way of working in one line of folder structure; the target stands only in the select (Z8.2)', async () => {
    for (const [language, line] of [
      ['de', 'Ordnerstruktur: Kundenname/Belege'],
      ['en', 'Folder structure: customer name/documents'],
    ] as const) {
      await settingsIn(language)
      const select = host.querySelector('select')!
      expect(select.parentElement!.textContent).toContain(line)
      const terms = [...host.querySelectorAll('dt')].map((d) => d.textContent)
      expect(terms).not.toContain('Kunde')
      expect(terms).not.toContain('Customer')
      expect(terms).not.toContain('Police')
      expect(host.textContent).not.toMatch(/Geht an|Goes to/)
      expect(host.textContent!.split('Broker program')).toHaveLength(2)
      expect(select.textContent).toContain('Broker program')
      act(() => root.unmount())
      host.remove()
    }
    await mount()
  })

  it('renders its own line for a profile without a customer folder and for one two levels down (Z8.2)', async () => {
    for (const [level, line] of [
      [null, 'Ordnerstruktur: Belege'],
      [2, 'Ordnerstruktur: Ordner/Kundenname/Belege'],
    ] as const) {
      await settingsIn('de', { ...PROFILE, customer_folder_level: level })
      expect(host.textContent).toContain(line)
      act(() => root.unmount())
      host.remove()
    }
    await mount()
  })

  it('has one folder line with one folder button (Z9.7)', async () => {
    await settingsIn('de')
    const folderButtons = [...host.querySelectorAll('button')].filter(
      (b) => b.textContent === de.pilotSettings.change || b.textContent === de.pilotSettings.choose,
    )
    expect(folderButtons).toHaveLength(1)
    expect(host.querySelectorAll('.font-mono')).toHaveLength(1)
    expect(host.textContent).not.toContain('/scans/Ausgabe')
  })

  it('names the refusal of a file called „Ausgabe“ beside the folder line and keeps the folder (Z9.3)', async () => {
    await settingsIn('de')
    const answer = invoke.getMockImplementation()!
    invoke.mockImplementation(async (command: string, args?: Record<string, unknown>) => {
      if (command === 'choose_inbox_settings') throw { key: 'output-name-taken', title: '', status: 409 }
      return answer(command, args)
    })
    await click(button(de.pilotSettings.change))
    const alerts = [...host.querySelectorAll('[role="alert"]')]
    expect(alerts).toHaveLength(1)
    expect(alerts[0]!.textContent).toBe(de.errors.messages['output-name-taken'])
    expect(alerts[0]!.parentElement).toBe(button(de.pilotSettings.change).parentElement)
    expect(host.textContent).toContain('/scans')
    expect(en.errors.messages['output-name-taken']).toMatch(/Ausgabe/)
  })
})
