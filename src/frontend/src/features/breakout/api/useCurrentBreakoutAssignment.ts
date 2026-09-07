import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import { queryClient } from '@/api/queryClient'
import type { BreakoutCurrentAssignment } from './types'

export const breakoutAssignmentKey = (roomId?: string, sessionId?: string) =>
  ['breakout-current-assignment', roomId, sessionId] as const

export const useCurrentBreakoutAssignment = (
  roomId?: string,
  sessionId?: string
) =>
  useQuery({
    queryKey: breakoutAssignmentKey(roomId, sessionId),
    queryFn: () =>
      fetchApi<BreakoutCurrentAssignment>(
        `/rooms/${roomId}/breakout-sessions/${sessionId}/current-assignment/`
      ),
    enabled: !!roomId && !!sessionId,
    refetchInterval: 5000,
    retry: false,
  })

/** Fetch the caller's assignment now and share the result with the poll. */
export const fetchCurrentBreakoutAssignment = (
  roomId: string,
  sessionId: string
) =>
  queryClient.fetchQuery({
    queryKey: breakoutAssignmentKey(roomId, sessionId),
    queryFn: () =>
      fetchApi<BreakoutCurrentAssignment>(
        `/rooms/${roomId}/breakout-sessions/${sessionId}/current-assignment/`
      ),
    staleTime: 0,
  })
