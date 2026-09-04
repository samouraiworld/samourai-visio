import { useMutation, useQuery } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'
import { queryClient } from '@/api/queryClient'
import type { BreakoutHelpRequest } from './types'

export const breakoutHelpRequestsKey = (roomId?: string, sessionId?: string) =>
  ['breakout-help-requests', roomId, sessionId] as const

export const acknowledgeBreakoutHelp = ({
  roomId,
  sessionId,
  helpRequestId,
  expectedBreakoutRoomId,
  expectedAssignmentRevision,
}: {
  roomId: string
  sessionId: string
  helpRequestId: string
  expectedBreakoutRoomId: string
  expectedAssignmentRevision: number
}) =>
  fetchApi<BreakoutHelpRequest>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/acknowledge-help/`,
    {
      method: 'POST',
      body: JSON.stringify({
        help_request_id: helpRequestId,
        expected_breakout_room_id: expectedBreakoutRoomId,
        expected_assignment_revision: expectedAssignmentRevision,
      }),
    }
  )

export const useBreakoutHelpRequests = (
  roomId?: string,
  sessionId?: string,
  enabled = true
) =>
  useQuery({
    queryKey: breakoutHelpRequestsKey(roomId, sessionId),
    queryFn: () =>
      fetchApi<BreakoutHelpRequest[]>(
        `/rooms/${roomId}/breakout-sessions/${sessionId}/help-requests/`
      ),
    enabled: enabled && !!roomId && !!sessionId,
    refetchInterval: 5000,
  })

export const useAcknowledgeBreakoutHelp = () =>
  useMutation({
    mutationFn: acknowledgeBreakoutHelp,
    onSuccess: (_data, variables) =>
      queryClient.invalidateQueries({
        queryKey: breakoutHelpRequestsKey(
          variables.roomId,
          variables.sessionId
        ),
      }),
  })
