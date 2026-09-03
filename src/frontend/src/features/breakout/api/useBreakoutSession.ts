/**
 * Query hook: fetch active/configuring breakout session for a room.
 */

import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutSession } from './types'

const fetchBreakoutSessions = (roomId: string): Promise<BreakoutSession[]> => {
  return fetchApi<BreakoutSession[]>(`/rooms/${roomId}/breakout-sessions/`)
}

export const useBreakoutSession = (roomId: string | undefined) => {
  return useQuery({
    queryKey: ['breakout-session', roomId],
    queryFn: () => fetchBreakoutSessions(roomId!),
    enabled: !!roomId,
    refetchInterval: 10000,
    select: (sessions) => sessions[0] ?? null,
  })
}
