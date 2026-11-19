/**
 * What the client makes of an error from the shell: a refusal keeps what it
 * names, and any other error keeps its message without the name of its class.
 */

import { describe, expect, it, vi } from 'vitest'

const invoke = vi.hoisted(() => vi.fn())
vi.mock('@tauri-apps/api/core', () => ({ invoke }))

import { api, SubstraktError } from '../../src/api/client'

describe('an error from the shell', () => {
  it('keeps the items a refused approval names', async () => {
    invoke.mockRejectedValue({
      key: 'approval-refused',
      title: 'Refused',
      detail: null,
      status: 409,
      reason: 'hand-over-not-possible',
      items: ['payment_mode_code'],
    })
    const error = await api.approveInboxEntry(1).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(SubstraktError)
    expect((error as SubstraktError).items).toEqual(['payment_mode_code'])
  })

  it('keeps the message of any other error without its class name', async () => {
    invoke.mockRejectedValue(new TypeError('Load failed'))
    const error = await api.status().catch((e: unknown) => e)
    expect((error as SubstraktError).detail).toBe('Load failed')
  })
})
