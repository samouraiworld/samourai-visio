/**
 * Mutation hook: bulk assign participants to breakout rooms.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutSession } from './types'

interface AssignParams {
  roomId: string
  sessionId: string
  assignments: Record<string, { identity: string; name: string }[]>
}

const assignParticipants = ({
  roomId,
  sessionId,
  assignments,
}: AssignParams): Promise<BreakoutSession> => {
  return fetchApi<BreakoutSession>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/assignments/`,
    {
      method: 'PUT',
      body: JSON.stringify({ assignments }),
    }
  )
}

export const useAssignParticipants = () => {
  return useMutation({
    mutationFn: assignParticipants,
  })
}
