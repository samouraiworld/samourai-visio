/**
 * Core hook: disconnect from current LiveKit room and connect to another.
 *
 * Uses the in-component room swap pattern: updates shared state that
 * triggers the Conference component to remount `<LiveKitRoom>` with a
 * new key/token, instead of navigating to a new URL.
 *
 * The `setActiveRoomConnection` callback must be provided by the
 * Conference component.
 */

import { useCallback } from 'react'
import { useLocalParticipant } from '@livekit/components-react'
import {
  breakoutStore,
  clearBreakoutState,
  triggerRoomSwap,
} from '../stores/breakout'
import { fetchRoom } from '@/features/rooms/api/fetchRoom'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutLiveKitConnection } from '../api/types'
import { useSnapshot } from 'valtio'
import { userStore } from '@/stores/user'

interface RoomConnection {
  token: string
  roomName: string
}

interface UseBreakoutRoomSwapParams {
  /** The slug of the current main room. */
  currentRoomSlug?: string
  /** Callback to update the active LiveKit connection in Conference. */
  setActiveRoomConnection?: (conn: RoomConnection) => void
}

export const useBreakoutRoomSwap = ({
  currentRoomSlug,
  setActiveRoomConnection,
}: UseBreakoutRoomSwapParams = {}) => {
  const { username } = useSnapshot(userStore)
  const { localParticipant } = useLocalParticipant()

  const moveToBreakoutRoom = useCallback(
    async (
      breakoutRoomId: string,
      sessionId: string,
      roomId: string,
      roomDisplayName?: string,
      participantIdentity?: string
    ) => {
      breakoutStore.isTransitioning = true
      breakoutStore.transitionTargetName = roomDisplayName ?? null

      try {
        const resolvedIdentity =
          participantIdentity ||
          localParticipant?.identity ||
          (typeof window !== 'undefined'
            ? sessionStorage.getItem('meet_lk_participant_identity') ||
              sessionStorage.getItem('meet_anon_participant_id') ||
              undefined
            : undefined)

        if (localParticipant?.identity && typeof window !== 'undefined') {
          sessionStorage.setItem(
            'meet_lk_participant_identity',
            localParticipant.identity
          )
        }

        // Request token for the breakout room
        const response = await fetchApi<BreakoutLiveKitConnection>(
          `/rooms/${roomId}/breakout-sessions/${sessionId}/rooms/${breakoutRoomId}/join/`,
          {
            method: 'POST',
            body: JSON.stringify({
              username: username ?? '',
              participant_id: resolvedIdentity,
            }),
          }
        )

        // Update store state
        breakoutStore.activeSessionId = sessionId
        breakoutStore.assignedRoomId = breakoutRoomId
        breakoutStore.mainRoomSlug = currentRoomSlug ?? null
        breakoutStore.currentBreakoutRoomLkName = response.livekit.room
        breakoutStore.activeConnection = response.livekit

        // Trigger LiveKitRoom remount via key change
        const conn = {
          token: response.livekit.token,
          roomName: response.livekit.room,
        }
        if (setActiveRoomConnection) {
          setActiveRoomConnection(conn)
        } else {
          triggerRoomSwap(conn)
        }
      } catch (error) {
        console.error('Failed to move to breakout room:', error)
        breakoutStore.isTransitioning = false
        throw error
      }

      // Delay clearing the transitioning flag to ensure LiveKitRoom
      // has started connecting (prevents onDisconnected race)
      setTimeout(() => {
        breakoutStore.isTransitioning = false
      }, 2000)
    },
    [
      currentRoomSlug,
      localParticipant?.identity,
      setActiveRoomConnection,
      username,
    ]
  )

  const returnToMainRoom = useCallback(async () => {
    const mainSlug = breakoutStore.mainRoomSlug
    if (!mainSlug) return

    breakoutStore.isTransitioning = true

    try {
      // Fetch fresh token for the main room
      const data = await fetchRoom({
        roomId: mainSlug,
        username: username ?? '',
      })

      if (!data?.livekit) {
        throw new Error('Failed to get main room token')
      }

      // Trigger LiveKitRoom remount with main room token
      const mainConn = {
        token: data.livekit.token,
        roomName: data.livekit.room,
      }
      if (setActiveRoomConnection) {
        setActiveRoomConnection(mainConn)
      } else {
        triggerRoomSwap(mainConn)
      }

      // Clear breakout state after remount is triggered
      // Delay slightly so LiveKitRoom's onDisconnected doesn't fire first
      setTimeout(() => {
        clearBreakoutState()
      }, 2000)
    } catch (error) {
      console.error('Failed to return to main room:', error)
      breakoutStore.isTransitioning = false
      throw error
    }
  }, [setActiveRoomConnection, username])

  return { moveToBreakoutRoom, returnToMainRoom }
}
