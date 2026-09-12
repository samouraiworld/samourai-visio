/**
 * Turn breakout data packets into server refreshes.
 *
 * Packets are hints only: any participant can publish one, and livekit-client
 * reports an undefined sender whenever the publisher is absent from the local
 * participant map. Nothing here changes breakout state from packet content.
 */

import { useEffect, useRef } from 'react'
import { useRoomContext } from '@livekit/components-react'
import { RoomEvent } from 'livekit-client'
import { requestAssignmentRefresh } from '../stores/breakout'
import { queryClient } from '@/api/queryClient'
import {
  classifyBreakoutHint,
  parseBreakoutControlMessage,
  type BreakoutHint,
} from '../utils/controlMessages'

/**
 * Any participant can publish packets, so act on at most one hint of each kind
 * per interval. The poll is authoritative and runs anyway, so a dropped hint
 * costs latency, never correctness.
 */
const HINT_MIN_INTERVAL_MS = 2000

export const useBreakoutDataMessages = () => {
  const room = useRoomContext()
  const lastHintAt = useRef<Record<BreakoutHint, number>>({
    help: 0,
    refresh: 0,
  })

  useEffect(() => {
    if (!room) return

    const handleData = (payload: Uint8Array) => {
      const data = parseBreakoutControlMessage(payload)
      const hint = data ? classifyBreakoutHint(data) : null
      if (!hint) return

      const now = Date.now()
      if (now - lastHintAt.current[hint] < HINT_MIN_INTERVAL_MS) return
      lastHintAt.current[hint] = now

      if (hint === 'help') {
        void queryClient.invalidateQueries({
          queryKey: ['breakout-help-requests'],
        })
      } else {
        requestAssignmentRefresh()
      }
    }

    room.on(RoomEvent.DataReceived, handleData)
    return () => {
      room.off(RoomEvent.DataReceived, handleData)
    }
  }, [room])
}
