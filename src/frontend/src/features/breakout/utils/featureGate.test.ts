import { describe, expect, it } from 'vitest'
import { canUseBreakoutRooms } from './featureGate'

describe('canUseBreakoutRooms', () => {
  it('requires management rights', () => {
    expect(canUseBreakoutRooms(true, false)).toBe(false)
    expect(canUseBreakoutRooms(true, false, true)).toBe(false)
  })

  it('opens for managers when the flag is on', () => {
    expect(canUseBreakoutRooms(true, true)).toBe(true)
    expect(canUseBreakoutRooms(undefined, true)).toBe(false)
    expect(canUseBreakoutRooms(false, true)).toBe(false)
  })

  it('stays open for managers of a session that already exists', () => {
    expect(canUseBreakoutRooms(false, true, true)).toBe(true)
    expect(canUseBreakoutRooms(undefined, true, true)).toBe(true)
  })
})
