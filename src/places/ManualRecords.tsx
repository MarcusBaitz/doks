/**
 * Documents opened by hand in this session, with „Ergebnis sichern“.
 *
 * Hidden in the pilot: no place renders this list (decision 2 of
 * docs/decisions.md, “Interface clarity”). It lived in Overview and stays here
 * for stage 3, when the path for documents read by hand comes back.
 */

import { Check, CircleAlert, Download } from 'lucide-react'
import { useState } from 'react'

import { useLanguage, useTexts } from '../i18n'
import { requestResult, saveResult } from '../results/save'
import { openValues, type DocumentRecord, type Session } from '../state/session'
import { Badge, SectionHeading } from '../ui/components'
import { timeOfDay } from '../ui/format'

/** Documents opened by hand in this session, held only in memory. */
export function ManualRecords({
  session,
  onReview,
  onError,
}: {
  session: Session
  onReview: () => void
  onError: (error: unknown) => void
}) {
  const t = useTexts().pilotOverview
  const [savingNow, setSavingNow] = useState<string | null>(null)
  if (session.records.length === 0) return null
  const fileResult = async (record: DocumentRecord) => {
    setSavingNow(record.id)
    try {
      const result = await requestResult(record)
      saveResult(result, record.fields, record.output, record.fileName)
      session.change(record.id, { state: 'filed' })
    } catch (f) {
      onError(f)
    } finally {
      setSavingNow(null)
    }
  }
  return (
    <>
      <SectionHeading className="mt-11">{t.manual}</SectionHeading>
      <div>
        {session.records.map((record) => (
          <HistoryRow
            key={record.id}
            record={record}
            saving={savingNow === record.id}
            onReview={() => onReview()}
            onFile={() => void fileResult(record)}
          />
        ))}
      </div>
    </>
  )
}

function HistoryRow({
  record,
  saving,
  onReview,
  onFile,
}: {
  record: DocumentRecord
  saving: boolean
  onReview: () => void
  onFile: () => void
}) {
  const texts = useTexts()
  const [language] = useLanguage()
  const openItem = record.state === 'waiting' && openValues(record).length > 0

  return (
    <div className="flex items-center gap-4 border-b border-line py-2.5 text-[13.5px] text-ink-2 last:border-b-0">
      <span className="tabular-number w-[46px] shrink-0 text-[12.5px] text-ink-3">
        {timeOfDay(record.readAt, language)}
      </span>
      <span className="min-w-0 truncate font-medium text-ink">{record.fileName}</span>
      <span className="truncate text-[12.5px]">{record.template}</span>

      <span className="ml-auto flex shrink-0 items-center gap-3">
        {openItem ? (
          <>
            <Badge tone="waiting">
              <CircleAlert size={12} aria-hidden="true" />
              {texts.document.state.waiting}
            </Badge>
            <button
              type="button"
              onClick={onReview}
              className="text-[12.5px] underline underline-offset-[3px] hover:text-ink"
            >
              {texts.overview.reviewNow}
            </button>
          </>
        ) : record.state === 'filed' ? (
          <Badge tone="good">
            <Check size={12} aria-hidden="true" />
            {texts.document.state.filed}
          </Badge>
        ) : (
          <>
            <Badge>{texts.document.state.read}</Badge>
            <button
              type="button"
              onClick={onFile}
              disabled={saving}
              className="flex items-center gap-1.5 text-[12.5px] underline underline-offset-[3px] hover:text-ink disabled:opacity-50"
            >
              <Download size={13} aria-hidden="true" />
              {texts.document.saveResult}
            </button>
          </>
        )}
      </span>
    </div>
  )
}
