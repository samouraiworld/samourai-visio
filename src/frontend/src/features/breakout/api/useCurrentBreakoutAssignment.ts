import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
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
