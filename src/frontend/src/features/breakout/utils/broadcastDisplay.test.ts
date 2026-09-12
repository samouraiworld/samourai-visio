import { describe, expect, it } from 'vitest'
import { shouldShowBroadcast } from './broadcastDisplay'

const now = Date.parse('2026-09-07T10:00:00Z')
const at = (offsetSeconds: number) =>
  new Date(now + offsetSeconds * 1000).toISOString()

describe('shouldShowBroadcast', () => {
  it('shows a fresh announcement once', () => {
    expect(shouldShowBroadcast(null, at(-2), now)).toBe(true)
    expect(shouldShowBroadcast(at(-2), at(-2), now)).toBe(false)
  })

  it('shows a newer announcement after an older one', () => {
    expect(shouldShowBroadcast(at(-60), at(-2), now)).toBe(true)
  })

  it('never replays an announcement first seen long after it was sent', () => {
    expect(shouldShowBroadcast(null, at(-40 * 60), now)).toBe(false)
    expect(shouldShowBroadcast(null, at(-11), now)).toBe(false)
  })
})
