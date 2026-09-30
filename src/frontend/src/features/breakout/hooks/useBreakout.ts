import { useEffect } from 'react'
import {
  useConnectionState,
  useLocalParticipant,
  useRoomContext,
  useRoomInfo,
} from '@livekit/components-react'
import { ConnectionState, type Room } from 'livekit-client'
import { requestEntry } from '@/features/rooms/api/requestEntry'
import { reportError } from '@/features/analytics/telemetry'
import { fetchBreakoutAssignment, joinBreakoutRoom } from '../api'
import { breakoutStore } from '../store'
import { captureMediaIntent } from '../utils/mediaIntent'
import { swapRoomConnection } from '../utils/roomLifecycle'
import {
  readBreakoutSessionId,
  shouldFetchAssignment,
} from '../utils/transitions'

// Hands a pass to Conference, which builds a new Room for it.
export type Connect = (token: string) => void

const moveToAssignedRoom = async (
  room: Room,
  mainRoomId: string,
  connect: Connect
) => {
  const assignment = await fetchBreakoutAssignment(mainRoomId)
  if (!assignment || breakoutStore.target) return
  breakoutStore.target = assignment.room
  try {
    const pass = await joinBreakoutRoom(
      mainRoomId,
      assignment.session_id,
      assignment.room.id
    )
    breakoutStore.pendingMedia = breakoutStore.media
    breakoutStore.leaving = true
    await swapRoomConnection(room, pass.token, (token) => {
      breakoutStore.leaving = false
      breakoutStore.room = assignment.room
      connect(token)
    })
  } catch (error) {
    Object.assign(breakoutStore, {
      target: null,
      leaving: false,
      pendingMedia: null,
    })
    throw error
  }
}

// Called once the breakout room is gone; the page reloads when no pass comes back.
export const returnToMainRoom = async (
  slug: string,
  username: string,
  connect: Connect
) => {
  // A failed join reaches both onDisconnected and onError; return once.
  if (breakoutStore.target === 'main' && breakoutStore.room) return
  breakoutStore.target = 'main'
  breakoutStore.pendingMedia = breakoutStore.media
  const entry = await requestEntry({ roomId: slug, username }).catch(
    (error) => {
      reportError('generic_failure', error, { path: 'breakout_return' })
      return null
    }
  )
  if (!entry?.livekit) return window.location.reload()
  breakoutStore.room = null
  connect(entry.livekit.token)
}

export const useBreakout = (mainRoomId: string, connect: Connect) => {
  const room = useRoomContext()
  const { metadata } = useRoomInfo()
  const state = useConnectionState()
  const { isCameraEnabled, isMicrophoneEnabled } = useLocalParticipant()

  // Recorded while connected, since a deleted room has already unpublished them.
  useEffect(() => {
    if (state !== ConnectionState.Connected || breakoutStore.pendingMedia)
      return
    breakoutStore.media = captureMediaIntent({
      isCameraEnabled,
      isMicrophoneEnabled,
    })
  }, [state, isCameraEnabled, isMicrophoneEnabled])

  const sessionId = readBreakoutSessionId(metadata)
  useEffect(() => {
    if (!sessionId && breakoutStore.moveFailed) breakoutStore.moveFailed = false
    if (state !== ConnectionState.Connected) return
    if (!shouldFetchAssignment(sessionId, breakoutStore)) return
    Object.assign(breakoutStore, { sessionId, moveFailed: false })
    moveToAssignedRoom(room, mainRoomId, connect).catch((error) => {
      // Forgotten, so the next metadata change or reconnect tries again.
      Object.assign(breakoutStore, { sessionId: null, moveFailed: true })
      reportError('generic_failure', error, { path: 'breakout_move' })
    })
  }, [state, sessionId, room, mainRoomId, connect])
}
