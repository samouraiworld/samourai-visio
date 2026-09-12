/**
 * Breakout Rooms side panel — moderator-only.
 *
 * Three states:
 * - No session → BreakoutSetup (create)
 * - Session CONFIGURING → BreakoutSetup (assign + open)
 * - Session ACTIVE → BreakoutActiveView (monitor + close)
 */

import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import { useBreakoutSession } from '../api/useBreakoutSession'
import { BreakoutSetup } from './BreakoutSetup'
import { BreakoutActiveView } from './BreakoutActiveView'

export const BreakoutPanel = () => {
  const roomData = useRoomData()
  // API is the sole source of truth and survives moderator reloads.
  const { data: remoteSession } = useBreakoutSession(roomData?.id)
  const session = remoteSession ?? null

  const roomUuid = roomData?.id ?? ''

  if (!roomData) return null

  // Active session → monitoring view
  if (session?.status === 'active' || session?.status === 'closing') {
    return <BreakoutActiveView roomUuid={roomUuid} session={session} />
  }

  // Configuring or no session → setup view
  return (
    <BreakoutSetup
      roomUuid={roomUuid}
      session={
        session?.status === 'configuring' || session?.status === 'activating'
          ? session
          : null
      }
    />
  )
}
