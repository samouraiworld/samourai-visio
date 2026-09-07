/**
 * Turn breakout data packets into server refreshes.
 *
 * Packets are hints only: any participant can publish one, and livekit-client
 * reports an undefined sender whenever the publisher is absent from the local
 * participant map. Nothing here changes breakout state from packet content.
 */

import { useEffect } from 'react'
import { useRoomContext } from '@livekit/components-react'
import { RoomEvent } from 'livekit-client'
import { requestAssignmentRefresh } from '../stores/breakout'
import { queryClient } from '@/api/queryClient'
import {
  classifyBreakoutHint,
  parseBreakoutControlMessage,
} from '../utils/controlMessages'

export const useBreakoutDataMessages = () => {
  const room = useRoomContext()

  useEffect(() => {
    if (!room) return

    const handleData = (payload: Uint8Array) => {
      const data = parseBreakoutControlMessage(payload)
      const hint = data ? classifyBreakoutHint(data) : null
      if (hint === 'help') {
        void queryClient.invalidateQueries({
          queryKey: ['breakout-help-requests'],
        })
      } else if (hint === 'refresh') {
        requestAssignmentRefresh()
      }
    }

    room.on(RoomEvent.DataReceived, handleData)
    return () => {
      room.off(RoomEvent.DataReceived, handleData)
    }
  }, [room])
}
