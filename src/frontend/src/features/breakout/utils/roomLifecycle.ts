// Room.connect() on a room already connected resolves without reading its token,
// so a move leaves the current room, and waits for it, before the new pass is used.

// The part of livekit-client's `Room` this module needs.
export interface LeavableRoom {
  state: string
  disconnect: () => Promise<void>
}

export const DISCONNECTED = 'disconnected'

// Resolves to whether a disconnect was performed.
export const leaveCurrentRoom = async (
  room?: LeavableRoom | null
): Promise<boolean> => {
  if (!room || room.state === DISCONNECTED) return false
  await room.disconnect()
  return true
}

export const swapRoomConnection = async <T>(
  room: LeavableRoom | null | undefined,
  connection: T,
  apply: (connection: T) => void
): Promise<void> => {
  await leaveCurrentRoom(room)
  apply(connection)
}
