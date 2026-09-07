import type { BreakoutCurrentAssignment } from '../api/types'

export interface AssignmentInput {
  status: BreakoutCurrentAssignment['status']
  revision: number
  assignment: BreakoutCurrentAssignment['assignment']
  /** The timed session's ends_at has passed; the server close is imminent. */
  isExpired: boolean
  isTransitioning: boolean
  isModeratorVisiting: boolean
  currentBreakoutRoomLkName: string | null
  connectionLost: boolean
  pausedAssignmentRevision: number | null
  lastTransitionRevision: number | null
}

export type AssignmentAction =
  | { type: 'none' }
  | { type: 'clear' }
  | { type: 'return-after-close' }
  | { type: 'return-to-main' }
  | {
      type: 'move'
      breakoutRoomId: string
      breakoutRoomName: string
      revision: number
    }

/** Decide what the polled assignment means for this participant right now. */
export const resolveAssignmentAction = (
  input: AssignmentInput
): AssignmentAction => {
  if (input.isTransitioning) return { type: 'none' }

  if (input.status === 'closing' || input.status === 'closed') {
    return input.currentBreakoutRoomLkName
      ? { type: 'return-after-close' }
      : { type: 'clear' }
  }

  if (input.status !== 'active' || input.isModeratorVisiting) {
    return { type: 'none' }
  }

  // A join after ends_at is refused by the server and the webhook would evict
  // anyone let in by a cached token: wait for the scheduled close instead.
  if (input.isExpired) return { type: 'none' }

  const { assignment } = input
  if (!assignment) {
    return input.currentBreakoutRoomLkName
      ? { type: 'return-to-main' }
      : { type: 'none' }
  }

  const isAlreadyThere =
    input.currentBreakoutRoomLkName === assignment.livekit_room_name &&
    !input.connectionLost
  const isPausedHere =
    !input.currentBreakoutRoomLkName &&
    input.pausedAssignmentRevision === input.revision
  const alreadyTransitioned =
    input.lastTransitionRevision === input.revision && !input.connectionLost

  if (isAlreadyThere || isPausedHere || alreadyTransitioned) {
    return { type: 'none' }
  }

  return {
    type: 'move',
    breakoutRoomId: assignment.breakout_room_id,
    breakoutRoomName: assignment.breakout_room_name,
    revision: input.revision,
  }
}
