/**
 * Mutation hook: randomly assign participants across breakout rooms.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutSession } from './types'

interface RandomizeParams {
  roomId: string
  sessionId: string
  participants: { identity: string; name: string }[]
}

const randomizeAssignments = ({
  roomId,
  sessionId,
  participants,
}: RandomizeParams): Promise<BreakoutSession> => {
  return fetchApi<BreakoutSession>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/randomize/`,
    {
      method: 'POST',
      body: JSON.stringify({ participants }),
    }
  )
}

export const useRandomizeAssignments = () => {
  return useMutation({
    mutationFn: randomizeAssignments,
  })
}
