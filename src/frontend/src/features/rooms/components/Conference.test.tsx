// @vitest-environment jsdom
import type { ComponentProps, ReactNode } from 'react'
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

it('uses a fresh Room transport for every token, including same-room reconnects', async () => {
  render(<Conference roomId="main" />)
  await waitFor(() => expect(mocks.props?.connect).toBe(true))
  const initialRoom = mocks.props?.room
  act(() =>
    triggerRoomSwap({ roomName: 'breakout_one', token: 'breakout-token' })
  )
  const breakoutRoom = mocks.props?.room
  expect(breakoutRoom).not.toBe(initialRoom)
  act(() => triggerRoomSwap({ roomName: 'breakout_one', token: 'retry-token' }))
  expect(mocks.props?.room).not.toBe(breakoutRoom)
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
