/**
 * Counts that run from the old to the new number instead of jumping.
 *
 * The owner asked for it on 11 November 2026 (counts run like an odometer): one requestAnimationFrame loop drives
 * every counter, a number seen for the first time is not animated, and with
 * `prefers-reduced-motion: reduce` the number jumps.
 */

import { useEffect, useRef, useState } from 'react'

/** The duration grows with the distance, so a step of one stays brisk. */
export const ODOMETER = { minMs: 300, maxMs: 900, msPerStep: 120 }

export function duration(from: number, to: number): number {
  return Math.min(ODOMETER.maxMs, ODOMETER.minMs + ODOMETER.msPerStep * Math.abs(to - from))
}

/** The number shown at `t` between 0 and 1, eased out cubically. */
export function between(from: number, to: number, t: number): number {
  return Math.round(from + (to - from) * (1 - (1 - Math.min(1, Math.max(0, t))) ** 3))
}

interface Run {
  from: number
  to: number
  start: number
  ms: number
  show: (value: number) => void
}

const runs = new Set<Run>()
let frame = 0

function tick(now: number) {
  for (const run of runs) {
    const t = (now - run.start) / run.ms
    run.show(between(run.from, run.to, t))
    if (t >= 1) runs.delete(run)
  }
  frame = runs.size > 0 ? requestAnimationFrame(tick) : 0
}

function still(): boolean {
  return (
    typeof matchMedia !== 'function' || matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/** Returns the number to show for `value`, running towards it when it changes. */
export function useOdometer(value: number): number {
  const [shown, setShown] = useState(value)
  const current = useRef(value)

  useEffect(() => {
    const from = current.current
    if (from === value) return
    const show = (next: number) => {
      current.current = next
      setShown(next)
    }
    if (still() || typeof requestAnimationFrame !== 'function') {
      show(value)
      return
    }
    const run: Run = { from, to: value, start: performance.now(), ms: duration(from, value), show }
    runs.add(run)
    if (!frame) frame = requestAnimationFrame(tick)
    return () => {
      runs.delete(run)
    }
  }, [value])

  return shown
}
