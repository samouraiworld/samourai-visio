// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ParticipantKind } from 'livekit-client'
import { BreakoutSetup } from './BreakoutSetup'

const h = vi.hoisted(() => ({ participants: [] as unknown[] }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))
vi.mock('@livekit/components-react', () => ({
  useParticipants: () => h.participants,
}))

const guest = {
  identity: 'guest-1',
  name: 'Ann',
  isLocal: false,
  kind: ParticipantKind.STANDARD,
  attributes: { room_role: 'member' },
}

const renderSetup = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BreakoutSetup roomId="room-1" />
    </QueryClientProvider>
  )

afterEach(() => {
  cleanup()
  h.participants = []
})

describe('BreakoutSetup', () => {
  it('names the room-count selector for screen readers', () => {
    renderSetup()
    expect(
      screen.queryByRole('button', { name: /setup\.roomCount/ })
    ).not.toBeNull()
  })

  it('keeps Open disabled until someone is assigned', () => {
    h.participants = [guest]
    renderSetup()
    const open = screen.getByRole('button', { name: 'setup.open' })
    expect(open.hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'setup.shuffle' }))
    expect(open.hasAttribute('disabled')).toBe(false)
  })
})
