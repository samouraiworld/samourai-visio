/**
 * Mutation hook: activate or close a breakout session.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutSession } from './types'

interface UpdateParams {
  roomId: string
  sessionId: string
  status: 'active' | 'closed'
}

const updateBreakoutSession = ({
  roomId,
  sessionId,
  status,
}: UpdateParams): Promise<BreakoutSession> => {
  return fetchApi<BreakoutSession>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/`,
    {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }
  )
}

export const useUpdateBreakoutSession = () => {
  return useMutation({
    mutationFn: updateBreakoutSession,
  })
}
