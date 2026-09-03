/**
 * Mutation hook: broadcast an announcement message to all breakout rooms.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'

interface BroadcastParams {
  roomId: string
  sessionId: string
  message: string
}

interface BroadcastResponse {
  status: string
  recipient_rooms: number
}

const broadcastMessage = ({
  roomId,
  sessionId,
  message,
}: BroadcastParams): Promise<BroadcastResponse> => {
  return fetchApi<BroadcastResponse>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/broadcast/`,
    {
      method: 'POST',
      body: JSON.stringify({ message }),
    }
  )
}

export const useBroadcastMessage = () => {
  return useMutation({
    mutationFn: broadcastMessage,
  })
}
