/**
 * Mutation hook: request help from the host while inside a breakout room.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import type { BreakoutHelpRequest } from './types'
import { queryClient } from '@/api/queryClient'
import { breakoutAssignmentKey } from './useCurrentBreakoutAssignment'

interface RequestHelpParams {
  roomId: string
  sessionId: string
}

const requestHelp = ({
  roomId,
  sessionId,
}: RequestHelpParams): Promise<BreakoutHelpRequest> => {
  return fetchApi<BreakoutHelpRequest>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/request-help/`,
    {
      method: 'POST',
    }
  )
}

export const useRequestBreakoutHelp = () => {
  return useMutation({
    mutationFn: requestHelp,
    onSuccess: (_request, variables) =>
      queryClient.invalidateQueries({
        queryKey: breakoutAssignmentKey(variables.roomId, variables.sessionId),
      }),
  })
}
