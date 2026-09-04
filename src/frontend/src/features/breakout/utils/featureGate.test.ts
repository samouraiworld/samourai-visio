import { describe, expect, it } from 'vitest'
import { canUseBreakoutRooms } from './featureGate'

describe('breakout feature gate', () => {
  it.each([undefined, false])(
    'keeps the feature hidden when the runtime flag is %s',
    (isEnabled) => {
      expect(canUseBreakoutRooms(isEnabled, true)).toBe(false)
    }
  )

  it('keeps the feature hidden from non-moderators', () => {
    expect(canUseBreakoutRooms(true, false)).toBe(false)
  })

  it('shows the feature to moderators only when explicitly enabled', () => {
    expect(canUseBreakoutRooms(true, true)).toBe(true)
  })
})
