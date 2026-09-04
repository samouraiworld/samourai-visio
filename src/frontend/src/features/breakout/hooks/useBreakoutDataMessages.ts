/**
 * Hook to listen for breakout-related data messages (e.g. host broadcast announcements, recall to main room).
 */

import { useEffect, useRef } from 'react'
import { useRoomContext } from '@livekit/components-react'
import { RoomEvent, type RemoteParticipant } from 'livekit-client'
import { breakoutStore } from '../stores/breakout'
import { queryClient } from '@/api/queryClient'
import {
  isTrustedBreakoutControlMessage,
  parseBreakoutControlMessage,
} from '../utils/controlMessages'

interface UseBreakoutDataMessagesOptions {
  onRecall?: () => void
}

export const useBreakoutDataMessages = (
  options?: UseBreakoutDataMessagesOptions
) => {
  const room = useRoomContext()
  const onRecallRef = useRef(options?.onRecall)

  useEffect(() => {
    onRecallRef.current = options?.onRecall
  }, [options?.onRecall])

  useEffect(() => {
    if (!room) return

    const handleData = (
      payload: Uint8Array,
      participant?: RemoteParticipant
    ) => {
      const data = parseBreakoutControlMessage(payload)
      if (
        !data ||
        !isTrustedBreakoutControlMessage(data, Boolean(participant))
      ) {
        return
      }

      try {
        // Only accept control messages from the server (participant === undefined).
        // A remote participant must not be able to forge host-level commands.
        if (
          !participant &&
          data.type === 'breakout:broadcast' &&
          typeof data.message === 'string' &&
          data.message
        ) {
          breakoutStore.broadcastAnnouncement = {
            message: data.message,
            timestamp: Date.now(),
          }
        }

        if (!participant && data.type === 'breakout:revision') {
          breakoutStore.revisionHint = Math.max(
            breakoutStore.revisionHint,
            Number(data.revision) || 0
          )
        }

        if (!participant && data.type === 'breakout:help_revision') {
          void queryClient.invalidateQueries({
            queryKey: ['breakout-help-requests'],
          })
        }

        if (data.type === 'breakout:recall' || data.type === 'breakout:close') {
          // Reject recall/close from any remote participant — server only.
          if (!participant) {
            onRecallRef.current?.()
          }
        }
      } catch {
        // Invalid fields in a well-formed message are ignored.
      }
    }

    room.on(RoomEvent.DataReceived, handleData)
    return () => {
      room.off(RoomEvent.DataReceived, handleData)
    }
  }, [room])
}
