export interface BreakoutTiming {
  status: string
  started_at: string | null
  ends_at: string | null
  duration_seconds?: number | null
}

export interface TimerSnapshot {
  remaining: number
  elapsed: number
  hasTimer: boolean
  isCountdown: boolean
  isExpired: boolean
}

const IDLE: TimerSnapshot = {
  remaining: 0,
  elapsed: 0,
  hasTimer: false,
  isCountdown: false,
  isExpired: false,
}

/**
 * Derive the timer display from server timestamps and a clock reading.
 *
 * Pure so that the very first render already knows whether the session is
 * expired: the recall banner must never fire because a counter started at 0.
 */
export const computeTimerSnapshot = (
  timing: BreakoutTiming | null | undefined,
  now: number
): TimerSnapshot => {
  const isActive = timing?.status === 'active' || timing?.status === 'closing'
  if (!timing || !isActive) return IDLE

  const startedAt = timing.started_at ? Date.parse(timing.started_at) : now
  const endsAt = timing.ends_at ? Date.parse(timing.ends_at) : null
  const elapsed = Math.max(0, Math.floor((now - startedAt) / 1000))
  const remaining =
    endsAt === null ? 0 : Math.max(0, Math.ceil((endsAt - now) / 1000))

  return {
    remaining,
    elapsed,
    hasTimer: true,
    isCountdown: endsAt !== null,
    isExpired: endsAt !== null && remaining <= 0,
  }
}

export const isSameTimerSnapshot = (a: TimerSnapshot, b: TimerSnapshot) =>
  a.remaining === b.remaining &&
  a.elapsed === b.elapsed &&
  a.hasTimer === b.hasTimer &&
  a.isCountdown === b.isCountdown &&
  a.isExpired === b.isExpired
