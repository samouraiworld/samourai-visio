/**
 * Mutation hook: bulk assign participants to breakout rooms.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutSession } from './types'
import { queryClient } from '@/api/queryClient'
import { breakoutSessionKey } from './useBreakoutSession'

interface AssignParams {
  roomId: string
  sessionId: string
  revision: number
  assignments: Record<string, { identity: string; name: string }[]>
}

const assignParticipants = ({
  roomId,
  sessionId,
  revision,
  assignments,
}: AssignParams): Promise<BreakoutSession> => {
  return fetchApi<BreakoutSession>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/assignments/`,
    {
      method: 'PUT',
      body: JSON.stringify({ assignments, revision }),
    }
  )
}

export const useAssignParticipants = () => {
  return useMutation({
    mutationFn: assignParticipants,
    onSuccess: (session, variables) => {
      queryClient.setQueryData(breakoutSessionKey(variables.roomId), [session])
    },
  })
}
