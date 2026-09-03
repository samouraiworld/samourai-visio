/**
 * Watch LiveKit room metadata for breakout state changes.
 *
 * Room metadata is the SOURCE OF TRUTH for breakout state.
 * Data messages are just push optimizations — this watcher
 * handles the case where a data message was missed.
 */

import { useEffect, useRef } from 'react'
import { useLocalParticipant, useRoomInfo } from '@livekit/components-react'
import { useSnapshot } from 'valtio'
import { breakoutStore, clearBreakoutState } from '../stores/breakout'
import { useBreakoutRoomSwap } from './useBreakoutRoomSwap'
import type { BreakoutMetadata } from '../api/types'

interface UseBreakoutMetadataWatcherParams {
  currentRoomSlug: string
  setActiveRoomConnection: (conn: { token: string; roomName: string }) => void
  /** The main room's UUID (used to verify we're watching the right room). */
  mainRoomId: string
}

export const useBreakoutMetadataWatcher = ({
  currentRoomSlug,
  setActiveRoomConnection,
  mainRoomId,
}: UseBreakoutMetadataWatcherParams) => {
  const roomInfo = useRoomInfo()
  const { localParticipant } = useLocalParticipant()
  const { moveToBreakoutRoom, returnToMainRoom } = useBreakoutRoomSwap({
    currentRoomSlug,
    setActiveRoomConnection,
  })
  const snap = useSnapshot(breakoutStore)
  const hasTriggeredRef = useRef(false)

  useEffect(() => {
    if (!roomInfo?.metadata) return

    let meta: { breakout?: BreakoutMetadata }
    try {
      meta = JSON.parse(roomInfo.metadata)
    } catch {
      return
    }

    if (!meta.breakout) return

    const breakout = meta.breakout
    // Use the LiveKit participant's identity — this is exactly user.sub
    // (set by generate_token on the backend), which matches assignment keys.
    const myIdentity = localParticipant?.identity

    const isCurrentlyInMainRoom =
      !roomInfo?.name || !roomInfo.name.startsWith('breakout_')

    // ── Activation or Page-Refresh Reconnection: move to assigned breakout room ──
    if (
      breakout.status === 'active' &&
      (isCurrentlyInMainRoom || !breakoutStore.currentBreakoutRoomLkName) &&
      !breakoutStore.isTransitioning &&
      !hasTriggeredRef.current
    ) {
      const myAssignment = myIdentity
        ? breakout.assignments[myIdentity]
        : undefined
      if (myAssignment) {
        hasTriggeredRef.current = true

        // Store session info
        breakoutStore.session = {
          id: breakout.session_id,
          status: 'active',
          duration_seconds: breakout.duration_seconds ?? null,
          started_at: breakout.started_at ?? null,
          closed_at: null,
          created_at: '',
          breakout_rooms: breakout.rooms.map((r) => ({
            ...r,
            assignments: [],
          })),
        }

        const targetRoom = breakout.rooms.find(
          (r) => r.id === myAssignment.breakout_room_id
        )
        moveToBreakoutRoom(
          myAssignment.breakout_room_id,
          breakout.session_id,
          mainRoomId,
          targetRoom?.name,
          localParticipant?.identity
        ).catch(() => {
          hasTriggeredRef.current = false
        })
      }
    }

    // ── In-flight reassignment: move to new room if host reassigns while active ──
    if (
      breakout.status === 'active' &&
      breakoutStore.currentBreakoutRoomLkName &&
      !breakoutStore.isTransitioning &&
      myIdentity
    ) {
      const myAssignment = breakout.assignments[myIdentity]
      const currentAssignedId = breakoutStore.assignedRoomId

      if (myAssignment && myAssignment.breakout_room_id !== currentAssignedId) {
        const targetRoom = breakout.rooms.find(
          (r) => r.id === myAssignment.breakout_room_id
        )
        moveToBreakoutRoom(
          myAssignment.breakout_room_id,
          breakout.session_id,
          mainRoomId,
          targetRoom?.name,
          localParticipant?.identity
        ).catch((err) => {
          console.error('Failed to move to reassigned breakout room:', err)
        })
      } else if (!myAssignment && currentAssignedId) {
        returnToMainRoom()
      }
    }

    // ── Closed: return to main room and clear state ──
    if (
      breakout.status === 'closed' &&
      (breakoutStore.currentBreakoutRoomLkName || !isCurrentlyInMainRoom) &&
      !breakoutStore.isTransitioning
    ) {
      returnToMainRoom()
      clearBreakoutState()
    }
  }, [
    roomInfo?.metadata,
    roomInfo?.name,
    localParticipant?.identity,
    mainRoomId,
    moveToBreakoutRoom,
    returnToMainRoom,
  ])

  // Reset trigger ref when session changes
  useEffect(() => {
    if (!snap.activeSessionId) {
      hasTriggeredRef.current = false
    }
  }, [snap.activeSessionId])
}
