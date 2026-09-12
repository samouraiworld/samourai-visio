import { useCallback } from 'react'
import { useLocalParticipant, useRoomContext } from '@livekit/components-react'
import { useSnapshot } from 'valtio'
import { fetchApi } from '@/api/fetchApi'
import { requestEntry } from '@/features/rooms/api/requestEntry'
import { userStore } from '@/stores/user'
import type { BreakoutLiveKitConnection } from '../api/types'
import {
  breakoutStore,
  completeBreakoutTransition,
  prepareLobbyReentry,
  triggerRoomSwap,
} from '../stores/breakout'
import { captureMediaIntent } from '../utils/mediaIntent'
import { swapRoomConnection } from '../utils/roomLifecycle'

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
  const room = useRoomContext()

  const beginTransition = useCallback(() => {
    breakoutStore.transitionError = null
    breakoutStore.isTransitioning = true
    breakoutStore.pendingMediaIntent ??= captureMediaIntent(localParticipant)
  }, [localParticipant])

  const applyConnection = useCallback(
    async (connection: RoomConnection) => {
      if (room.state === 'connected' && room.name === connection.roomName) {
        completeBreakoutTransition()
        return
      }
      // Room.connect() returns immediately when the room object is already
      // connected and never looks at the token, so the meeting has to be left
      // before the remount hands the breakout token over. See roomLifecycle.
      await swapRoomConnection(room, connection, (next) => {
        if (setActiveRoomConnection) setActiveRoomConnection(next)
        else triggerRoomSwap(next)
      })
    },
    [room, setActiveRoomConnection]
  )

  const failTransition = useCallback(
    (error: unknown) => {
      breakoutStore.isTransitioning = false
      if (room.state === 'connected') breakoutStore.pendingMediaIntent = null
      breakoutStore.clearAfterTransition = false
      breakoutStore.transitionError =
        error instanceof Error ? error.message : 'room_transition_failed'
    },
    [room]
  )

  const moveToBreakoutRoom = useCallback(
    async (
      breakoutRoomId: string,
      sessionId: string,
      roomId: string,
      roomDisplayName?: string,
      isModeratorVisit = false
    ) => {
      if (breakoutStore.isTransitioning)
        throw new Error('room_transition_in_progress')
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
        await applyConnection({
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
      if (!mainSlug || breakoutStore.isTransitioning) return

      // Nothing to return from: a participant already in the meeting would
      // otherwise be disconnected and reconnected to the room they are in.
      // The lost-connection recovery path keeps currentBreakoutRoomLkName set,
      // so it still passes here.
      if (
        !breakoutStore.currentBreakoutRoomLkName &&
        !breakoutStore.connectionLost
      )
        return

      beginTransition()
      breakoutStore.clearAfterTransition = clearOnConnect
      breakoutStore.transitionTargetName = null
      try {
        const response = await requestEntry({
          roomId: mainSlug,
          username: username ?? '',
        })
        // Record the deliberate-return intent first: the re-entry path below
        // must keep it, or the watcher moves the participant straight back.
        if (!breakoutStore.isModeratorVisiting) {
          breakoutStore.pausedAssignmentRevision = breakoutStore.revisionHint
        }
        if (!response.livekit) {
          prepareLobbyReentry()
          window.location.reload()
          return
        }
        breakoutStore.isModeratorVisiting = false
        await applyConnection({
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
