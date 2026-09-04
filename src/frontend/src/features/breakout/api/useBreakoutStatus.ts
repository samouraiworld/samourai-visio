/**
 * Query hook: live breakout session status (participant counts).
 * Only used by the moderator.
 */

import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutSessionStatus } from './types'
import { BREAKOUT_DEFAULTS } from '../utils/constants'

const fetchBreakoutStatus = (
  roomId: string,
  sessionId: string
): Promise<BreakoutSessionStatus> => {
  return fetchApi<BreakoutSessionStatus>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/status/`
  )
}

export const useBreakoutStatus = (
  roomId: string | undefined,
  sessionId: string | undefined,
  enabled: boolean
) => {
  return useQuery({
    queryKey: ['breakout-status', roomId, sessionId],
    queryFn: () => fetchBreakoutStatus(roomId!, sessionId!),
    enabled: enabled && !!roomId && !!sessionId,
    refetchInterval: BREAKOUT_DEFAULTS.STATUS_POLL_INTERVAL_MS,
  })
}
