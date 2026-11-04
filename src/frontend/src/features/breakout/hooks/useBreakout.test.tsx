// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { BreakoutParticipant } from '../components/BreakoutParticipant'
import { fetchBreakoutAssignment } from '../api'
import { resetBreakout } from '../store'

const h = vi.hoisted(() => ({
  state: 'connected',
  room: { state: 'connected', disconnect: async () => {} },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('@livekit/components-react', () => ({
  useRoomContext: () => h.room,
  useRoomInfo: () => ({
    metadata: JSON.stringify({ breakout: { session_id: 's1' } }),
  }),
  useConnectionState: () => h.state,
  useLocalParticipant: () => ({
    isCameraEnabled: false,
    isMicrophoneEnabled: true,
  }),
}))
vi.mock('@/features/analytics/telemetry', () => ({ reportError: vi.fn() }))
vi.mock('@/features/rooms/api/requestEntry', () => ({ requestEntry: vi.fn() }))
vi.mock('../api', () => ({
  fetchBreakoutAssignment: vi
    .fn()
    .mockRejectedValueOnce(new Error('503 Service Unavailable'))
    .mockResolvedValue({ session_id: 's1', room: { id: 'r1', name: 'R1' } }),
  joinBreakoutRoom: vi.fn(async () => ({ token: 'breakout-token' })),
}))

const flush = () => act(async () => new Promise((r) => setTimeout(r, 0)))

afterEach(() => {
  cleanup()
  resetBreakout()
})

describe('a failed move to the assigned room', () => {
  it('is shown, then tried again once the main room reconnects', async () => {
    const connect = vi.fn()
    const ui = () => <BreakoutParticipant mainRoomId="main" connect={connect} />
    const { rerender } = render(ui())
    await flush()
    expect(screen.getByRole('status').textContent).toBe('moveFailed')

    h.state = 'reconnecting'
    rerender(ui())
    h.state = 'connected'
    rerender(ui())
    await flush()

    expect(vi.mocked(fetchBreakoutAssignment)).toHaveBeenCalledTimes(2)
    expect(connect).toHaveBeenCalledWith('breakout-token')
  })
})
