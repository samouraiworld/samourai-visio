import { describe, expect, it, vi } from 'vitest'
import {
  acknowledgeConnectedHelp,
  type PendingHelpAcknowledgement,
} from './helpAcknowledgement'

const pending: PendingHelpAcknowledgement = {
  roomId: 'main-room',
  sessionId: 'session-1',
  helpRequestId: 'help-1',
  expectedBreakoutRoomId: 'breakout-1',
  expectedLivekitRoomName: 'breakout-livekit-1',
  assignmentRevision: 7,
}

describe('acknowledgeConnectedHelp', () => {
  it('acknowledges the exact connected room and assignment revision', async () => {
    const acknowledge = vi.fn().mockResolvedValue(undefined)
    const invalidate = vi.fn().mockResolvedValue(undefined)

    const acknowledged = await acknowledgeConnectedHelp({
      pending,
      connectedRoomName: pending.expectedLivekitRoomName,
      acknowledge,
      invalidate,
    })

    expect(acknowledged).toBe(true)
    expect(acknowledge).toHaveBeenCalledWith({
      roomId: pending.roomId,
      sessionId: pending.sessionId,
      helpRequestId: pending.helpRequestId,
      expectedBreakoutRoomId: pending.expectedBreakoutRoomId,
      expectedAssignmentRevision: pending.assignmentRevision,
    })
    expect(invalidate).toHaveBeenCalledWith(pending.roomId, pending.sessionId)
  })

  it('does not acknowledge after connecting to a different room', async () => {
    const acknowledge = vi.fn().mockResolvedValue(undefined)
    const invalidate = vi.fn().mockResolvedValue(undefined)

    const acknowledged = await acknowledgeConnectedHelp({
      pending,
      connectedRoomName: 'another-room',
      acknowledge,
      invalidate,
    })

    expect(acknowledged).toBe(false)
    expect(acknowledge).not.toHaveBeenCalled()
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('keeps the durable alert open when the acknowledgement is stale', async () => {
    const acknowledge = vi.fn().mockRejectedValue(new Error('HTTP 409'))
    const invalidate = vi.fn().mockResolvedValue(undefined)

    const acknowledged = await acknowledgeConnectedHelp({
      pending,
      connectedRoomName: pending.expectedLivekitRoomName,
      acknowledge,
      invalidate,
    })

    expect(acknowledged).toBe(false)
    expect(invalidate).not.toHaveBeenCalled()
  })
})
