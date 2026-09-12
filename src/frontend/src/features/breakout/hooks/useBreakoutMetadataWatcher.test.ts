// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  breakoutStore,
  clearBreakoutState,
  failBreakoutConnection,
} from '../stores/breakout'
import { useBreakoutMetadataWatcher } from './useBreakoutMetadataWatcher'

const mocks = vi.hoisted(() => ({
  move: vi.fn().mockResolvedValue('breakout_one'),
  returnToMain: vi.fn(),
  returnAfterClose: vi.fn(),
  refetch: vi.fn(),
  metadata: '',
  updatedAt: 1,
  assignment: {
    session_id: 'one',
    status: 'active',
    revision: 3,
    ends_at: null,
    assignment: {
      breakout_room_id: 'room-one',
      breakout_room_name: 'Room one',
      livekit_room_name: 'breakout_one',
    },
  },
}))
vi.mock('@livekit/components-react', () => ({
  useRoomInfo: () => ({ metadata: mocks.metadata }),
}))
vi.mock('../api/useCurrentBreakoutAssignment', () => ({
  useCurrentBreakoutAssignment: () => ({
    data: mocks.assignment,
    dataUpdatedAt: mocks.updatedAt,
    refetch: mocks.refetch,
  }),
}))
vi.mock('./useBreakoutRoomSwap', () => ({
  useBreakoutRoomSwap: () => ({
    moveToBreakoutRoom: mocks.move,
    returnToMainRoom: mocks.returnToMain,
    returnToMainRoomAfterClose: mocks.returnAfterClose,
  }),
}))
const params = {
  currentRoomSlug: 'main',
  mainRoomId: 'main-id',
  setActiveRoomConnection: vi.fn(),
}
beforeEach(() => {
  clearBreakoutState()
  vi.clearAllMocks()
  mocks.metadata = JSON.stringify({
    breakout: { session_id: 'one', revision: 3 },
  })
  mocks.updatedAt = 1
  mocks.assignment.session_id = 'one'
  mocks.assignment.revision = 3
})
afterEach(cleanup)

it('retries a token whose media connection failed on the next poll', async () => {
  mocks.move.mockImplementation(async () => {
    breakoutStore.isTransitioning = true
  })
  const { rerender } = renderHook(() => useBreakoutMetadataWatcher(params))
  await act(async () => {})
  expect(mocks.move).toHaveBeenCalledTimes(1)
  await act(async () => {
    failBreakoutConnection(new Error('connect rejected'))
  })
  mocks.updatedAt = 2
  rerender()
  await act(async () => {})
  expect(mocks.move).toHaveBeenCalledTimes(2)
})

it('resets revision and deliberate-return state when a new session replaces the old one', async () => {
  breakoutStore.activeSessionId = 'old'
  breakoutStore.revisionHint = 12
  breakoutStore.pausedAssignmentRevision = 3
  mocks.metadata = JSON.stringify({
    breakout: { session_id: 'one', revision: 3 },
  })
  renderHook(() => useBreakoutMetadataWatcher(params))
  await act(async () => {})
  expect(breakoutStore.revisionHint).toBe(3)
  expect(breakoutStore.pausedAssignmentRevision).toBeNull()
  expect(mocks.move).toHaveBeenCalledTimes(1)
})
