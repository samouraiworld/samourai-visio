/**
 * Moving between the meeting and a breakout room is a real reconnection.
 *
 * `Room.connect()` returns immediately when the room object is already
 * connected — it logs `already connected to room <name>` and resolves without
 * ever looking at the token it was handed. Handing a breakout token to the
 * meeting's own `Room`, by remounting `<LiveKitRoom>` with a new key, therefore
 * resolves as a success while leaving the participant in the meeting they
 * started in: the overlay names the breakout room, the roster does not move.
 *
 * `<LiveKitRoom>` does disconnect on unmount, but fire-and-forget, so it races
 * the connect the remount starts. Leaving the current room *first*, and
 * awaiting it, is what removes the race.
 */

/** The part of livekit-client's `Room` this module needs. */
export interface LeavableRoom {
  /** livekit-client's `ConnectionState`; `'disconnected'` when not in a room. */
  state: string
  disconnect: () => Promise<void>
}

export const DISCONNECTED = 'disconnected'

/**
 * Leave the room the participant is currently in, if any, and wait for it.
 *
 * Returns whether a disconnect was actually performed, so a caller can tell
 * "left the meeting" from "was not in one".
 */
export const leaveCurrentRoom = async (
  room?: LeavableRoom | null
): Promise<boolean> => {
  if (!room || room.state === DISCONNECTED) return false
  await room.disconnect()
  return true
}

/**
 * Hand a participant over to a new connection.
 *
 * The order is the whole point: the meeting has to be left, and the leave has
 * to have completed, before `apply` publishes the new token to
 * `<LiveKitRoom>`. Applying first — or not waiting — hands the token to a room
 * object that is still connected, which drops it.
 */
export const swapRoomConnection = async <T>(
  room: LeavableRoom | null | undefined,
  connection: T,
  apply: (connection: T) => void
): Promise<void> => {
  await leaveCurrentRoom(room)
  apply(connection)
}
