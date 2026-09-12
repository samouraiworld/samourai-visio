import { describe, expect, it } from 'vitest'
import {
  resolveAssignmentAction,
  type AssignmentInput,
} from './assignmentActions'

const assignment = {
  breakout_room_id: 'room-1',
  breakout_room_name: 'Room 1',
  livekit_room_name: 'breakout_s_0',
}

const base: AssignmentInput = {
  status: 'active',
  revision: 3,
  assignment,
  isExpired: false,
  isTransitioning: false,
  isModeratorVisiting: false,
  currentBreakoutRoomLkName: null,
  connectionLost: false,
  pausedAssignmentRevision: null,
}

const resolve = (overrides: Partial<AssignmentInput>) =>
  resolveAssignmentAction({ ...base, ...overrides })

describe('resolveAssignmentAction', () => {
  it('moves a participant in the main room to their assigned room', () => {
    expect(resolve({})).toEqual({
      type: 'move',
      breakoutRoomId: 'room-1',
      breakoutRoomName: 'Room 1',
      revision: 3,
    })
  })

  it('does nothing while a transition is in flight', () => {
    expect(resolve({ isTransitioning: true })).toEqual({ type: 'none' })
  })

  it('does nothing when already connected to the assigned room', () => {
    expect(resolve({ currentBreakoutRoomLkName: 'breakout_s_0' })).toEqual({
      type: 'none',
    })
  })

  it('rejoins the assigned room after the connection to it was lost', () => {
    const action = resolve({
      currentBreakoutRoomLkName: 'breakout_s_0',
      connectionLost: true,
    })
    expect(action.type).toBe('move')
  })

  it('respects a deliberate return to main until the assignment changes', () => {
    expect(resolve({ pausedAssignmentRevision: 3 })).toEqual({ type: 'none' })
    expect(resolve({ pausedAssignmentRevision: 2 }).type).toBe('move')
  })

  it('moves a participant between breakout rooms on reassignment', () => {
    expect(resolve({ currentBreakoutRoomLkName: 'breakout_s_1' }).type).toBe(
      'move'
    )
  })

  it('returns to main when the assignment was removed', () => {
    expect(
      resolve({ assignment: null, currentBreakoutRoomLkName: 'breakout_s_0' })
    ).toEqual({ type: 'return-to-main' })
    expect(resolve({ assignment: null })).toEqual({ type: 'none' })
  })

  it('returns after close from a breakout room and clears from main', () => {
    for (const status of ['closing', 'closed'] as const) {
      expect(
        resolve({ status, currentBreakoutRoomLkName: 'breakout_s_0' })
      ).toEqual({ type: 'return-after-close' })
      expect(resolve({ status })).toEqual({ type: 'clear' })
    }
  })

  it('waits for the server close once the timer has expired', () => {
    expect(resolve({ isExpired: true })).toEqual({ type: 'none' })
    expect(
      resolve({ isExpired: true, currentBreakoutRoomLkName: 'breakout_s_1' })
    ).toEqual({ type: 'none' })
  })

  it('leaves a visiting moderator alone', () => {
    expect(resolve({ isModeratorVisiting: true })).toEqual({ type: 'none' })
  })

  it('waits while the session is still activating', () => {
    expect(resolve({ status: 'activating' })).toEqual({ type: 'none' })
  })
  it('returns a disconnected visiting manager to the main meeting', () => {
    expect(
      resolve({ isModeratorVisiting: true, connectionLost: true })
    ).toEqual({ type: 'return-to-main' })
  })

  it('recovers to main after closure even when the first breakout join never connected', () => {
    expect(resolve({ status: 'closed', connectionLost: true })).toEqual({
      type: 'return-after-close',
    })
  })
})
