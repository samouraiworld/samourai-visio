import { proxy } from 'valtio'
import type { MediaIntent } from './utils/mediaIntent'

type BreakoutRoomRef = { id: string; name: string }

type BreakoutState = {
  // The breakout room this browser is in, null in the main meeting.
  room: BreakoutRoomRef | null
  // Where a move in progress goes, for the overlay.
  target: BreakoutRoomRef | 'main' | null
  // True while this browser disconnects on purpose.
  leaving: boolean
  // The session whose assignment was fetched, so each is fetched once.
  sessionId: string | null
  // The last move failed; cleared by the next attempt or when the session ends.
  moveFailed: boolean
  // Camera and microphone as last seen while connected.
  media: MediaIntent | null
  // Restored once the next connection is up.
  pendingMedia: MediaIntent | null
}

const initialState = (): BreakoutState => ({
  room: null,
  target: null,
  leaving: false,
  sessionId: null,
  moveFailed: false,
  media: null,
  pendingMedia: null,
})

// In memory only: a reload rejoins the main meeting, whose metadata moves it again.
export const breakoutStore = proxy<BreakoutState>(initialState())

export const resetBreakout = () => {
  Object.assign(breakoutStore, initialState())
}
