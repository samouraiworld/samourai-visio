// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { breakoutStore, clearBreakoutState } from '../stores/breakout'
import { useBreakoutRoomSwap } from './useBreakoutRoomSwap'

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  entry: vi.fn(),
  room: {
    name: 'main',
    state: 'connected',
    disconnect: vi.fn<() => Promise<void>>(),
  },
  participant: { isCameraEnabled: false, isMicrophoneEnabled: true },
}))
vi.mock('@livekit/components-react', () => ({
  useLocalParticipant: () => ({ localParticipant: mocks.participant }),
  useRoomContext: () => mocks.room,
}))
vi.mock('@/api/fetchApi', () => ({ fetchApi: mocks.fetch }))
vi.mock('@/features/rooms/api/requestEntry', () => ({
  requestEntry: mocks.entry,
}))
vi.mock('@/stores/user', async () => {
  const { proxy } = await import('valtio')
  return { userStore: proxy({ username: 'Alice' }) }
})

beforeEach(() => {
  clearBreakoutState()
  vi.clearAllMocks()
  mocks.room.name = 'main'
  mocks.room.state = 'connected'
  mocks.fetch.mockResolvedValue({
    livekit: { token: 'new-token', room: 'breakout_one' },
  })
  mocks.room.disconnect.mockResolvedValue()
})
afterEach(cleanup)

it('waits for the real disconnect before handing the token to the conference', async () => {
  let finishDisconnect!: () => void
  mocks.room.disconnect.mockImplementation(
    () =>
      new Promise<void>((resolve) => {
        finishDisconnect = resolve
      })
  )
  const apply = vi.fn()
  const { result } = renderHook(() =>
    useBreakoutRoomSwap({
      currentRoomSlug: 'main',
      setActiveRoomConnection: apply,
    })
  )
  let moving!: Promise<string>
  await act(async () => {
    moving = result.current.moveToBreakoutRoom('room', 'session', 'main-id')
  })
  expect(apply).not.toHaveBeenCalled()
  expect(breakoutStore.pendingMediaIntent).toEqual({
    camera: false,
    microphone: true,
  })
  await act(async () => {
    finishDisconnect()
    await moving
  })
  expect(apply).toHaveBeenCalledWith({
    token: 'new-token',
    roomName: 'breakout_one',
  })
})

it('keeps the current meeting connected when a token request is refused', async () => {
  mocks.fetch.mockRejectedValue(new Error('unavailable'))
  const { result } = renderHook(() => useBreakoutRoomSwap())
  await act(async () => {
    await expect(
      result.current.moveToBreakoutRoom('room', 'session', 'main-id')
    ).rejects.toThrow('unavailable')
  })
  expect(mocks.room.disconnect).not.toHaveBeenCalled()
  expect(breakoutStore.isTransitioning).toBe(false)
  expect(breakoutStore.transitionError).toBe('unavailable')
})

it('does not disconnect a host who is already in the requested help room', async () => {
  mocks.room.name = 'breakout_one'
  const apply = vi.fn()
  const { result } = renderHook(() =>
    useBreakoutRoomSwap({ setActiveRoomConnection: apply })
  )
  await act(async () => {
    await result.current.moveToBreakoutRoom(
      'room',
      'session',
      'main-id',
      'Room',
      true
    )
  })
  expect(mocks.room.disconnect).not.toHaveBeenCalled()
  expect(apply).not.toHaveBeenCalled()
  expect(breakoutStore.isTransitioning).toBe(false)
})

it('does not start a return while another transition owns the connection', async () => {
  breakoutStore.mainRoomSlug = 'main'
  breakoutStore.currentBreakoutRoomLkName = 'breakout_one'
  breakoutStore.isTransitioning = true
  const { result } = renderHook(() => useBreakoutRoomSwap())
  await act(async () => {
    await result.current.returnToMainRoom()
  })
  expect(mocks.entry).not.toHaveBeenCalled()
})

it('retains the original media intent when a disconnected retry cannot fetch a token', async () => {
  breakoutStore.pendingMediaIntent = { camera: true, microphone: true }
  mocks.room.state = 'disconnected'
  mocks.fetch.mockRejectedValue(new Error('unavailable'))
  const { result } = renderHook(() => useBreakoutRoomSwap())
  await act(async () => {
    await expect(
      result.current.moveToBreakoutRoom('room', 'session', 'main-id')
    ).rejects.toThrow()
  })
  expect(breakoutStore.pendingMediaIntent).toEqual({
    camera: true,
    microphone: true,
  })
})
