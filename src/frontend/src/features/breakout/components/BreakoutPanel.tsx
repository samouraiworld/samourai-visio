/**
 * Breakout Rooms side panel — moderator-only.
 *
 * Three states:
 * - No session → BreakoutSetup (create)
 * - Session CONFIGURING → BreakoutSetup (assign + open)
 * - Session ACTIVE → BreakoutActiveView (monitor + close)
 */

import { useSnapshot } from 'valtio'
import { breakoutStore } from '../stores/breakout'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import { useBreakoutSession } from '../api/useBreakoutSession'
import { BreakoutSetup } from './BreakoutSetup'
import { BreakoutActiveView } from './BreakoutActiveView'
import type { BreakoutSession } from '../api/types'

export const BreakoutPanel = () => {
  const roomData = useRoomData()
  const snap = useSnapshot(breakoutStore)

  // API is the source of truth — survives host reload over a live session.
  const { data: remoteSession } = useBreakoutSession(roomData?.id)

  // breakoutStore.session provides optimistic state during the brief window
  // after creation before the first poll returns (10s interval).
  const session =
    remoteSession ?? (snap.session as BreakoutSession | null) ?? null

  const roomUuid = roomData?.id ?? ''

  if (!roomData) return null

  // Active session → monitoring view
  if (session?.status === 'active') {
    return <BreakoutActiveView roomUuid={roomUuid} />
  }

  // Configuring or no session → setup view
  return (
    <BreakoutSetup
      roomUuid={roomUuid}
      session={session?.status === 'configuring' ? session : null}
      onSessionCreated={(s) => {
        // Optimistic update: store the session so the panel transitions
        // immediately, before useBreakoutSession's next poll returns.
        breakoutStore.session = s
      }}
    />
  )
}
