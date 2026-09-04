/**
 * Mutation hook: get a LiveKit token for a breakout room.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutLiveKitConnection } from './types'

interface JoinParams {
  roomId: string
  sessionId: string
  breakoutRoomId: string
}

const joinBreakoutRoom = ({
  roomId,
  sessionId,
  breakoutRoomId,
}: JoinParams): Promise<BreakoutLiveKitConnection> => {
  return fetchApi<BreakoutLiveKitConnection>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/rooms/${breakoutRoomId}/join/`,
    {
      method: 'POST',
    }
  )
}

export const useJoinBreakoutRoom = () => {
  return useMutation({
    mutationFn: joinBreakoutRoom,
  })
}
