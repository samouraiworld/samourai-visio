import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'
import {
  bindBreakoutToMainRoom,
  breakoutStore,
  clearBreakoutState,
  clearMatchingPendingHelpAcknowledgement,
  completeBreakoutTransition,
} from './breakout'

describe('completeBreakoutTransition', () => {
  beforeAll(() => {
    const values = new Map<string, string>()
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value)
      },
      removeItem: (key: string) => {
        values.delete(key)
      },
      clear: () => values.clear(),
      key: (index: number) => [...values.keys()][index] ?? null,
      get length() {
        return values.size
      },
    } satisfies Storage)
  })

  afterAll(() => vi.unstubAllGlobals())

  beforeEach(() => {
    clearBreakoutState()
    breakoutStore.activeSessionId = 'session-1'
    breakoutStore.mainRoomId = 'main-1'
    breakoutStore.isTransitioning = true
    breakoutStore.pendingMediaIntent = { camera: false, microphone: true }
  })

  it('preserves the active assignment after an ordinary room move', () => {
    breakoutStore.assignedRoomId = 'room-1'

    completeBreakoutTransition()

    expect(breakoutStore.activeSessionId).toBe('session-1')
    expect(breakoutStore.assignedRoomId).toBe('room-1')
    expect(breakoutStore.pendingMediaIntent).toBeNull()
    expect(breakoutStore.isTransitioning).toBe(false)
  })

  it('clears session state only after a closing return connects', () => {
    breakoutStore.clearAfterTransition = true
    breakoutStore.pendingHelpAcknowledgement = {
      roomId: 'main-1',
      sessionId: 'session-1',
      helpRequestId: 'help-1',
      expectedBreakoutRoomId: 'breakout-1',
      expectedLivekitRoomName: 'breakout-livekit-1',
      assignmentRevision: 1,
    }

    completeBreakoutTransition()

    expect(breakoutStore.activeSessionId).toBeNull()
    expect(breakoutStore.mainRoomId).toBeNull()
    expect(breakoutStore.pendingMediaIntent).toBeNull()
    expect(breakoutStore.isTransitioning).toBe(false)
    expect(breakoutStore.clearAfterTransition).toBe(false)
    expect(breakoutStore.pendingHelpAcknowledgement).toBeNull()
  })

  it('preserves a media restoration error after a closing return connects', () => {
    breakoutStore.clearAfterTransition = true
    breakoutStore.transitionError = 'camera_restore_failed'

    completeBreakoutTransition()

    expect(breakoutStore.activeSessionId).toBeNull()
    expect(breakoutStore.transitionError).toBe('camera_restore_failed')
  })

  it('does not let an older connection erase a newer help target', () => {
    const older = {
      roomId: 'main-1',
      sessionId: 'session-1',
      helpRequestId: 'help-1',
      expectedBreakoutRoomId: 'breakout-1',
      expectedLivekitRoomName: 'breakout-livekit-1',
      assignmentRevision: 1,
    }
    breakoutStore.pendingHelpAcknowledgement = {
      ...older,
      helpRequestId: 'help-2',
      expectedBreakoutRoomId: 'breakout-2',
      expectedLivekitRoomName: 'breakout-livekit-2',
      assignmentRevision: 2,
    }

    expect(clearMatchingPendingHelpAcknowledgement(older)).toBe(false)
    expect(breakoutStore.pendingHelpAcknowledgement?.helpRequestId).toBe(
      'help-2'
    )
  })

  it('clears the matching help target after a target-room attempt', () => {
    const pending = {
      roomId: 'main-1',
      sessionId: 'session-1',
      helpRequestId: 'help-1',
      expectedBreakoutRoomId: 'breakout-1',
      expectedLivekitRoomName: 'breakout-livekit-1',
      assignmentRevision: 1,
    }
    breakoutStore.pendingHelpAcknowledgement = pending

    expect(clearMatchingPendingHelpAcknowledgement(pending)).toBe(true)
    expect(breakoutStore.pendingHelpAcknowledgement).toBeNull()
  })
})

describe('bindBreakoutToMainRoom', () => {
  beforeAll(() => {
    const values = new Map<string, string>()
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value)
      },
      removeItem: (key: string) => {
        values.delete(key)
      },
      clear: () => values.clear(),
      key: (index: number) => [...values.keys()][index] ?? null,
      get length() {
        return values.size
      },
    } satisfies Storage)
  })

  afterAll(() => vi.unstubAllGlobals())

  beforeEach(() => {
    clearBreakoutState()
  })

  it('retains restored state for the same parent meeting', () => {
    breakoutStore.mainRoomId = 'main-1'
    breakoutStore.activeSessionId = 'session-1'

    bindBreakoutToMainRoom('main-1', 'room-slug')

    expect(breakoutStore.activeSessionId).toBe('session-1')
    expect(breakoutStore.mainRoomSlug).toBe('room-slug')
  })

  it('clears restored state when entering another meeting', () => {
    breakoutStore.mainRoomId = 'main-1'
    breakoutStore.activeSessionId = 'session-1'
    breakoutStore.assignedRoomId = 'breakout-1'

    bindBreakoutToMainRoom('main-2', 'other-room')

    expect(breakoutStore.activeSessionId).toBeNull()
    expect(breakoutStore.assignedRoomId).toBeNull()
    expect(breakoutStore.mainRoomId).toBe('main-2')
    expect(breakoutStore.mainRoomSlug).toBe('other-room')
  })
})
