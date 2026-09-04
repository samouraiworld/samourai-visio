import { useCallback } from 'react'
import { useLocalParticipant } from '@livekit/components-react'
import { useSnapshot } from 'valtio'
import { fetchApi } from '@/api/fetchApi'
import { requestEntry } from '@/features/rooms/api/requestEntry'
import { userStore } from '@/stores/user'
import type { BreakoutLiveKitConnection } from '../api/types'
import { breakoutStore, triggerRoomSwap } from '../stores/breakout'
import { captureMediaIntent } from '../utils/mediaIntent'

interface RoomConnection {
  token: string
  roomName: string
}

interface UseBreakoutRoomSwapParams {
  currentRoomSlug?: string
  setActiveRoomConnection?: (connection: RoomConnection) => void
}

export const useBreakoutRoomSwap = ({
  currentRoomSlug,
  setActiveRoomConnection,
}: UseBreakoutRoomSwapParams = {}) => {
  const { username } = useSnapshot(userStore)
  const { localParticipant } = useLocalParticipant()

  const beginTransition = useCallback(() => {
    breakoutStore.transitionError = null
    breakoutStore.isTransitioning = true
    breakoutStore.pendingMediaIntent ??= captureMediaIntent(localParticipant)
  }, [localParticipant])

  const applyConnection = useCallback(
    (connection: RoomConnection) => {
      if (setActiveRoomConnection) setActiveRoomConnection(connection)
      else triggerRoomSwap(connection)
    },
    [setActiveRoomConnection]
  )

  const failTransition = useCallback((error: unknown) => {
    breakoutStore.isTransitioning = false
    breakoutStore.pendingMediaIntent = null
    breakoutStore.clearAfterTransition = false
    breakoutStore.transitionError =
      error instanceof Error ? error.message : 'room_transition_failed'
  }, [])

  const moveToBreakoutRoom = useCallback(
    async (
      breakoutRoomId: string,
      sessionId: string,
      roomId: string,
      roomDisplayName?: string,
      isModeratorVisit = false
    ) => {
      beginTransition()
      breakoutStore.transitionTargetName = roomDisplayName ?? null
      try {
        const response = await fetchApi<BreakoutLiveKitConnection>(
          `/rooms/${roomId}/breakout-sessions/${sessionId}/rooms/${breakoutRoomId}/join/`,
          { method: 'POST' }
        )

        breakoutStore.activeSessionId = sessionId
        breakoutStore.isModeratorVisiting = isModeratorVisit
        if (!isModeratorVisit) {
          breakoutStore.assignedRoomId = breakoutRoomId
          breakoutStore.pausedAssignmentRevision = null
        }
        breakoutStore.mainRoomSlug =
          currentRoomSlug ?? breakoutStore.mainRoomSlug
        breakoutStore.activeConnection = response.livekit
        applyConnection({
          token: response.livekit.token,
          roomName: response.livekit.room,
        })
        return response.livekit.room
      } catch (error) {
        failTransition(error)
        throw error
      }
    },
    [applyConnection, beginTransition, currentRoomSlug, failTransition]
  )

  const transitionToMainRoom = useCallback(
    async (clearOnConnect: boolean) => {
      const mainSlug = breakoutStore.mainRoomSlug
      if (!mainSlug) return

      beginTransition()
      breakoutStore.clearAfterTransition = clearOnConnect
      breakoutStore.transitionTargetName = null
      try {
        const response = await requestEntry({
          roomId: mainSlug,
          username: username ?? '',
        })
        if (!response.livekit) {
          throw new Error(`main_room_${response.status}`)
        }

        if (!breakoutStore.isModeratorVisiting) {
          breakoutStore.pausedAssignmentRevision = breakoutStore.revisionHint
        }
        breakoutStore.isModeratorVisiting = false
        breakoutStore.activeConnection = response.livekit
        applyConnection({
          token: response.livekit.token,
          roomName: response.livekit.room,
        })
      } catch (error) {
        failTransition(error)
        throw error
      }
    },
    [applyConnection, beginTransition, failTransition, username]
  )

  const returnToMainRoom = useCallback(
    () => transitionToMainRoom(false),
    [transitionToMainRoom]
  )
  const returnToMainRoomAfterClose = useCallback(
    () => transitionToMainRoom(true),
    [transitionToMainRoom]
  )

  return {
    moveToBreakoutRoom,
    returnToMainRoom,
    returnToMainRoomAfterClose,
  }
}
