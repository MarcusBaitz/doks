/** The odometer's timing and easing, without a browser frame loop. */

import { describe, expect, it } from 'vitest'

import { between, duration, ODOMETER } from '../../src/ui/odometer'

describe('the odometer', () => {
  it('keeps a step of one brisk and caps a long run', () => {
    expect(duration(4, 5)).toBe(ODOMETER.minMs + ODOMETER.msPerStep)
    expect(duration(5, 4)).toBe(duration(4, 5))
    expect(duration(0, 500)).toBe(ODOMETER.maxMs)
  })

  it('starts at the old number, ends at the new one and never overshoots', () => {
    expect(between(3, 9, 0)).toBe(3)
    expect(between(3, 9, 1)).toBe(9)
    expect(between(3, 9, 2)).toBe(9)
    expect(between(9, 3, -1)).toBe(9)
    let last = 3
    for (let t = 0; t <= 1; t += 0.05) {
      const shown = between(3, 9, t)
      expect(shown).toBeGreaterThanOrEqual(last)
      expect(shown).toBeLessThanOrEqual(9)
      last = shown
    }
  })
})
