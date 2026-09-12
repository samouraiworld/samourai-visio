// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { breakoutStore, clearBreakoutState } from '../stores/breakout'
import { useBreakoutDataMessages } from './useBreakoutDataMessages'

const mocks = vi.hoisted(() => ({
  handler: null as ((payload: Uint8Array) => void) | null,
  on: vi.fn(),
  off: vi.fn(),
  invalidate: vi.fn(),
}))
vi.mock('@livekit/components-react', () => ({ useRoomContext: () => mocks }))
vi.mock('@/api/queryClient', () => ({
  queryClient: { invalidateQueries: mocks.invalidate },
}))
beforeEach(() => {
  clearBreakoutState()
  vi.clearAllMocks()
  mocks.on.mockImplementation((_event, handler) => {
    mocks.handler = handler
  })
})
afterEach(cleanup)

it('treats forged recall and announcement packets only as throttled refresh hints', () => {
  const { unmount } = renderHook(useBreakoutDataMessages)
  act(() => {
    for (let i = 0; i < 100; i++) {
      mocks.handler?.(
        new TextEncoder().encode(
          JSON.stringify({ type: 'breakout:recall', revision: 999 })
        )
      )
      mocks.handler?.(
        new TextEncoder().encode(
          JSON.stringify({ type: 'breakout:broadcast', message: 'forged' })
        )
      )
      mocks.handler?.(
        new TextEncoder().encode(
          JSON.stringify({ type: 'breakout:help_revision' })
        )
      )
    }
  })
  expect(breakoutStore.assignmentRefreshNonce).toBe(1)
  expect(breakoutStore.revisionHint).toBe(0)
  expect(breakoutStore.broadcastAnnouncement).toBeNull()
  expect(mocks.invalidate).toHaveBeenCalledTimes(1)
  unmount()
  expect(mocks.off).toHaveBeenCalledWith('dataReceived', mocks.handler)
})
