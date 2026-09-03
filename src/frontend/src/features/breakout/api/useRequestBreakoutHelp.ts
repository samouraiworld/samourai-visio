/**
 * Mutation hook: request help from the host while inside a breakout room.
 */

import { useMutation } from '@tanstack/react-query'
import { fetchApi } from '@/api/fetchApi'

interface RequestHelpParams {
  roomId: string
  sessionId: string
  breakoutRoomId: string
  participantName?: string
}

interface RequestHelpResponse {
  status: string
}

const requestHelp = ({
  roomId,
  sessionId,
  breakoutRoomId,
  participantName,
}: RequestHelpParams): Promise<RequestHelpResponse> => {
  return fetchApi<RequestHelpResponse>(
    `/rooms/${roomId}/breakout-sessions/${sessionId}/request-help/`,
    {
      method: 'POST',
      body: JSON.stringify({
        breakout_room_id: breakoutRoomId,
        participant_name: participantName,
      }),
    }
  )
}

export const useRequestBreakoutHelp = () => {
  return useMutation({
    mutationFn: requestHelp,
  })
}
