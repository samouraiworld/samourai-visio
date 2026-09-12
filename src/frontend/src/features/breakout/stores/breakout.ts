/**
 * Valtio store for breakout room state.
 *
 * Critical state is persisted to sessionStorage so participants
 * can recover their breakout room assignment on page refresh.
 */

import { proxy, subscribe } from 'valtio'
import { STORAGE_KEYS } from '../utils/constants'
import type { PendingHelpAcknowledgement } from '../utils/helpAcknowledgement'

interface PersistedBreakoutState {
  activeSessionId: string | null
  currentBreakoutRoomLkName: string | null
  mainRoomSlug: string | null
  mainRoomId: string | null
  assignedRoomId: string | null
  pausedAssignmentRevision: number | null
  lastBroadcastShownAt: string | null
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
  /** Bumped whenever a hint says the assignment poll must run now. */
  assignmentRefreshNonce: number
  /** The room we belonged to dropped us outside a planned transition. */
  connectionLost: boolean
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
        lastBroadcastShownAt: null,
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
    lastBroadcastShownAt: null,
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
  assignmentRefreshNonce: 0,
  activeSessionId: restored.activeSessionId,
  currentBreakoutRoomLkName: restored.currentBreakoutRoomLkName,
  mainRoomSlug: restored.mainRoomSlug,
  mainRoomId: restored.mainRoomId,
  assignedRoomId: restored.assignedRoomId,
  pausedAssignmentRevision: restored.pausedAssignmentRevision,
  lastBroadcastShownAt: restored.lastBroadcastShownAt,
  connectionLost: false,
})

/** Persist the critical fields to sessionStorage. */
const persistBreakoutState = () => {
  const {
    activeSessionId,
    currentBreakoutRoomLkName,
    mainRoomSlug,
    mainRoomId,
    assignedRoomId,
    pausedAssignmentRevision,
    lastBroadcastShownAt,
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
        lastBroadcastShownAt,
      })
    )
  } catch {
    // sessionStorage full or unavailable: best effort
  }
}

subscribe(breakoutStore, persistBreakoutState)

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
  breakoutStore.assignmentRefreshNonce = 0
  breakoutStore.activeSessionId = null
  breakoutStore.currentBreakoutRoomLkName = null
  breakoutStore.mainRoomSlug = null
  breakoutStore.mainRoomId = null
  breakoutStore.assignedRoomId = null
  breakoutStore.pausedAssignmentRevision = null
  breakoutStore.lastBroadcastShownAt = null
  breakoutStore.connectionLost = false
  try {
    sessionStorage.removeItem(STORAGE_KEYS.BREAKOUT_STATE)
  } catch {
    // Storage may be unavailable; in-memory cleanup still completes.
  }
}

/**
 * Reset session-scoped state but keep what belongs to the page: the binding
 * to the current meeting and the announcement already shown.
 */
export const clearBreakoutSession = (): void => {
  const { mainRoomId, mainRoomSlug, lastBroadcastShownAt } = breakoutStore
  clearBreakoutState()
  breakoutStore.mainRoomId = mainRoomId
  breakoutStore.mainRoomSlug = mainRoomSlug
  breakoutStore.lastBroadcastShownAt = lastBroadcastShownAt
}

/**
 * The lobby no longer holds our admission: forget the session but keep the
 * deliberate-return intent, and tell the lobby page why it is shown.
 */
export const prepareLobbyReentry = (): void => {
  const { activeSessionId, pausedAssignmentRevision } = breakoutStore
  clearBreakoutSession()
  breakoutStore.activeSessionId = activeSessionId
  breakoutStore.pausedAssignmentRevision = pausedAssignmentRevision
  // Write now: the caller reloads before valtio's subscriber microtask runs.
  persistBreakoutState()
  try {
    sessionStorage.setItem(STORAGE_KEYS.BREAKOUT_REENTRY, '1')
  } catch {
    // Best effort: the lobby simply shows no explanation.
  }
}

/** Revisions and deliberate returns belong to one session, not the meeting. */
export const bindBreakoutSession = (sessionId: string): void => {
  if (breakoutStore.activeSessionId === sessionId) return
  breakoutStore.activeSessionId = sessionId
  breakoutStore.revisionHint = 0
  breakoutStore.pausedAssignmentRevision = null
  breakoutStore.assignedRoomId = null
  breakoutStore.lastBroadcastShownAt = null
  breakoutStore.broadcastAnnouncement = null
  breakoutStore.pendingHelpAcknowledgement = null
}

/** Ask the metadata watcher to re-read the caller's assignment from the server. */
export const requestAssignmentRefresh = (): void => {
  breakoutStore.assignmentRefreshNonce += 1
}

export const completeBreakoutTransition = (): void => {
  if (breakoutStore.clearAfterTransition) {
    const transitionError = breakoutStore.transitionError
    clearBreakoutSession()
    breakoutStore.transitionError = transitionError
    return
  }
  breakoutStore.pendingMediaIntent = null
  breakoutStore.isTransitioning = false
  breakoutStore.transitionTargetName = null
}

/** Record connection failure separately from token-request failure. */
export const failBreakoutConnection = (error: Error): void => {
  breakoutStore.pendingHelpAcknowledgement = null
  if (breakoutStore.isTransitioning) {
    breakoutStore.isTransitioning = false
    // A later SignalConnected event must not reuse initial device preferences.
    // Keep both intent and recall completion until the target actually connects.
    breakoutStore.transitionError = error.message
  }
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
