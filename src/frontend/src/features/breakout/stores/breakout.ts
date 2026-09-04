/**
 * Valtio store for breakout room state.
 *
 * Critical state is persisted to sessionStorage so participants
 * can recover their breakout room assignment on page refresh.
 */

import { proxy, subscribe } from 'valtio'
import { STORAGE_KEYS } from '../utils/constants'
import type { BreakoutLiveKitConnection } from '../api/types'
import type { PendingHelpAcknowledgement } from '../utils/helpAcknowledgement'

interface PersistedBreakoutState {
  activeSessionId: string | null
  currentBreakoutRoomLkName: string | null
  mainRoomSlug: string | null
  mainRoomId: string | null
  assignedRoomId: string | null
  pausedAssignmentRevision: number | null
}

interface BreakoutState extends PersistedBreakoutState {
  /** When true, `onDisconnected` should not navigate to the feedback page. */
  isTransitioning: boolean
  /** Human-readable target room name during transition. */
  transitionTargetName: string | null
  /** In-meeting announcement broadcast by host. */
  broadcastAnnouncement: { message: string; timestamp: number } | null
  /** Latest trusted server revision hint. */
  revisionHint: number
  /** Actual media publication intent captured before a room move. */
  pendingMediaIntent: { camera: boolean; microphone: boolean } | null
  /** Visible room-transition failure. */
  transitionError: string | null
  /** Manager visits never alter participant assignment semantics. */
  isModeratorVisiting: boolean
  /** Clear session state only after a close/recall return actually connects. */
  clearAfterTransition: boolean
  /** Help work is acknowledged only after the host reaches its room. */
  pendingHelpAcknowledgement: PendingHelpAcknowledgement | null
  /** Active LiveKit connection details for the breakout room. */
  activeConnection: BreakoutLiveKitConnection['livekit'] | null
}

/** Restore persisted state from sessionStorage. */
const restoreState = (): PersistedBreakoutState => {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEYS.BREAKOUT_STATE)
    if (stored) {
      return {
        activeSessionId: null,
        currentBreakoutRoomLkName: null,
        mainRoomSlug: null,
        mainRoomId: null,
        assignedRoomId: null,
        pausedAssignmentRevision: null,
        ...(JSON.parse(stored) as Partial<PersistedBreakoutState>),
      }
    }
  } catch {
    // Corrupted storage — ignore
  }
  return {
    activeSessionId: null,
    currentBreakoutRoomLkName: null,
    mainRoomSlug: null,
    mainRoomId: null,
    assignedRoomId: null,
    pausedAssignmentRevision: null,
  }
}

const restored = restoreState()

export const breakoutStore = proxy<BreakoutState>({
  isTransitioning: false,
  transitionTargetName: null,
  broadcastAnnouncement: null,
  revisionHint: 0,
  pendingMediaIntent: null,
  transitionError: null,
  isModeratorVisiting: false,
  clearAfterTransition: false,
  pendingHelpAcknowledgement: null,
  activeSessionId: restored.activeSessionId,
  currentBreakoutRoomLkName: restored.currentBreakoutRoomLkName,
  mainRoomSlug: restored.mainRoomSlug,
  mainRoomId: restored.mainRoomId,
  assignedRoomId: restored.assignedRoomId,
  pausedAssignmentRevision: restored.pausedAssignmentRevision,
  activeConnection: null,
})

// Persist critical fields to sessionStorage on change
subscribe(breakoutStore, () => {
  const {
    activeSessionId,
    currentBreakoutRoomLkName,
    mainRoomSlug,
    mainRoomId,
    assignedRoomId,
    pausedAssignmentRevision,
  } = breakoutStore

  try {
    sessionStorage.setItem(
      STORAGE_KEYS.BREAKOUT_STATE,
      JSON.stringify({
        activeSessionId,
        currentBreakoutRoomLkName,
        mainRoomSlug,
        mainRoomId,
        assignedRoomId,
        pausedAssignmentRevision,
      })
    )
  } catch {
    // sessionStorage full or unavailable — best effort
  }
})

/** Reset all breakout state (on session close or return to main). */
export const clearBreakoutState = (): void => {
  breakoutStore.isTransitioning = false
  breakoutStore.transitionTargetName = null
  breakoutStore.broadcastAnnouncement = null
  breakoutStore.revisionHint = 0
  breakoutStore.pendingMediaIntent = null
  breakoutStore.transitionError = null
  breakoutStore.isModeratorVisiting = false
  breakoutStore.clearAfterTransition = false
  breakoutStore.pendingHelpAcknowledgement = null
  breakoutStore.activeSessionId = null
  breakoutStore.currentBreakoutRoomLkName = null
  breakoutStore.mainRoomSlug = null
  breakoutStore.mainRoomId = null
  breakoutStore.assignedRoomId = null
  breakoutStore.pausedAssignmentRevision = null
  breakoutStore.activeConnection = null
  sessionStorage.removeItem(STORAGE_KEYS.BREAKOUT_STATE)
}

export const completeBreakoutTransition = (): void => {
  if (breakoutStore.clearAfterTransition) {
    const transitionError = breakoutStore.transitionError
    clearBreakoutState()
    breakoutStore.transitionError = transitionError
    return
  }
  breakoutStore.pendingMediaIntent = null
  breakoutStore.isTransitioning = false
  breakoutStore.transitionTargetName = null
}

/** Clear only the help target whose room connection has just completed. */
export const clearMatchingPendingHelpAcknowledgement = (
  completed: Readonly<PendingHelpAcknowledgement>
): boolean => {
  const current = breakoutStore.pendingHelpAcknowledgement
  if (
    !current ||
    current.helpRequestId !== completed.helpRequestId ||
    current.expectedLivekitRoomName !== completed.expectedLivekitRoomName ||
    current.assignmentRevision !== completed.assignmentRevision
  ) {
    return false
  }
  breakoutStore.pendingHelpAcknowledgement = null
  return true
}

/** Bind restored state to its parent meeting and discard cross-meeting residue. */
export const bindBreakoutToMainRoom = (
  mainRoomId: string,
  mainRoomSlug: string
): void => {
  if (breakoutStore.mainRoomId && breakoutStore.mainRoomId !== mainRoomId) {
    clearBreakoutState()
  }
  breakoutStore.mainRoomId = mainRoomId
  breakoutStore.mainRoomSlug = mainRoomSlug
}

type RoomConnection = { token: string; roomName: string }
type RoomSwapCallback = (conn: RoomConnection) => void

let globalRoomSwapHandler: RoomSwapCallback | null = null

export const registerRoomSwapHandler = (
  handler: RoomSwapCallback
): (() => void) => {
  globalRoomSwapHandler = handler
  return () => {
    if (globalRoomSwapHandler === handler) globalRoomSwapHandler = null
  }
}

export const triggerRoomSwap = (conn: RoomConnection): void => {
  if (globalRoomSwapHandler) {
    globalRoomSwapHandler(conn)
  } else {
    console.warn('triggerRoomSwap called but no handler registered')
  }
}
