import { useEffect, useRef, useState } from 'react'

export interface BreakoutTiming {
  status: string
  started_at: string | null
  ends_at: string | null
  duration_seconds?: number | null
}

export const useBreakoutTimer = (timing?: BreakoutTiming | null) => {
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [remaining, setRemaining] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const isActive = timing?.status === 'active' || timing?.status === 'closing'
  const hasDuration = !!timing?.ends_at

  useEffect(() => {
    if (!timing || !isActive) {
      setRemaining(0)
      setElapsed(0)
      return
    }

    const startedAt = timing.started_at
      ? new Date(timing.started_at).getTime()
      : Date.now()
    const endsAt = timing.ends_at ? new Date(timing.ends_at).getTime() : null

    const tick = () => {
      const now = Date.now()
      setElapsed(Math.max(0, Math.floor((now - startedAt) / 1000)))
      if (endsAt !== null) {
        setRemaining(Math.max(0, Math.ceil((endsAt - now) / 1000)))
      }
    }

    tick()
    intervalRef.current = setInterval(tick, 1000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [isActive, timing])

  return {
    remaining,
    elapsed,
    hasTimer: isActive,
    isCountdown: hasDuration,
    isExpired: hasDuration && remaining <= 0,
  }
}
