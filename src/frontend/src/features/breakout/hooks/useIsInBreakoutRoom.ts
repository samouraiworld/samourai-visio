/**
 * Derived state: is the current user in a breakout room?
 */

import { useSnapshot } from 'valtio'
import { breakoutStore } from '../stores/breakout'

export const useIsInBreakoutRoom = () => {
  const snap = useSnapshot(breakoutStore)
  return {
    isInBreakoutRoom: !!snap.currentBreakoutRoomLkName,
    currentBreakoutRoomLkName: snap.currentBreakoutRoomLkName,
    mainRoomSlug: snap.mainRoomSlug,
    isTransitioning: snap.isTransitioning,
  }
}
