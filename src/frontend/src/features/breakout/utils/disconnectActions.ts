import { DisconnectReason } from 'livekit-client'
import type { BreakoutCurrentAssignment } from '../api/types'

export type DisconnectAction =
  | 'ignore'
  | 'verify-assignment'
  | 'recover-session'
  | 'leave'

interface DisconnectInput {
  reason?: DisconnectReason
  isTransitioning: boolean
  activeSessionId: string | null
  currentBreakoutRoomLkName: string | null
}

/**
 * What a LiveKit disconnect means while a breakout session may be active.
 *
 * Reconnect exhaustion and refused joins arrive with no reason at all, so
 * inside a breakout room every disconnect that is not a deliberate leave or
 * a duplicate identity is treated as recoverable.
 */
export const resolveDisconnectAction = (
  input: DisconnectInput
): DisconnectAction => {
  if (input.isTransitioning) return 'ignore'
  if (!input.activeSessionId) return 'leave'
  if (input.reason === DisconnectReason.PARTICIPANT_REMOVED) {
    return 'verify-assignment'
  }
  if (
    input.currentBreakoutRoomLkName &&
    input.reason !== DisconnectReason.CLIENT_INITIATED &&
    input.reason !== DisconnectReason.DUPLICATE_IDENTITY
  ) {
    return 'recover-session'
  }
  return 'leave'
}

/**
 * A removal is part of a reassignment only if we were in a breakout room and
 * the server now wants us somewhere else. Removal from the main room is the
 * host's moderation control, never a breakout move.
 */
export const isRemovalAReassignment = (
  previousRoomLkName: string | null,
  fresh: BreakoutCurrentAssignment
): boolean => {
  if (previousRoomLkName === null) return false
  if (fresh.status === 'closing' || fresh.status === 'closed') return true
  if (fresh.status !== 'active') return false
  const target = fresh.assignment?.livekit_room_name ?? null
  return target !== previousRoomLkName
}
