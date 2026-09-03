/**
 * Hook to listen for breakout-related data messages (e.g. host broadcast announcements, recall to main room).
 */

import { useEffect, useRef } from 'react'
import { useRoomContext } from '@livekit/components-react'
import { RoomEvent, type RemoteParticipant } from 'livekit-client'
import { breakoutStore } from '../stores/breakout'

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
      try {
        const text = new TextDecoder().decode(payload)
        const data = JSON.parse(text)

        // Only accept control messages from the server (participant === undefined).
        // A remote participant must not be able to forge host-level commands.
        if (
          !participant &&
          data.type === 'breakout:broadcast' &&
          data.message
        ) {
          breakoutStore.broadcastAnnouncement = {
            message: data.message,
            timestamp: Date.now(),
          }
        }

        // breakout:help_request is legitimately participant-sourced (guests
        // send it to surface the SOS beacon on the host panel).
        if (data.type === 'breakout:help_request') {
          breakoutStore.helpAlert = {
            roomName: data.room_name || 'Breakout Room',
            participantName: data.participant_name || 'A participant',
            breakoutRoomId: data.breakout_room_id || '',
            sessionId: data.session_id || '',
            timestamp: Date.now(),
          }
        }

        if (data.type === 'breakout:recall' || data.type === 'breakout:close') {
          // Reject recall/close from any remote participant — server only.
          if (!participant) {
            onRecallRef.current?.()
          }
        }
      } catch {
        // Not a JSON message — ignore
      }
    }

    room.on(RoomEvent.DataReceived, handleData)
    return () => {
      room.off(RoomEvent.DataReceived, handleData)
    }
  }, [room])
}
