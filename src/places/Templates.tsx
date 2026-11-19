/**
 * Templates, on screen „Belegarten“: the kinds the watched folder reads, in the
 * order of the active profile, each opening its values for change.
 *
 * The library of templates for documents read by hand is hidden in the pilot
 * (docs/decisions.md, “Interface clarity”); `HandTemplates` stays
 * for stage 3 and no place renders it.
 */

import { FileText, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { DocumentType, KindValues, ProfileDescription } from '../api/types'
import { useLanguage, useTexts } from '../i18n'
import {
  SectionHeading,
  Surface,
  Card,
  Button,
  Header,
  Empty,
  SearchInput,
  Title,
} from '../ui/components'
import { relativeTime } from '../ui/format'
import { useKeys } from '../ui/keys'

interface Props {
  kinds: KindValues[]
  profile: ProfileDescription | null
  onOpenKind: (name: string) => void
  onSettings: () => void
  onOverview: () => void
}

/** The kinds of the active profile, in its order; a kind of no profile is not read. */
export function kindsOfFolder(kinds: KindValues[], profile: ProfileDescription | null): KindValues[] {
  return (profile?.kinds ?? []).flatMap((p) => kinds.filter((k) => k.name === p.name))
}

export function Templates({ kinds, profile, onOpenKind, onSettings, onOverview }: Props) {
  const t = useTexts().kinds
  const read = kindsOfFolder(kinds, profile)
  useKeys(read.length === 0 ? onSettings : onOverview)
  if (read.length === 0) {
    return (
      <Surface wide>
        <Header>
          <Title subtitle={t.listSubtitle}>{t.title}</Title>
        </Header>
        <Card>
          <Empty
            title={t.none}
            detail={t.noneDetail}
            symbol={<FileText size={22} />}
            action={
              <Button variant="primary" large onClick={onSettings}>
                {t.toSettings}
              </Button>
            }
          />
        </Card>
      </Surface>
    )
  }
  return (
    <Surface wide>
      <Header>
        <Title subtitle={t.listSubtitle}>{t.title}</Title>
        <Button variant="primary" onClick={onOverview}>
          {t.toOverview}
        </Button>
      </Header>
      <KindList kinds={read} onOpen={onOpenKind} />
    </Surface>
  )
}

/** One row per kind, clickable across its width, with its number of values. */
function KindList({ kinds, onOpen }: { kinds: KindValues[]; onOpen: (name: string) => void }) {
  const t = useTexts().kinds
  return (
    <Card className="overflow-hidden">
      {kinds.map((kind) => (
        <button
          key={kind.name}
          type="button"
          onClick={() => onOpen(kind.name)}
          className="flex w-full items-center gap-4 border-b border-line px-6 py-3.5 text-left transition-colors duration-(--dur-1) last:border-b-0 hover:bg-card-2"
        >
          <span className="grid size-[34px] shrink-0 place-items-center rounded-sm bg-card-2 text-ink-3">
            <FileText size={16} aria-hidden="true" />
          </span>
          <span className="min-w-0 truncate font-medium tracking-[-0.01em]">{kind.title}</span>
          <span className="ml-auto shrink-0 text-[13px] text-ink-2">{t.values(kind.values.length)}</span>
        </button>
      ))}
    </Card>
  )
}

interface HandProps {
  templates: DocumentType[]
  onOpen: (typeId: number) => void
  onNew: () => void
}

/** Number of templates shown in the recent section. */
const RECENT = 5

/** The library of templates for documents read by hand; hidden in the pilot. */
export function HandTemplates({ templates, onOpen, onNew }: HandProps) {
  const texts = useTexts()
  const [language] = useLanguage()
  const [searchValue, setSearchValue] = useState('')

  const found = useMemo(() => {
    const s = searchValue.trim().toLowerCase()
    if (!s) return templates
    return templates.filter(
      (v) =>
        v.name.toLowerCase().includes(s) || v.description.toLowerCase().includes(s),
    )
  }, [templates, searchValue])

  // The API order is recent-first; the complete section is alphabetical.
  const alphabetical = useMemo(
    () => [...found].sort((a, b) => a.name.localeCompare(b.name, language)),
    [found, language],
  )

  if (templates.length === 0) {
    return (
      <Surface wide>
        <Header>
          <Title subtitle={texts.templates.subtitle}>{texts.templates.title}</Title>
        </Header>
        <Card>
          <Empty
            title={texts.templates.none}
            detail={texts.templates.noneDetail}
            symbol={<FileText size={22} />}
            action={
              <Button variant="primary" large onClick={onNew}>
                <Plus size={16} />
                {texts.templates.newLabel}
              </Button>
            }
          />
        </Card>
      </Surface>
    )
  }

  return (
    <Surface wide>
      <Header>
        <Title subtitle={texts.templates.subtitle}>{texts.templates.title}</Title>
        <Button variant="primary" onClick={onNew}>
          <Plus size={16} />
          {texts.templates.newLabel}
        </Button>
      </Header>

      <div className="mb-5 flex items-center gap-4">
        <SearchInput valueText={searchValue} onChange={setSearchValue} placeholder={texts.templates.search} />
        <span className="text-[13px] text-ink-3">
          {texts.templates.count(found.length)}
        </span>
      </div>

      {found.length === 0 ? (
        <Card>
          <p className="px-7 py-10 text-center text-[13.5px] text-ink-2">
            {texts.templates.nothingFound}
          </p>
        </Card>
      ) : (
        <>
          {!searchValue && templates.length > RECENT && (
            <>
              <SectionHeading>{texts.templates.lastUsed}</SectionHeading>
              <Card className="mb-9 overflow-hidden">
                {templates.slice(0, RECENT).map((v) => (
                  <Row key={v.id} template={v} onOpen={onOpen} />
                ))}
              </Card>
            </>
          )}

          <SectionHeading>{texts.templates.all}</SectionHeading>
          <Card className="overflow-hidden">
            {alphabetical.map((v) => (
              <Row key={v.id} template={v} onOpen={onOpen} />
            ))}
          </Card>
        </>
      )}
    </Surface>
  )
}

function Row({
  template,
  onOpen,
}: {
  template: DocumentType
  onOpen: (typeId: number) => void
}) {
  const texts = useTexts()
  const [language] = useLanguage()
  return (
    <button
      type="button"
      onClick={() => template.id !== null && onOpen(template.id)}
      className="flex w-full items-center gap-4 border-b border-line px-6 py-3.5 text-left transition-colors duration-(--dur-1) last:border-b-0 hover:bg-card-2"
    >
      <span className="grid size-[34px] shrink-0 place-items-center rounded-sm bg-card-2 text-ink-3">
        <FileText size={16} aria-hidden="true" />
      </span>

      <span className="min-w-0">
        <span className="block truncate font-medium tracking-[-0.01em]">
          {template.name}
        </span>
        <span className="mt-0.5 block text-[12.5px] text-ink-3">
          {texts.templates.values(template.value_count)}
          {template.description && ` · ${template.description}`}
        </span>
      </span>

      <span className="ml-auto shrink-0 text-right text-[13px] text-ink-2">
        {relativeTime(template.updated_at, language, texts)}
        <span className="block text-[11.5px] text-ink-3">{texts.templates.changed}</span>
      </span>
    </button>
  )
}
