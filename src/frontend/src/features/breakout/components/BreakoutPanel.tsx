/**
 * Breakout Rooms side panel — moderator-only.
 *
 * Three states:
 * - No session → BreakoutSetup (create)
 * - Session CONFIGURING → BreakoutSetup (assign + open)
 * - Session ACTIVE → BreakoutActiveView (monitor + close)
 */

import { useState } from 'react'
import { useSnapshot } from 'valtio'
import { breakoutStore } from '../stores/breakout'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import { BreakoutSetup } from './BreakoutSetup'
import { BreakoutActiveView } from './BreakoutActiveView'
import type { BreakoutSession } from '../api/types'

export const BreakoutPanel = () => {
  const roomData = useRoomData()
  const snap = useSnapshot(breakoutStore)
  const [localSession, setLocalSession] = useState<BreakoutSession | null>(null)

  // Trigger reactivity via snap, but use mutable store reference for child prop passing
  const session = snap.session
    ? (breakoutStore.session as BreakoutSession)
    : localSession
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
        setLocalSession(s)
        breakoutStore.session = s
      }}
    />
  )
}
