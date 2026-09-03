/**
 * Valtio store for breakout room state.
 *
 * Critical state is persisted to sessionStorage so participants
 * can recover their breakout room assignment on page refresh.
 */

import { proxy, subscribe } from 'valtio'
import { STORAGE_KEYS } from '../utils/constants'
import type { BreakoutSession, BreakoutLiveKitConnection } from '../api/types'

interface PersistedBreakoutState {
  activeSessionId: string | null
  currentBreakoutRoomLkName: string | null
  mainRoomSlug: string | null
  mainRoomId: string | null
  assignedRoomId: string | null
}

interface BreakoutState extends PersistedBreakoutState {
  /** When true, `onDisconnected` should not navigate to the feedback page. */
  isTransitioning: boolean
  /** Human-readable target room name during transition. */
  transitionTargetName: string | null
  /** In-meeting announcement broadcast by host. */
  broadcastAnnouncement: { message: string; timestamp: number } | null
  /** Assistance request received by host from a breakout room. */
  helpAlert: {
    roomName: string
    participantName: string
    breakoutRoomId: string
    sessionId: string
    timestamp: number
  } | null
  /** Timer countdown state. */
  timer: { remaining: number; total: number }
  /** The full session data (cached from last API fetch). */
  session: BreakoutSession | null
  /** Active LiveKit connection details for the breakout room. */
  activeConnection: BreakoutLiveKitConnection['livekit'] | null
}

/** Restore persisted state from sessionStorage. */
const restoreState = (): PersistedBreakoutState => {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEYS.BREAKOUT_STATE)
    if (stored) return JSON.parse(stored) as PersistedBreakoutState
  } catch {
    // Corrupted storage — ignore
  }
  return {
    activeSessionId: null,
    currentBreakoutRoomLkName: null,
    mainRoomSlug: null,
    mainRoomId: null,
    assignedRoomId: null,
  }
}

const restored = restoreState()

export const breakoutStore = proxy<BreakoutState>({
  isTransitioning: false,
  transitionTargetName: null,
  broadcastAnnouncement: null,
  helpAlert: null,
  activeSessionId: restored.activeSessionId,
  currentBreakoutRoomLkName: restored.currentBreakoutRoomLkName,
  mainRoomSlug: restored.mainRoomSlug,
  mainRoomId: restored.mainRoomId,
  assignedRoomId: restored.assignedRoomId,
  timer: { remaining: 0, total: 0 },
  session: null,
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
  breakoutStore.helpAlert = null
  breakoutStore.activeSessionId = null
  breakoutStore.currentBreakoutRoomLkName = null
  breakoutStore.mainRoomSlug = null
  breakoutStore.assignedRoomId = null
  breakoutStore.timer = { remaining: 0, total: 0 }
  breakoutStore.session = null
  breakoutStore.activeConnection = null
  sessionStorage.removeItem(STORAGE_KEYS.BREAKOUT_STATE)
}

type RoomConnection = { token: string; roomName: string }
type RoomSwapCallback = (conn: RoomConnection) => void

let globalRoomSwapHandler: RoomSwapCallback | null = null

export const registerRoomSwapHandler = (handler: RoomSwapCallback): void => {
  globalRoomSwapHandler = handler
}

export const triggerRoomSwap = (conn: RoomConnection): void => {
  if (globalRoomSwapHandler) {
    globalRoomSwapHandler(conn)
  } else {
    console.warn('triggerRoomSwap called but no handler registered')
  }
}
