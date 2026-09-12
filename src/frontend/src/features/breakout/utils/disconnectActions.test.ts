import { describe, expect, it } from 'vitest'
import { DisconnectReason } from 'livekit-client'
import {
  isRemovalAReassignment,
  resolveDisconnectAction,
} from './disconnectActions'
import type { BreakoutCurrentAssignment } from '../api/types'

const fresh = (
  overrides: Partial<BreakoutCurrentAssignment> = {}
): BreakoutCurrentAssignment => ({
  session_id: 's',
  revision: 1,
  status: 'active',
  started_at: null,
  ends_at: null,
  duration_seconds: null,
  assignment: {
    breakout_room_id: 'r1',
    breakout_room_name: 'Room 1',
    livekit_room_name: 'breakout_s_0',
  },
  help_request: null,
  last_broadcast: null,
  ...overrides,
})

const inMain = {
  isTransitioning: false,
  activeSessionId: 's',
  currentBreakoutRoomLkName: null,
}
const inBreakout = { ...inMain, currentBreakoutRoomLkName: 'breakout_s_0' }

describe('resolveDisconnectAction', () => {
  it('ignores disconnects that belong to a planned transition', () => {
    const input = { ...inBreakout, isTransitioning: true }
    expect(resolveDisconnectAction(input)).toBe('ignore')
  })

  it('leaves the meeting on a reason-less disconnect in the main room', () => {
    // The realistic trigger, in the position that has no recovery path.
    expect(resolveDisconnectAction(inMain)).toBe('leave')
  })

  it('leaves the meeting when no session is active', () => {
    const input = { ...inMain, activeSessionId: null }
    const reason = DisconnectReason.PARTICIPANT_REMOVED
    expect(resolveDisconnectAction({ ...input, reason })).toBe('leave')
  })

  it('verifies the assignment before treating a removal as an ejection', () => {
    const reason = DisconnectReason.PARTICIPANT_REMOVED
    expect(resolveDisconnectAction({ ...inMain, reason })).toBe(
      'verify-assignment'
    )
  })

  it('recovers from any unplanned disconnect inside a breakout room', () => {
    expect(resolveDisconnectAction(inBreakout)).toBe('recover-session')
    const deleted = DisconnectReason.ROOM_DELETED
    expect(resolveDisconnectAction({ ...inBreakout, reason: deleted })).toBe(
      'recover-session'
    )
  })

  it('does not recover from a deliberate leave or a duplicate identity', () => {
    const left = DisconnectReason.CLIENT_INITIATED
    const duplicate = DisconnectReason.DUPLICATE_IDENTITY
    expect(resolveDisconnectAction({ ...inBreakout, reason: left })).toBe(
      'leave'
    )
    expect(resolveDisconnectAction({ ...inBreakout, reason: duplicate })).toBe(
      'leave'
    )
  })

  it('leaves to the feedback page when the main room itself vanishes', () => {
    const deleted = DisconnectReason.ROOM_DELETED
    expect(resolveDisconnectAction({ ...inMain, reason: deleted })).toBe(
      'leave'
    )
  })
})

describe('isRemovalAReassignment', () => {
  it('is an ejection when removed from the main room', () => {
    expect(isRemovalAReassignment(null, fresh())).toBe(false)
  })

  it('is a reassignment when the assigned room differs from the one left', () => {
    expect(isRemovalAReassignment('breakout_s_1', fresh())).toBe(true)
  })

  it('is an ejection when the assignment did not change', () => {
    expect(isRemovalAReassignment('breakout_s_0', fresh())).toBe(false)
  })

  it('lets the close flow handle a removal from a closing session', () => {
    const closing = fresh({ status: 'closing' })
    expect(isRemovalAReassignment('breakout_s_0', closing)).toBe(true)
  })

  it('is a return to main when the assignment was removed', () => {
    const unassigned = fresh({ assignment: null })
    expect(isRemovalAReassignment('breakout_s_0', unassigned)).toBe(true)
  })
})
