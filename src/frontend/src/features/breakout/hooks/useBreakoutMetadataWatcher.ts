import { useEffect, useMemo, useRef } from 'react'
import { useRoomInfo } from '@livekit/components-react'
import { useSnapshot } from 'valtio'
import type { BreakoutMetadata } from '../api/types'
import { useCurrentBreakoutAssignment } from '../api/useCurrentBreakoutAssignment'
import { breakoutStore, clearBreakoutState } from '../stores/breakout'
import { useBreakoutRoomSwap } from './useBreakoutRoomSwap'

interface UseBreakoutMetadataWatcherParams {
  currentRoomSlug: string
  setActiveRoomConnection: (connection: {
    token: string
    roomName: string
  }) => void
  mainRoomId: string
}

export const useBreakoutMetadataWatcher = ({
  currentRoomSlug,
  setActiveRoomConnection,
  mainRoomId,
}: UseBreakoutMetadataWatcherParams) => {
  const roomInfo = useRoomInfo()
  const snapshot = useSnapshot(breakoutStore)
  const transitionRevision = useRef<number | null>(null)
  const { moveToBreakoutRoom, returnToMainRoom, returnToMainRoomAfterClose } =
    useBreakoutRoomSwap({ currentRoomSlug, setActiveRoomConnection })

  const metadata = useMemo(() => {
    if (!roomInfo?.metadata) return null
    try {
      return (JSON.parse(roomInfo.metadata) as { breakout?: BreakoutMetadata })
        .breakout
    } catch {
      return null
    }
  }, [roomInfo?.metadata])

  const sessionId =
    metadata?.session_id ?? snapshot.activeSessionId ?? undefined
  const { data: assignmentState, refetch: refetchAssignment } =
    useCurrentBreakoutAssignment(mainRoomId, sessionId)

  useEffect(() => {
    if (!metadata) return
    breakoutStore.activeSessionId = metadata.session_id
    breakoutStore.revisionHint = Math.max(
      breakoutStore.revisionHint,
      metadata.revision
    )
  }, [metadata])

  useEffect(() => {
    if (snapshot.revisionHint > (assignmentState?.revision ?? -1)) {
      void refetchAssignment()
    }
  }, [assignmentState?.revision, refetchAssignment, snapshot.revisionHint])

  useEffect(() => {
    const state = assignmentState
    if (!state || breakoutStore.isTransitioning) return

    breakoutStore.activeSessionId = state.session_id
    breakoutStore.revisionHint = Math.max(
      breakoutStore.revisionHint,
      state.revision
    )

    if (state.status === 'closing' || state.status === 'closed') {
      if (breakoutStore.currentBreakoutRoomLkName) {
        void returnToMainRoomAfterClose().catch(() => undefined)
      } else {
        clearBreakoutState()
      }
      return
    }

    if (state.status !== 'active' || breakoutStore.isModeratorVisiting) return

    const assignment = state.assignment
    if (!assignment) {
      breakoutStore.assignedRoomId = null
      if (breakoutStore.currentBreakoutRoomLkName) void returnToMainRoom()
      return
    }

    breakoutStore.assignedRoomId = assignment.breakout_room_id
    const isAlreadyThere =
      breakoutStore.currentBreakoutRoomLkName === assignment.livekit_room_name
    const isPausedHere =
      !breakoutStore.currentBreakoutRoomLkName &&
      breakoutStore.pausedAssignmentRevision === state.revision
    const alreadyTransitioned = transitionRevision.current === state.revision

    if (!isAlreadyThere && !isPausedHere && !alreadyTransitioned) {
      transitionRevision.current = state.revision
      void moveToBreakoutRoom(
        assignment.breakout_room_id,
        state.session_id,
        mainRoomId,
        assignment.breakout_room_name
      ).catch(() => {
        transitionRevision.current = null
      })
    }
  }, [
    assignmentState,
    mainRoomId,
    moveToBreakoutRoom,
    returnToMainRoom,
    returnToMainRoomAfterClose,
  ])
}
