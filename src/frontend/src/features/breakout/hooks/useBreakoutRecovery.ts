import { useCallback, useEffect, useRef } from 'react'
import type { DisconnectReason } from 'livekit-client'
import { navigateTo } from '@/navigation/navigateTo'
import {
  breakoutStore,
  clearBreakoutState,
  requestAssignmentRefresh,
} from '../stores/breakout'
import { BREAKOUT_DEFAULTS } from '../utils/constants'

/** Give assignment polling a bounded opportunity to restore a dropped connection. */
export const useBreakoutRecovery = (roomId: string) => {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const stopRecovery = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }, [])
  useEffect(() => stopRecovery, [stopRecovery])

  const recoverSession = useCallback(
    (reason?: DisconnectReason) => {
      // A retry failure belongs to the same outage and must not extend its deadline.
      if (timer.current) return
      breakoutStore.connectionLost = true
      requestAssignmentRefresh()
      timer.current = setTimeout(() => {
        timer.current = null
        if (!breakoutStore.connectionLost) return
        clearBreakoutState()
        navigateTo('feedback', {}, { state: { reason, room_id: roomId } })
      }, BREAKOUT_DEFAULTS.RECOVERY_TIMEOUT_MS)
    },
    [roomId]
  )
  return { recoverSession, stopRecovery }
}
