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
  username?: string
  participantId?: string
}

const joinBreakoutRoom = ({
  roomId,
  sessionId,
  breakoutRoomId,
  username,
  participantId,
}: JoinParams): Promise<BreakoutLiveKitConnection> => {
  return fetchApi<BreakoutLiveKitConnection>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/rooms/${breakoutRoomId}/join/`,
    {
      method: 'POST',
      body: JSON.stringify({
        username: username ?? '',
        participant_id: participantId ?? '',
      }),
    }
  )
}

export const useJoinBreakoutRoom = () => {
  return useMutation({
    mutationFn: joinBreakoutRoom,
  })
}
