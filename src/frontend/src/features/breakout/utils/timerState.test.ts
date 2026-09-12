import { describe, expect, it } from 'vitest'
import { computeTimerSnapshot } from './timerState'

const now = Date.parse('2026-09-07T10:00:00Z')
const iso = (offsetSeconds: number) =>
  new Date(now + offsetSeconds * 1000).toISOString()

describe('computeTimerSnapshot', () => {
  it('is not expired on the first computation of a session with time left', () => {
    const snapshot = computeTimerSnapshot(
      { status: 'active', started_at: iso(-30), ends_at: iso(570) },
      now
    )
    expect(snapshot).toEqual({
      remaining: 570,
      elapsed: 30,
      hasTimer: true,
      isCountdown: true,
      isExpired: false,
    })
  })

  it('expires only once ends_at has passed', () => {
    const timing = { status: 'active', started_at: iso(-600), ends_at: iso(0) }
    expect(computeTimerSnapshot(timing, now - 1000).isExpired).toBe(false)
    expect(computeTimerSnapshot(timing, now).isExpired).toBe(true)
    expect(computeTimerSnapshot(timing, now + 5000).remaining).toBe(0)
  })

  it('never expires an untimed session', () => {
    const snapshot = computeTimerSnapshot(
      { status: 'active', started_at: iso(-30), ends_at: null },
      now
    )
    expect(snapshot.isCountdown).toBe(false)
    expect(snapshot.isExpired).toBe(false)
    expect(snapshot.elapsed).toBe(30)
  })

  it('has no timer outside active and closing', () => {
    for (const status of ['configuring', 'activating', 'closed']) {
      const snapshot = computeTimerSnapshot(
        { status, started_at: iso(-30), ends_at: iso(-1) },
        now
      )
      expect(snapshot.hasTimer).toBe(false)
      expect(snapshot.isExpired).toBe(false)
    }
    expect(computeTimerSnapshot(null, now).hasTimer).toBe(false)
  })

  it('treats a closing session as still timed', () => {
    const timing = { status: 'closing', started_at: iso(-5), ends_at: iso(5) }
    expect(computeTimerSnapshot(timing, now).hasTimer).toBe(true)
  })
})
