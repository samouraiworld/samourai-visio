import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import { queryClient } from '@/api/queryClient'
import type { BreakoutSession } from './types'
import { breakoutSessionKey } from './useBreakoutSession'

export const useRetryBreakoutSession = () =>
  useMutation({
    mutationFn: ({
      roomId,
      sessionId,
    }: {
      roomId: string
      sessionId: string
    }) =>
      fetchApi<BreakoutSession>(
        `/rooms/${roomId}/breakout-sessions/${sessionId}/retry/`,
        { method: 'POST' }
      ),
    onSuccess: (session, variables) => {
      queryClient.setQueryData(
        breakoutSessionKey(variables.roomId),
        session.status === 'closed' ? [] : [session]
      )
    },
  })
