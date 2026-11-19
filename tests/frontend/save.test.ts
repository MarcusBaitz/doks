/**
 * The saved result must carry what the clerk decided in review. A value
 * confirmed without a location is only in the session; if the request for the
 * result does not name it, the sidecar leaves it out.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

const invoke = vi.hoisted(() => vi.fn())
vi.mock('@tauri-apps/api/core', () => ({ invoke }))

import type { Export, FieldSpec } from '../../src/api/types'
import { asTable, requestResult } from '../../src/results/save'
import type { DocumentRecord } from '../../src/state/session'

const fields = [{ name: 'policy_number', label: 'Nummer' }] as FieldSpec[]

const record = {
  docId: 'doc-1',
  fields,
  corrections: { insurer: 'Beispiel AG' },
  confirmed: ['policy_number'],
} as unknown as DocumentRecord

describe('requestResult', () => {
  beforeEach(() => invoke.mockReset())

  it('names the values the clerk confirmed, next to the corrections', async () => {
    invoke.mockResolvedValue({ data: {} })

    await requestResult(record)

    expect(invoke).toHaveBeenCalledWith('export', {
      docId: 'doc-1',
      fields,
      manual: { insurer: 'Beispiel AG' },
      confirmed: ['policy_number'],
    })
  })

  it('returns a confirmed value so that it reaches the saved table', async () => {
    const result = { data: { policy_number: 'K 12 345' } } as unknown as Export
    invoke.mockResolvedValue(result)

    const received = await requestResult(record)

    expect(asTable(fields, received.data)).toContain('K 12 345')
  })
})
