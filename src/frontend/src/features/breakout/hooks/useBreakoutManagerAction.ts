import { useCallback, useState } from 'react'
import { queryClient } from '@/api/queryClient'
import { breakoutSessionKey } from '../api/useBreakoutSession'
import {
  classifyActionFailure,
  type ActionFailure,
} from '../utils/actionFailure'

/** Keep failures visible until the host tries again; polls must not erase them. */
export const useBreakoutManagerAction = (roomId: string) => {
  const [actionFailure, setActionFailure] = useState<ActionFailure | null>(null)
  const runAction = useCallback(
    async (action: () => Promise<unknown>) => {
      setActionFailure(null)
      try {
        await action()
        return true
      } catch (error) {
        setActionFailure(classifyActionFailure(error))
        await queryClient.invalidateQueries({
          queryKey: breakoutSessionKey(roomId),
        })
        return false
      }
    },
    [roomId]
  )
  return { actionFailure, runAction }
}
