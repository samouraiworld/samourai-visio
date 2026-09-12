// @vitest-environment jsdom
import type { ComponentProps, ReactNode } from 'react'
import { useEffect } from 'react'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { LiveKitRoom } from '@livekit/components-react'
import {
  breakoutStore,
  clearBreakoutState,
  triggerRoomSwap,
} from '@/features/breakout/stores/breakout'
import { Conference } from './Conference'

const mocks = vi.hoisted(() => ({
  props: null as ComponentProps<typeof LiveKitRoom> | null,
  config: { livekit: { url: 'wss://example.test' } },
  data: { id: 'main', livekit: { room: 'main', token: 'initial' } },
  choices: { audioEnabled: false, videoEnabled: false },
  navigate: vi.fn(),
  connect: vi.fn(),
}))
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ status: 'success', data: mocks.data }),
}))
vi.mock('@/api/queryClient', () => ({ queryClient: { setQueryData: vi.fn() } }))
vi.mock('@/api/useConfig', () => ({
  useConfig: () => ({ data: mocks.config }),
}))
vi.mock('../api/createRoom', () => ({
  useCreateRoom: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock('@livekit/components-react', () => ({
  LiveKitRoom: (props: ComponentProps<typeof LiveKitRoom>) => {
    mocks.props = props
    const connectOptions = JSON.stringify(props.connectOptions)
    // Mirror the SDK's connection effect: onError is a connection dependency.
    // An inline callback would reconnect the previous room on store updates.
    useEffect(() => {
      if (props.connect) mocks.connect(props.room, props.token)
    }, [
      props.connect,
      props.token,
      connectOptions,
      props.room,
      props.onError,
      props.serverUrl,
    ])
    return <div />
  },
  usePersistentUserChoices: () => ({ userChoices: mocks.choices }),
}))
vi.mock('livekit-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('livekit-client')>()
  return {
    ...original,
    Room: class {
      name = 'main'
      state = 'disconnected'
      localParticipant = {
        setCameraEnabled: vi.fn(),
        setMicrophoneEnabled: vi.fn(),
      }
      prepareConnection = vi.fn().mockResolvedValue(undefined)
    },
  }
})
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('@/features/analytics/telemetry', () => ({
  captureMediaEvent: vi.fn(),
  captureEvent: vi.fn(),
  reportError: vi.fn(),
}))
vi.mock('@/layout/Screen', () => ({
  Screen: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock('@/components/QueryAware', () => ({
  QueryAware: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
vi.mock('../livekit/prefabs/VideoConference', () => ({
  VideoConference: () => null,
}))
vi.mock('./InviteDialog', () => ({ InviteDialog: () => null }))
vi.mock('@/features/pip/components/PictureInPictureConference', () => ({
  PictureInPictureConference: () => null,
}))
vi.mock('@/features/devtools', () => ({ MeetDevtools: () => null }))
vi.mock('./WatchMediaDeviceErrors', () => ({
  WatchMediaDeviceErrors: () => null,
}))
vi.mock('../livekit/components/blur', () => ({
  BackgroundProcessorFactory: {},
}))
vi.mock('@/utils/useIsMobile', () => ({ useIsMobile: () => false }))
vi.mock('@/navigation/navigateTo', () => ({ navigateTo: mocks.navigate }))
vi.mock('@/features/notifications/utils', () => ({
  notifyAutoMutedOnJoin: vi.fn(),
}))
vi.mock('@/features/rooms/livekit/utils/mediaPermissions', () => ({
  getMediaDeviceFailure: () => undefined,
}))

beforeEach(() => {
  clearBreakoutState()
  vi.clearAllMocks()
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

it('uses a fresh transport for every attempt even when retry tokens are identical', async () => {
  render(<Conference roomId="main" />)
  await waitFor(() => expect(mocks.props?.connect).toBe(true))
  const initialRoom = mocks.props?.room
  mocks.connect.mockClear()
  act(() =>
    triggerRoomSwap({ roomName: 'breakout_one', token: 'breakout-token' })
  )
  const breakoutRoom = mocks.props?.room
  expect(breakoutRoom).not.toBe(initialRoom)
  expect(mocks.connect).toHaveBeenCalledTimes(1)
  expect(mocks.connect).toHaveBeenLastCalledWith(breakoutRoom, 'breakout-token')
  // Tokens minted within the same second can be byte-for-byte identical.
  act(() =>
    triggerRoomSwap({ roomName: 'breakout_one', token: 'breakout-token' })
  )
  expect(mocks.props?.room).not.toBe(breakoutRoom)
  expect(mocks.connect).toHaveBeenCalledTimes(2)
  expect(mocks.connect).toHaveBeenLastCalledWith(
    mocks.props?.room,
    'breakout-token'
  )
})

it('starts bounded recovery when the requested media connection fails', async () => {
  render(<Conference roomId="main" />)
  await waitFor(() => expect(mocks.props?.connect).toBe(true))
  vi.useFakeTimers()
  act(() => {
    breakoutStore.isTransitioning = true
    breakoutStore.activeSessionId = 'session'
    mocks.props?.onError?.(new Error('connection refused'))
  })
  expect(breakoutStore.connectionLost).toBe(true)
  act(() => vi.advanceTimersByTime(15000))
  expect(mocks.navigate).toHaveBeenCalledTimes(1)
})

it('does not reconnect a removed room while breakout state prepares its replacement', async () => {
  render(<Conference roomId="main" />)
  await waitFor(() => expect(mocks.props?.connect).toBe(true))
  const previousRoom = mocks.props?.room
  const previousErrorHandler = mocks.props?.onError
  mocks.connect.mockClear()

  // LiveKit has removed this connection during reassignment; the watcher
  // updates the store before the next token request has completed.
  await act(async () => {
    breakoutStore.activeSessionId = 'session'
    breakoutStore.connectionLost = true
    breakoutStore.isTransitioning = true
    breakoutStore.pendingMediaIntent = { camera: false, microphone: false }
  })
  expect(mocks.connect).not.toHaveBeenCalled()
  expect(mocks.props?.onError).toBe(previousErrorHandler)

  act(() => triggerRoomSwap({ roomName: 'breakout_one', token: 'next-token' }))
  expect(mocks.connect).toHaveBeenCalledTimes(1)
  expect(mocks.connect).toHaveBeenCalledWith(mocks.props?.room, 'next-token')
  expect(mocks.props?.room).not.toBe(previousRoom)
})
