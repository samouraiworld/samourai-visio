/**
 * Client-side timer for active breakout sessions.
 *
 * Supports both:
 * 1. Countdown mode (when duration_seconds is set).
 * 2. Elapsed mode (when session has no time limit).
 *
 * Updates the breakout store every second.
 */

import { useEffect, useRef, useState } from 'react'
import { useSnapshot } from 'valtio'
import { breakoutStore } from '../stores/breakout'

export const useBreakoutTimer = () => {
  const snap = useSnapshot(breakoutStore)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [elapsed, setElapsed] = useState(0)

  const session = snap.session
  const isActive = session?.status === 'active'
  const hasDuration =
    !!session?.duration_seconds && session.duration_seconds > 0

  useEffect(() => {
    if (!session || session.status !== 'active') {
      breakoutStore.timer = { remaining: 0, total: 0 }
      setElapsed(0)
      return
    }

    const startedAt = session.started_at
      ? new Date(session.started_at).getTime()
      : Date.now()

    if (hasDuration && session.duration_seconds) {
      const total = session.duration_seconds
      breakoutStore.timer.total = total

      const tick = () => {
        const passed = Math.floor((Date.now() - startedAt) / 1000)
        const rem = Math.max(0, total - passed)
        breakoutStore.timer.remaining = rem
      }

      tick()
      intervalRef.current = setInterval(tick, 1000)
    } else {
      // Unlimited / elapsed mode
      breakoutStore.timer = { remaining: 0, total: 0 }

      const tick = () => {
        setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)))
      }

      tick()
      intervalRef.current = setInterval(tick, 1000)
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [session, hasDuration])

  return {
    remaining: snap.timer.remaining,
    total: snap.timer.total,
    elapsed,
    hasTimer: isActive,
    isCountdown: hasDuration,
    isExpired: hasDuration && snap.timer.total > 0 && snap.timer.remaining <= 0,
  }
}
