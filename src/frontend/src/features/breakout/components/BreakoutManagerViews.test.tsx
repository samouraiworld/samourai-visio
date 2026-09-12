// @vitest-environment jsdom
import type { ReactNode } from 'react'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/ApiError'
import type { BreakoutSession } from '../api/types'
import { BreakoutSetup } from './BreakoutSetup'
import { BreakoutActiveView } from './BreakoutActiveView'

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  invalidate: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('@/api/queryClient', () => ({
  queryClient: { invalidateQueries: mocks.invalidate },
}))
vi.mock('@/primitives', () => ({
  Button: ({
    children,
    onPress,
    isDisabled,
    ...props
  }: {
    children: ReactNode
    onPress?: () => void
    isDisabled?: boolean
    'aria-label'?: string
  }) => (
    <button
      aria-label={props['aria-label']}
      onClick={onPress}
      disabled={isDisabled}
    >
      {children}
    </button>
  ),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('@/api/useConfig', () => ({
  useConfig: () => ({ data: { breakout_rooms: { is_enabled: true } } }),
}))
vi.mock('@livekit/components-react', () => ({
  useParticipants: () => [
    { identity: 'alice', name: 'Alice', attributes: {}, isLocal: false },
  ],
}))
vi.mock('../api/useCreateBreakoutSession', () => ({
  useCreateBreakoutSession: () => ({ mutateAsync: mocks.mutate }),
}))
vi.mock('../api/useRandomizeAssignments', () => ({
  useRandomizeAssignments: () => ({ mutateAsync: mocks.mutate }),
}))
vi.mock('../api/useAssignParticipants', () => ({
  useAssignParticipants: () => ({ mutateAsync: mocks.mutate }),
}))
vi.mock('../api/useUpdateBreakoutSession', () => ({
  useUpdateBreakoutSession: () => ({ mutateAsync: mocks.mutate }),
}))
vi.mock('../api/useRetryBreakoutSession', () => ({
  useRetryBreakoutSession: () => ({ mutateAsync: mocks.mutate }),
}))
vi.mock('../api/useBroadcastMessage', () => ({
  useBroadcastMessage: () => ({ mutateAsync: mocks.mutate }),
}))
vi.mock('../api/useBreakoutStatus', () => ({
  useBreakoutStatus: () => ({
    data: {
      main_room: { participants: [{ identity: 'alice', name: 'Alice' }] },
      rooms: [],
    },
  }),
}))
vi.mock('../hooks/useBreakoutRoomSwap', () => ({
  useBreakoutRoomSwap: () => ({}),
}))

const session: BreakoutSession = {
  id: 'session',
  status: 'configuring',
  revision: 3,
  duration_seconds: null,
  started_at: null,
  ends_at: null,
  closed_at: null,
  effect_error: '',
  created_at: '',
  breakout_rooms: [
    {
      id: 'one',
      name: 'Room one',
      livekit_room_name: 'breakout_one',
      order: 0,
      assignments: [],
    },
  ],
}
beforeEach(() => {
  vi.clearAllMocks()
  mocks.mutate.mockRejectedValue(new ApiError(409, {}))
})
afterEach(cleanup)

it('shows a setup conflict and refreshes the authoritative session', async () => {
  const { rerender } = render(
    <BreakoutSetup roomUuid="main" session={session} />
  )
  fireEvent.click(screen.getByText('randomize'))
  await waitFor(() =>
    expect(screen.getByRole('alert').textContent).toBe('actionFailed.conflict')
  )
  expect(mocks.invalidate).toHaveBeenCalledWith({
    queryKey: ['breakout-session', 'main'],
  })
  rerender(
    <BreakoutSetup roomUuid="main" session={{ ...session, revision: 4 }} />
  )
  expect(screen.getByRole('alert').textContent).toBe('actionFailed.conflict')
})

it('shows a retry refusal while cleanup is still closing', async () => {
  render(
    <BreakoutActiveView
      roomUuid="main"
      session={{ ...session, status: 'closing', effect_error: 'unavailable' }}
    />
  )
  fireEvent.click(screen.getByText('retrySynchronization'))
  await waitFor(() =>
    expect(screen.getByText('actionFailed.conflict')).toBeTruthy()
  )
})

it('resets the main-room assignment action so the same destination can be retried', async () => {
  render(
    <BreakoutActiveView
      roomUuid="main"
      session={{ ...session, status: 'active' }}
    />
  )
  const selector = screen.getByRole('combobox', {
    name: 'reassignParticipant',
  }) as HTMLSelectElement
  fireEvent.change(selector, { target: { value: 'one' } })
  await waitFor(() =>
    expect(screen.getByText('actionFailed.conflict')).toBeTruthy()
  )
  expect(selector.value).toBe('')
  fireEvent.change(selector, { target: { value: 'one' } })
  await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(2))
})
