/**
 * Mutation hook: randomly assign participants across breakout rooms.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutSession } from './types'
import { queryClient } from '@/api/queryClient'
import { breakoutSessionKey } from './useBreakoutSession'

interface RandomizeParams {
  roomId: string
  sessionId: string
  revision: number
  participants: { identity: string; name: string }[]
}

const randomizeAssignments = ({
  roomId,
  sessionId,
  revision,
  participants,
}: RandomizeParams): Promise<BreakoutSession> => {
  return fetchApi<BreakoutSession>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/randomize/`,
    {
      method: 'POST',
      body: JSON.stringify({ participants, revision }),
    }
  )
}

export const useRandomizeAssignments = () => {
  return useMutation({
    mutationFn: randomizeAssignments,
    onSuccess: (session, variables) => {
      queryClient.setQueryData(breakoutSessionKey(variables.roomId), [session])
    },
  })
}
