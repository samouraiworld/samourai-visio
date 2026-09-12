import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutHelpRequest } from './types'
import { queryClient } from '@/api/queryClient'
import { breakoutAssignmentKey } from './useCurrentBreakoutAssignment'

export const useCancelBreakoutHelp = () =>
  useMutation({
    mutationFn: ({
      roomId,
      sessionId,
    }: {
      roomId: string
      sessionId: string
    }) =>
      fetchApi<BreakoutHelpRequest>(
        `/rooms/${roomId}/breakout-sessions/${sessionId}/cancel-help/`,
        { method: 'POST' }
      ),
    onSuccess: (_request, variables) =>
      queryClient.invalidateQueries({
        queryKey: breakoutAssignmentKey(variables.roomId, variables.sessionId),
      }),
  })
