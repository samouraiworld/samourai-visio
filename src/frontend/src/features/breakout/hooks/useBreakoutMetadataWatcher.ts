import { useEffect, useMemo, useRef } from 'react'
import { useRoomInfo } from '@livekit/components-react'
import { useSnapshot } from 'valtio'
import type { BreakoutMetadata } from '../api/types'
import { useCurrentBreakoutAssignment } from '../api/useCurrentBreakoutAssignment'
import { breakoutStore, clearBreakoutSession } from '../stores/breakout'
import { resolveAssignmentAction } from '../utils/assignmentActions'
import { shouldShowBroadcast } from '../utils/broadcastDisplay'
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
  // One transition attempt per poll result: a refused join must wait for the
  // next poll (or the next hint), never loop on the store flag flipping back.
  const attemptedAt = useRef(0)
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
  const {
    data: assignmentState,
    dataUpdatedAt,
    refetch: refetchAssignment,
  } = useCurrentBreakoutAssignment(mainRoomId, sessionId)

  // Room metadata is server-authored: it is the only source of revisionHint.
  useEffect(() => {
    if (!metadata) return
    breakoutStore.activeSessionId = metadata.session_id
    breakoutStore.revisionHint = Math.max(
      breakoutStore.revisionHint,
      metadata.revision
    )
  }, [metadata])

  // refetch() ignores `enabled`, so never fetch an undefined key.
  const canFetch = !!mainRoomId && !!sessionId

  useEffect(() => {
    if (!canFetch) return
    if (snapshot.revisionHint > (assignmentState?.revision ?? -1)) {
      void refetchAssignment()
    }
  }, [
    assignmentState?.revision,
    canFetch,
    refetchAssignment,
    snapshot.revisionHint,
  ])

  useEffect(() => {
    if (!canFetch || snapshot.assignmentRefreshNonce === 0) return
    void refetchAssignment()
  }, [canFetch, refetchAssignment, snapshot.assignmentRefreshNonce])

  // Announcements come from the poll; show each one once.
  const lastBroadcastSentAt = assignmentState?.last_broadcast?.sent_at ?? null
  const lastBroadcastMessage = assignmentState?.last_broadcast?.message ?? null
  useEffect(() => {
    if (!lastBroadcastSentAt || !lastBroadcastMessage) return
    const shown = breakoutStore.lastBroadcastShownAt
    if (!shouldShowBroadcast(shown, lastBroadcastSentAt, Date.now())) {
      // Older than the freshness window at first sight: remember it as seen.
      if (shown === null)
        breakoutStore.lastBroadcastShownAt = lastBroadcastSentAt
      return
    }
    breakoutStore.lastBroadcastShownAt = lastBroadcastSentAt
    breakoutStore.broadcastAnnouncement = {
      message: lastBroadcastMessage,
      timestamp: Date.parse(lastBroadcastSentAt),
    }
  }, [lastBroadcastMessage, lastBroadcastSentAt])

  // Primitive dependencies: the poll returns a structurally shared object, so
  // depending on the object itself would never re-run this effect.
  const status = assignmentState?.status
  const revision = assignmentState?.revision
  const polledSessionId = assignmentState?.session_id
  const endsAt = assignmentState?.ends_at ?? null
  const assignedRoomId = assignmentState?.assignment?.breakout_room_id ?? null
  const assignedRoomName =
    assignmentState?.assignment?.breakout_room_name ?? null
  const assignedLkName = assignmentState?.assignment?.livekit_room_name ?? null

  useEffect(() => {
    if (!status || revision === undefined || !polledSessionId) return

    breakoutStore.activeSessionId = polledSessionId
    breakoutStore.revisionHint = Math.max(breakoutStore.revisionHint, revision)
    if (status === 'active' && !snapshot.isModeratorVisiting) {
      breakoutStore.assignedRoomId = assignedRoomId
    }

    const action = resolveAssignmentAction({
      status,
      revision,
      assignment: assignedRoomId
        ? {
            breakout_room_id: assignedRoomId,
            breakout_room_name: assignedRoomName ?? '',
            livekit_room_name: assignedLkName ?? '',
          }
        : null,
      isExpired: endsAt !== null && Date.parse(endsAt) <= Date.now(),
      isTransitioning: snapshot.isTransitioning,
      isModeratorVisiting: snapshot.isModeratorVisiting,
      currentBreakoutRoomLkName: snapshot.currentBreakoutRoomLkName,
      connectionLost: snapshot.connectionLost,
      pausedAssignmentRevision: snapshot.pausedAssignmentRevision,
      lastTransitionRevision: transitionRevision.current,
    })

    if (action.type === 'none') return
    if (action.type === 'clear') {
      clearBreakoutSession()
      return
    }
    if (attemptedAt.current === dataUpdatedAt) return
    attemptedAt.current = dataUpdatedAt

    switch (action.type) {
      case 'return-after-close':
        void returnToMainRoomAfterClose().catch(() => undefined)
        return
      case 'return-to-main':
        breakoutStore.assignedRoomId = null
        void returnToMainRoom().catch(() => undefined)
        return
      case 'move':
        transitionRevision.current = action.revision
        void moveToBreakoutRoom(
          action.breakoutRoomId,
          polledSessionId,
          mainRoomId,
          action.breakoutRoomName
        ).catch((error: unknown) => {
          console.warn('breakout move failed; next poll retries', error)
          transitionRevision.current = null
        })
    }
  }, [
    assignedLkName,
    assignedRoomId,
    assignedRoomName,
    dataUpdatedAt,
    endsAt,
    mainRoomId,
    moveToBreakoutRoom,
    polledSessionId,
    returnToMainRoom,
    returnToMainRoomAfterClose,
    revision,
    snapshot.connectionLost,
    snapshot.currentBreakoutRoomLkName,
    snapshot.isModeratorVisiting,
    snapshot.isTransitioning,
    snapshot.pausedAssignmentRevision,
    status,
  ])
}
