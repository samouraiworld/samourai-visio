/**
 * Mutation hook: create a new breakout session.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutSession } from './types'

interface CreateParams {
  roomId: string
  numRooms: number
  durationSeconds?: number | null
  roomNames?: string[]
}

const createBreakoutSession = ({
  roomId,
  numRooms,
  durationSeconds,
  roomNames,
}: CreateParams): Promise<BreakoutSession> => {
  return fetchApi<BreakoutSession>(`/rooms/${roomId}/breakout-sessions/`, {
    method: 'POST',
    body: JSON.stringify({
      num_rooms: numRooms,
      duration_seconds: durationSeconds,
      room_names: roomNames,
    }),
  })
}

export const useCreateBreakoutSession = () => {
  return useMutation({
    mutationFn: createBreakoutSession,
  })
}
