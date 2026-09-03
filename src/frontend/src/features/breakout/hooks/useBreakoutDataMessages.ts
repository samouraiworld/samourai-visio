/**
 * Hook to listen for breakout-related data messages (e.g. host broadcast announcements, recall to main room).
 */

import { useEffect, useRef } from 'react'
import { useRoomContext } from '@livekit/components-react'
import { RoomEvent } from 'livekit-client'
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

    const handleData = (payload: Uint8Array) => {
      try {
        const text = new TextDecoder().decode(payload)
        const data = JSON.parse(text)

        if (data.type === 'breakout:broadcast' && data.message) {
          breakoutStore.broadcastAnnouncement = {
            message: data.message,
            timestamp: Date.now(),
          }
        }

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
          onRecallRef.current?.()
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
