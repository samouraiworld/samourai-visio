// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/api/queryClient'
import { ApiError } from '@/api/ApiError'
import { BreakoutPanel } from './BreakoutPanel'
import { closeBreakoutSession, fetchBreakoutSession } from '../api'

const h = vi.hoisted(() => ({ metadata: '' }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('@livekit/components-react', () => ({
  useRoomInfo: () => ({ metadata: h.metadata }),
  useParticipants: () => [],
}))
vi.mock('@/features/rooms/livekit/hooks/useRoomData', () => ({
  useRoomData: () => ({ id: 'room-1' }),
}))
vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  fetchBreakoutSession: vi.fn(),
  closeBreakoutSession: vi.fn(async () => ({})),
}))

const announce = (sessionId: string | null) => {
  h.metadata = sessionId
    ? JSON.stringify({ breakout: { session_id: sessionId } })
    : ''
}

const ui = () => (
  <QueryClientProvider client={queryClient}>
    <BreakoutPanel />
  </QueryClientProvider>
)

const session = {
  id: 's1',
  status: 'active' as const,
  rooms: [{ id: 'r1', name: 'Room 1', participants: [] }],
}

afterEach(() => {
  cleanup()
  queryClient.clear()
  vi.mocked(fetchBreakoutSession).mockReset()
})

describe('BreakoutPanel', () => {
  it('keeps the last session on screen while the next one loads', async () => {
    announce('s1')
    vi.mocked(fetchBreakoutSession).mockResolvedValueOnce(session)
    const { rerender } = render(ui())
    await screen.findByRole('button', { name: 'active.close' })

    vi.mocked(fetchBreakoutSession).mockReturnValueOnce(new Promise(() => {}))
    announce(null)
    rerender(ui())
    expect(
      screen.queryByRole('button', { name: 'active.close' })
    ).not.toBeNull()
  })

  it('offers no Open form once a leftover session is closed with the flag off', async () => {
    vi.mocked(fetchBreakoutSession).mockRejectedValue(
      new ApiError(404, { detail: 'Not found.' })
    )
    announce('s1')
    const { rerender } = render(ui())
    fireEvent.click(await screen.findByRole('button', { name: 'active.close' }))
    await waitFor(() =>
      expect(closeBreakoutSession).toHaveBeenCalledWith('room-1', 's1')
    )

    announce(null)
    rerender(ui())
    await waitFor(() =>
      expect(
        queryClient.getQueryState(['breakoutSession', 'room-1', null])?.status
      ).toBe('error')
    )
    expect(screen.queryByRole('button', { name: 'setup.open' })).toBeNull()
  })
})
