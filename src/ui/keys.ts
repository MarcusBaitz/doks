/**
 * The same two keys on every place (R7 of the ui-expert skill): Enter takes the
 * screen's one dark step, Escape goes back. A place passes null where Enter
 * must take no step, as on a final decision (R12).
 */

import { useEffect, useRef } from 'react'

/** Elements that handle Enter themselves. */
const ENTER_OWNERS = ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'A', 'SUMMARY']

export function useKeys(primary: (() => void) | null, onEscape?: () => void) {
  const current = useRef({ primary, onEscape })
  current.current = { primary, onEscape }
  useEffect(() => {
    const keyHandler = (e: KeyboardEvent) => {
      const target = e.target as HTMLInputElement | null
      // A chosen option does nothing with Enter, so Enter goes on to the step it was chosen for.
      const owned = target !== null && ENTER_OWNERS.includes(target.tagName) && target.type !== 'radio'
      const { primary: step, onEscape: leave } = current.current
      if (e.key === 'Enter' && !owned && step) {
        e.preventDefault()
        step()
      } else if (e.key === 'Escape' && leave) {
        e.preventDefault()
        leave()
      }
    }
    window.addEventListener('keydown', keyHandler)
    return () => window.removeEventListener('keydown', keyHandler)
  }, [])
}
